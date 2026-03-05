from __future__ import annotations

import argparse

from ygo_effect_dsl.pipeline.analyze import run_analyze


def cmd_analyze(args: argparse.Namespace) -> int:
    return run_analyze(args)
