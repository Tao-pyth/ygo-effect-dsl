from __future__ import annotations

import argparse
import json

from ygo_effect_dsl.external.ocgcore import (
    bootstrap_ocgcore,
    bootstrap_ocgcore_assets,
    doctor_ocgcore,
    verify_ocgcore,
    verify_ocgcore_assets,
)


def cmd_ocgcore_bootstrap(args: argparse.Namespace) -> int:
    manifest = bootstrap_ocgcore(
        external_root=args.external_root,
        offline=args.offline,
        source_only=args.source_only,
    )
    build = manifest["build"]
    if build is None:
        print(f"ocgcore-bootstrap: ok lock_id={manifest['lock_id']} source_only=true")
    else:
        binary = build["binary"]
        print(
            f"ocgcore-bootstrap: ok lock_id={manifest['lock_id']} "
            f"api={build['api']['major']}.{build['api']['minor']} "
            f"sha256={binary['sha256']} binary={binary['path']}"
        )
    return 0


def cmd_ocgcore_verify(args: argparse.Namespace) -> int:
    result = verify_ocgcore(external_root=args.external_root)
    build = result["build"]
    mode = "runtime" if build is not None else "source-only"
    print(f"ocgcore-verify: ok lock_id={result['lock_id']} mode={mode}")
    return 0


def cmd_ocgcore_doctor(args: argparse.Namespace) -> int:
    result = doctor_ocgcore(external_root=args.external_root)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


def cmd_ocgcore_assets_bootstrap(args: argparse.Namespace) -> int:
    manifest = bootstrap_ocgcore_assets(
        external_root=args.external_root,
        offline=args.offline,
    )
    print(
        f"ocgcore-assets-bootstrap: ok asset_lock_id={manifest['asset_lock_id']} "
        f"repositories={len(manifest['repositories'])}"
    )
    return 0


def cmd_ocgcore_assets_verify(args: argparse.Namespace) -> int:
    result = verify_ocgcore_assets(external_root=args.external_root)
    print(
        f"ocgcore-assets-verify: ok asset_lock_id={result['asset_lock_id']} "
        f"repositories={len(result['repositories'])}"
    )
    return 0
