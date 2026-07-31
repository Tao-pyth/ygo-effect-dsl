from __future__ import annotations

import argparse

from ygo_effect_dsl.support_bundle import write_redacted_support_bundle


def cmd_support_bundle(args: argparse.Namespace) -> int:
    manifest = write_redacted_support_bundle(
        output_dir=args.out,
        external_root=args.external_root,
        recent_error_json=args.recent_error_json,
        private_canaries=args.private_canary,
        size_limit_bytes=args.size_limit_bytes,
    )
    print(
        "support-bundle: ok "
        f"bundle_id={manifest['bundle_id']} "
        f"files={len(manifest['files'])} out={args.out}"
    )
    return 0


__all__ = ["cmd_support_bundle"]
