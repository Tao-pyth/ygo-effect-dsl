from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import quote

import yaml


RELEASE_GOVERNANCE_SCHEMA_VERSION = "release-governance-v1"
_VERSION_TITLE = re.compile(r"\[(?:milestone )?v(?P<version>\d+\.\d+\.\d+)\]", re.I)


@dataclass(frozen=True)
class VersionRule:
    version: str
    label: str
    milestone: str
    release_state: str


@dataclass(frozen=True)
class LegacyRange:
    first: int
    last: int
    version: str


@dataclass(frozen=True)
class ReleaseGovernancePolicy:
    repository: str
    managed_issue_minimum: int
    versions: Mapping[str, VersionRule]
    legacy_ranges: tuple[LegacyRange, ...]
    overrides: Mapping[int, str]


@dataclass(frozen=True)
class IssueSnapshot:
    number: int
    title: str
    labels: tuple[str, ...]
    milestone: str | None
    state: str = "open"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IssueSnapshot":
        raw_labels = value.get("labels", ())
        if not isinstance(raw_labels, Sequence):
            raise ValueError("issue labels must be a sequence")
        labels = tuple(
            str(item["name"] if isinstance(item, Mapping) else item)
            for item in raw_labels
        )
        raw_milestone = value.get("milestone")
        milestone = None
        if isinstance(raw_milestone, Mapping):
            milestone = str(raw_milestone.get("title"))
        elif isinstance(raw_milestone, str):
            milestone = raw_milestone
        return cls(
            number=int(value["number"]),
            title=str(value["title"]),
            labels=labels,
            milestone=milestone,
            state=str(value.get("state", "open")).lower(),
        )


@dataclass(frozen=True)
class IssueGovernanceFinding:
    issue_number: int
    target_version: str | None
    codes: tuple[str, ...]
    observed_version_labels: tuple[str, ...]
    observed_milestone: str | None

    @property
    def compliant(self) -> bool:
        return not self.codes

    def to_dict(self) -> dict[str, Any]:
        return {
            "codes": list(self.codes),
            "issue_number": self.issue_number,
            "observed_milestone": self.observed_milestone,
            "observed_version_labels": list(self.observed_version_labels),
            "target_version": self.target_version,
        }


def _required_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def load_release_governance_policy(path: str | Path) -> ReleaseGovernancePolicy:
    source = Path(path)
    document = _required_mapping(
        yaml.safe_load(source.read_text(encoding="utf-8")), "$"
    )
    if document.get("schema_version") != RELEASE_GOVERNANCE_SCHEMA_VERSION:
        raise ValueError("unsupported release governance schema")
    raw_versions = document.get("version_labels")
    if not isinstance(raw_versions, Sequence):
        raise ValueError("$.version_labels must be a sequence")
    versions: dict[str, VersionRule] = {}
    labels: set[str] = set()
    milestones: set[str] = set()
    for index, raw in enumerate(raw_versions):
        item = _required_mapping(raw, f"$.version_labels[{index}]")
        rule = VersionRule(
            version=str(item.get("version", "")),
            label=str(item.get("label", "")),
            milestone=str(item.get("milestone", "")),
            release_state=str(item.get("release_state", "")),
        )
        if not all((rule.version, rule.label, rule.milestone, rule.release_state)):
            raise ValueError(f"$.version_labels[{index}] has an empty field")
        if rule.release_state not in {"active", "planned", "released"}:
            raise ValueError(f"$.version_labels[{index}] has an invalid release state")
        if (
            rule.version in versions
            or rule.label in labels
            or rule.milestone in milestones
        ):
            raise ValueError("release governance version entries must be unique")
        if rule.label != f"version:{rule.version}":
            raise ValueError("version label must use version:X.Y.Z")
        if rule.milestone != f"v{rule.version}":
            raise ValueError("milestone must use vX.Y.Z")
        versions[rule.version] = rule
        labels.add(rule.label)
        milestones.add(rule.milestone)

    raw_ranges = document.get("legacy_ranges", ())
    if not isinstance(raw_ranges, Sequence):
        raise ValueError("$.legacy_ranges must be a sequence")
    ranges = tuple(
        LegacyRange(
            first=int(_required_mapping(item, "$.legacy_ranges[]")["first"]),
            last=int(_required_mapping(item, "$.legacy_ranges[]")["last"]),
            version=str(_required_mapping(item, "$.legacy_ranges[]")["version"]),
        )
        for item in raw_ranges
    )
    raw_overrides = _required_mapping(document.get("overrides", {}), "$.overrides")
    overrides = {int(number): str(version) for number, version in raw_overrides.items()}
    referenced = {item.version for item in ranges} | set(overrides.values())
    unknown = referenced - set(versions)
    if unknown:
        raise ValueError(
            "governance mappings reference unknown versions: "
            f"{sorted(unknown)}"
        )
    return ReleaseGovernancePolicy(
        repository=str(document.get("repository", "")),
        managed_issue_minimum=int(document.get("managed_issue_minimum", 0)),
        versions=versions,
        legacy_ranges=ranges,
        overrides=overrides,
    )


