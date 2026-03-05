from __future__ import annotations

import argparse

from ygo_effect_dsl.pipeline.validate import run_validate


def cmd_validate(args: argparse.Namespace) -> int:
    return run_validate(args)
