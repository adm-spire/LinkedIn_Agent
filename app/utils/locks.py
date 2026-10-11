"""Cross-process file lock to prevent overlapping cron executions."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path


class FileLock:
    """An advisory, non-blocking exclusive lock backed by ``fcntl.flock``."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._fh = None

    def acquire(self) -> bool:
        """Try to take the lock; return False if another process holds it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "w", encoding="utf-8")
        try:
            # LOCK_NB => don't block; a held lock raises instead of waiting.
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        """Release the lock (safe to call even if never acquired)."""
        if self._fh is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None
