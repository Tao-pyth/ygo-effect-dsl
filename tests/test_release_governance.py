from __future__ import annotations

from pathlib import Path

from ygo_effect_dsl.release_governance import (
    IssueSnapshot,
    audit_issue,
    load_release_governance_policy,
    target_version,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / ".github" / "release-governance.yml"


def test_release_governance_has_unique_label_and_milestone_pairs() -> None:
    policy = load_release_governance_policy(POLICY_PATH)

    assert policy.repository == "Tao-pyth/ygo-effect-dsl"
    assert policy.managed_issue_minimum == 84
    assert tuple(policy.versions) == (
        "0.3.0",
        "0.4.0",
        "0.5.0",
        "0.5.1",
        "1.0.0",
    )
    assert policy.versions["0.3.0"].release_state == "released"
    assert policy.versions["0.5.1"].milestone == "v0.5.1"


def test_title_version_precedes_legacy_range_and_override() -> None:
    policy = load_release_governance_policy(POLICY_PATH)
    explicit = IssueSnapshot(108, "[v0.5.0][test] explicit", (), None)
    overridden = IssueSnapshot(108, "legacy calibration", (), None)
    ranged = IssueSnapshot(120, "legacy search", (), None)

    assert target_version(explicit, policy) == "0.5.0"
    assert target_version(overridden, policy) == "0.5.1"
    assert target_version(ranged, policy) == "0.3.0"


def test_audit_reports_each_label_and_milestone_failure() -> None:
    policy = load_release_governance_policy(POLICY_PATH)
    missing = audit_issue(
        IssueSnapshot(159, "[v0.5.0][spec] jobs", (), None),
        policy,
    )
    conflicting = audit_issue(
        IssueSnapshot(
            159,
            "[v0.5.0][spec] jobs",
            ("version:0.4.0", "version:0.5.1"),
            "v0.4.0",
        ),
        policy,
    )

    assert missing.codes == ("missing_version_label", "missing_milestone")
    assert conflicting.codes == (
        "multiple_version_labels",
        "wrong_milestone",
    )


def test_audit_accepts_exact_target_and_exempts_prebaseline_history() -> None:
    policy = load_release_governance_policy(POLICY_PATH)
    current = audit_issue(
        IssueSnapshot(
            237,
            "[v0.5.1][test] portfolio",
            ("validation", "version:0.5.1"),
            "v0.5.1",
        ),
        policy,
    )
    historical = audit_issue(
        IssueSnapshot(33, "V0.2 replay", ("v0.2",), "V0.2: Bridge / Replay Baseline"),
        policy,
    )

    assert current.compliant is True
    assert historical.compliant is True


def test_released_target_rejects_an_open_issue() -> None:
    policy = load_release_governance_policy(POLICY_PATH)

    finding = audit_issue(
        IssueSnapshot(
            186,
            "[v0.3.0][wiki] historical guide",
            ("version:0.3.0",),
            "v0.3.0",
            "open",
        ),
        policy,
    )

    assert finding.codes == ("open_issue_in_released_milestone",)
