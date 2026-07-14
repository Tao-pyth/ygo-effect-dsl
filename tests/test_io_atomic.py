from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ygo_effect_dsl.io_atomic import atomic_write_text, sha256_file
import ygo_effect_dsl.io_atomic as atomic_module


def test_atomic_text_writer_supports_concurrent_writers(tmp_path) -> None:
    path = tmp_path / "nested" / "artifact.json"
    values = [f'{{"writer":{index}}}\n' for index in range(32)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda value: atomic_write_text(path, value), values))

    assert path.read_text(encoding="utf-8") in values
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    assert len(sha256_file(path)) == 64


def test_atomic_text_writer_retries_transient_windows_conflict(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "artifact.json"
    replace = atomic_module.os.replace
    attempts = 0

    def _replace(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("transient")
        replace(source, destination)

    monkeypatch.setattr(atomic_module.os, "replace", _replace)
    monkeypatch.setattr(atomic_module.time, "sleep", lambda _seconds: None)

    atomic_write_text(path, "committed\n", replace_attempts=3)

    assert attempts == 3
    assert path.read_text(encoding="utf-8") == "committed\n"


def test_atomic_text_writer_preserves_destination_on_failure(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "artifact.json"
    path.write_text("preserved\n", encoding="utf-8")

    def _replace(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(atomic_module.os, "replace", _replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(path, "new\n")

    assert path.read_text(encoding="utf-8") == "preserved\n"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
