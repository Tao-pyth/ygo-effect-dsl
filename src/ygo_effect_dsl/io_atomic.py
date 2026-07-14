from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path


ATOMIC_REPLACE_ATTEMPTS = 100


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    replace_attempts: int = ATOMIC_REPLACE_ATTEMPTS,
) -> None:
    if not isinstance(text, str):
        raise TypeError("atomic_write_text text must be a string")
    if (
        not isinstance(replace_attempts, int)
        or isinstance(replace_attempts, bool)
        or replace_attempts < 1
    ):
        raise ValueError("replace_attempts must be an integer >= 1")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        stream = os.fdopen(descriptor, "w", encoding=encoding, newline="\n")
        descriptor_open = False
        with stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(replace_attempts):
            try:
                os.replace(temporary, destination)
                break
            except PermissionError:
                if attempt + 1 == replace_attempts:
                    raise
                time.sleep(0.01)
    except BaseException:
        if descriptor_open:
            try:
                os.close(descriptor)
            except OSError:
                pass
        temporary.unlink(missing_ok=True)
        raise
