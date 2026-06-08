"""Small JSON persistence helpers.

The helpers keep machine-local state files intact under partial writes and
serialize read-modify-write sections across Edith processes.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def read_json_file(path: Path, default: Any) -> Any:
    """Read JSON from path, returning default on missing/corrupt files."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError):
        return default


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """Write JSON via same-directory temp file and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Exclusive advisory lock for a state file's read-modify-write section."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    with lock_path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _fsync_dir(path: Path) -> None:
    try:
        dir_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
