"""Small cross-process helpers for durable JSON state.

The project keeps several intentionally portable JSON stores.  They still need
the same basic guarantees: writers must not share a fixed temporary filename,
and concurrent writers must not enter the replace step at the same time.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Iterator


def _lock_is_stale(path: Path, stale_after: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime > stale_after
    except FileNotFoundError:
        return False


@contextmanager
def file_lock(path: str | Path, *, timeout: float = 10.0, stale_after: float = 300.0) -> Iterator[None]:
    """Acquire a small lock file without adding a platform dependency."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode("ascii", errors="ignore"))
        except FileExistsError:
            if _lock_is_stale(lock_path, stale_after):
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"无法获取状态文件锁：{target}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path: str | Path, content: str) -> None:
    """Write text through a unique temp file and an atomic replace."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def atomic_write_json(path: str | Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