def target_version(issue: IssueSnapshot, policy: ReleaseGovernancePolicy) -> str | None:
    title_match = _VERSION_TITLE.search(issue.title)
    if title_match:
        version = title_match.group("version")
        return version if version in policy.versions else None
    if issue.number in policy.overrides:
        return policy.overrides[issue.number]
    for item in policy.legacy_ranges:
        if item.first <= issue.number <= item.last:
            return item.version
    return None


def audit_issue(
    issue: IssueSnapshot,
    policy: ReleaseGovernancePolicy,
) -> IssueGovernanceFinding:
    if issue.number < policy.managed_issue_minimum:
        return IssueGovernanceFinding(issue.number, None, (), (), issue.milestone)
    version = target_version(issue, policy)
    known_labels = {item.label for item in policy.versions.values()}
    observed = tuple(sorted(set(issue.labels) & known_labels))
    if version is None:
        return IssueGovernanceFinding(
            issue.number,
            None,
            ("unclassified",),
            observed,
            issue.milestone,
        )
    expected = policy.versions[version]
    codes: list[str] = []
    if len(observed) == 0:
        codes.append("missing_version_label")
    elif len(observed) > 1:
        codes.append("multiple_version_labels")
    elif observed[0] != expected.label:
        codes.append("wrong_version_label")
    if issue.milestone is None:
        codes.append("missing_milestone")
    elif issue.milestone != expected.milestone:
        codes.append("wrong_milestone")
    if expected.release_state == "released" and issue.state == "open":
        codes.append("open_issue_in_released_milestone")
    return IssueGovernanceFinding(
        issue.number,
        version,
        tuple(codes),
        observed,
        issue.milestone,
    )


def audit_issues(
    issues: Sequence[IssueSnapshot],
    policy: ReleaseGovernancePolicy,
) -> tuple[IssueGovernanceFinding, ...]:
    return tuple(
        finding
        for issue in sorted(issues, key=lambda item: item.number)
        if not (finding := audit_issue(issue, policy)).compliant
    )


def _gh_json(
    arguments: Sequence[str],
    *,
    input_payload: Mapping[str, Any] | None = None,
) -> Any:
    completed = subprocess.run(
        ["gh", *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=(json.dumps(input_payload) if input_payload is not None else None),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "gh command failed")
    return json.loads(completed.stdout)


def fetch_issues(repository: str) -> tuple[IssueSnapshot, ...]:
    payload = _gh_json(
        (
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--limit",
            "1000",
            "--json",
            "number,title,state,labels,milestone",
        )
    )
    if not isinstance(payload, list):
        raise RuntimeError("gh issue list returned a non-list payload")
    return tuple(IssueSnapshot.from_mapping(item) for item in payload)


def apply_findings(
    findings: Sequence[IssueGovernanceFinding],
    policy: ReleaseGovernancePolicy,
) -> None:
    raw_milestones = _gh_json(
        (
            "api",
            f"repos/{policy.repository}/milestones?state=all&per_page=100",
        )
    )
    if not isinstance(raw_milestones, list):
        raise RuntimeError("GitHub milestone response must be a list")
    milestone_numbers = {
        str(item["title"]): int(item["number"])
        for item in raw_milestones
        if isinstance(item, Mapping)
    }
    for finding in findings:
        if finding.target_version is None:
            raise ValueError(
                f"issue #{finding.issue_number} is unclassified and cannot be applied"
            )
        rule = policy.versions[finding.target_version]
        if rule.milestone not in milestone_numbers:
            raise ValueError(f"GitHub milestone {rule.milestone!r} does not exist")
        for label in finding.observed_version_labels:
            if label != rule.label:
                _gh_json(
                    (
                        "api",
                        "--method",
                        "DELETE",
                        f"repos/{policy.repository}/issues/"
                        f"{finding.issue_number}/labels/{quote(label, safe='')}",
                    )
                )
        if rule.label not in finding.observed_version_labels:
            _gh_json(
                (
                    "api",
                    "--method",
                    "POST",
                    f"repos/{policy.repository}/issues/{finding.issue_number}/labels",
                    "--input",
                    "-",
                ),
                input_payload={"labels": [rule.label]},
            )
        _gh_json(
            (
                "api",
                "--method",
                "PATCH",
                f"repos/{policy.repository}/issues/{finding.issue_number}",
                "--input",
                "-",
            ),
            input_payload={"milestone": milestone_numbers[rule.milestone]},
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="audit or synchronize GitHub issue release governance"
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(".github/release-governance.yml"),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    policy = load_release_governance_policy(args.policy)
    issues = fetch_issues(policy.repository)
    findings = audit_issues(issues, policy)
    if args.apply and findings:
        apply_findings(findings, policy)
        findings = audit_issues(fetch_issues(policy.repository), policy)
    print(
        json.dumps(
            {
                "finding_count": len(findings),
                "findings": [item.to_dict() for item in findings],
                "managed_issue_count": sum(
                    issue.number >= policy.managed_issue_minimum for issue in issues
                ),
                "schema_version": RELEASE_GOVERNANCE_SCHEMA_VERSION,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
