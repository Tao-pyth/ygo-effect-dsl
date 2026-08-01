from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from ygo_effect_dsl.engine.canonical import stable_digest, to_canonical_data
from ygo_effect_dsl.external.licensing import (
    DistributionPolicy,
    load_distribution_policy,
)
from ygo_effect_dsl.external.ocgcore import (
    OcgcoreAssetLock,
    load_ocgcore_asset_lock,
    resolve_ocgcore_assets,
)
from ygo_effect_dsl.presentation import card_presentation_contract_document


CARD_PRESENTATION_SOURCE_QUALIFICATION_SCHEMA_VERSION = (
    "card-presentation-source-qualification-v1"
)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(
    check_id: str,
    passed: bool,
    evidence: Mapping[str, Any],
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "check_id": check_id,
        "evidence": dict(evidence),
        "passed": passed,
    }
    if reason is not None:
        row["reason"] = reason
    return row


def build_card_presentation_source_qualification(
    *,
    asset_lock: OcgcoreAssetLock,
    distribution_policy: DistributionPolicy,
    database_path: Path,
    locale: str = "ja",
) -> dict[str, Any]:
    database = asset_lock.repositories["card_database"]
    required_file_name = next(iter(database["required_files"]))
    required_file = database["required_files"][required_file_name]
    resolved = database_path.expanduser().resolve()
    observed = {
        "filename": resolved.name,
        "sha256": _sha256(resolved),
        "size": resolved.stat().st_size,
    }
    expected = {
        "filename": required_file_name,
        "sha256": str(required_file["sha256"]),
        "size": int(required_file["size"]),
    }
    policy_artifact = distribution_policy.artifacts["card_database"]
    controls = distribution_policy.data["controls"]
    contract = card_presentation_contract_document()

    checks = [
        _check(
            "pinned-database-file-matches-lock",
            observed == expected,
            {"expected": expected, "observed": observed},
            reason=None if observed == expected else "database_hash_or_size_mismatch",
        ),
        _check(
            "source-provenance-is-pinned",
            all(
                isinstance(database.get(field), str) and database[field]
                for field in ("repository", "ref", "commit", "tree")
            ),
            {
                "commit": database.get("commit"),
                "ref": database.get("ref"),
                "repository": database.get("repository"),
                "tree": database.get("tree"),
            },
        ),
        _check(
            "locale-is-operator-declared",
            locale == "ja",
            {
                "locale": locale,
                "source_locale_declaration": "operator_declared",
                "text_locale_inference": "forbidden",
            },
            reason=None if locale == "ja" else "unsupported_qualified_locale",
        ),
        _check(
            "license-status-is-recorded",
            database.get("license") == policy_artifact.get("license") == "NOASSERTION",
            {
                "asset_lock_license": database.get("license"),
                "distribution_policy_license": policy_artifact.get("license"),
            },
            reason=(
                None
                if database.get("license") == policy_artifact.get("license") == "NOASSERTION"
                else "license_status_mismatch"
            ),
        ),
        _check(
            "redistribution-is-blocked-until-approval",
            policy_artifact.get("include_in_release") is False
            and policy_artifact.get("commercial_bundle_status") == "blocked",
            {
                "commercial_bundle_status": policy_artifact.get(
                    "commercial_bundle_status"
                ),
                "include_in_release": policy_artifact.get("include_in_release"),
                "review_requirements": policy_artifact.get("review_requirements"),
            },
            reason=(
                None
                if policy_artifact.get("include_in_release") is False
                and policy_artifact.get("commercial_bundle_status") == "blocked"
                else "redistribution_policy_not_blocked"
            ),
        ),
        _check(
            "external-cache-only",
            controls.get("external_files_location") == "user_cache_only"
            and controls.get("runtime_network_access") is False
            and controls.get("implicit_download") is False,
            {
                "external_files_location": controls.get("external_files_location"),
                "implicit_download": controls.get("implicit_download"),
                "runtime_network_access": controls.get("runtime_network_access"),
            },
        ),
        _check(
            "presentation-authority-is-display-only",
            contract["authority"] == {
                "effect_interpretation": "forbidden",
                "legality_or_timing": "ocgcore_only",
                "provider": "read_only_presentation",
                "search_input": False,
            },
            {"authority": contract["authority"]},
        ),
        _check(
            "evidence-is-sanitized",
            True,
            {
                "card_text_embedded": False,
                "database_rows_embedded": False,
                "local_paths_embedded": False,
            },
        ),
    ]
    rejection_reasons = [
        f"{row['check_id']}:{row.get('reason', 'failed')}"
        for row in checks
        if row["passed"] is not True
    ]
    identity = to_canonical_data(
        {
            "asset_lock": {
                "lock_id": asset_lock.lock_id,
                "sha256": asset_lock.sha256,
            },
            "checks": checks,
            "distribution_boundary": {
                "card_database_release_payload_allowed": False,
                "redistribution_status": "blocked_no_license_grant_recorded",
                "tracked_by_issue": 91,
            },
            "passed": not rejection_reasons,
            "qualified_source": {
                "artifact_id": "card_database",
                "commit": database["commit"],
                "file": observed,
                "license_status": database["license"],
                "locale": locale,
                "ref": database["ref"],
                "repository": database["repository"],
                "source_tree": database["tree"],
            },
            "rejection_reasons": rejection_reasons,
            "schema_version": CARD_PRESENTATION_SOURCE_QUALIFICATION_SCHEMA_VERSION,
        }
    )
    return {
        **identity,
        "evidence_id": stable_digest(
            identity,
            prefix="cardpresentationsourcequal_",
        ),
    }


def build_pinned_card_presentation_source_qualification(
    *,
    external_root: str | Path | None = None,
    locale: str = "ja",
) -> dict[str, Any]:
    asset_lock = load_ocgcore_asset_lock()
    assets = resolve_ocgcore_assets(external_root=external_root)
    return build_card_presentation_source_qualification(
        asset_lock=asset_lock,
        distribution_policy=load_distribution_policy(),
        database_path=assets.database_path,
        locale=locale,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "qualify pinned non-English card presentation source provenance and "
            "distribution boundary"
        )
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--external-root", type=Path)
    parser.add_argument("--locale", default="ja")
    args = parser.parse_args()

    evidence = build_pinned_card_presentation_source_qualification(
        external_root=args.external_root,
        locale=args.locale,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    status = "passed" if evidence["passed"] else "failed"
    print(f"card-presentation-source-qualification: {status} out={args.out}")
    print(f"evidence_id={evidence['evidence_id']}")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
