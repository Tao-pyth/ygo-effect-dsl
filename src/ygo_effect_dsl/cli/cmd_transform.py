from __future__ import annotations

import argparse

from ygo_effect_dsl.pipeline.transform import run_transform


def cmd_transform(args: argparse.Namespace) -> int:
    return run_transform(args)
