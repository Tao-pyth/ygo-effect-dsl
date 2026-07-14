from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ygo_effect_dsl.runtime_imports import (
    current_checkout_environment,
    package_source_root,
)


def test_checkout_environment_prepends_active_source_root(tmp_path: Path) -> None:
    other_source = str(tmp_path / "other" / "source")
    existing = os.pathsep.join([other_source, str(package_source_root())])

    environment = current_checkout_environment({"PYTHONPATH": existing})

    entries = environment["PYTHONPATH"].split(os.pathsep)
    assert Path(entries[0]).resolve() == package_source_root()
    assert entries.count(str(package_source_root())) == 1
    assert other_source in entries


def test_child_python_imports_the_same_checkout() -> None:
    command = [
        sys.executable,
        "-c",
        (
            "import json, ygo_effect_dsl, ygo_effect_dsl.prototype._real_core_worker as w; "
            "print(json.dumps({'package': ygo_effect_dsl.__file__, 'worker': w.__file__}))"
        ),
    ]

    completed = subprocess.run(
        command,
        env=current_checkout_environment(os.environ),
        check=True,
        text=True,
        capture_output=True,
    )
    imported = json.loads(completed.stdout)

    assert Path(imported["package"]).resolve().is_relative_to(package_source_root())
    assert Path(imported["worker"]).resolve().is_relative_to(package_source_root())
