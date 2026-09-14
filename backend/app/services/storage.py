"""
File storage abstraction for evidence uploads.

Phase 1 scope only: save bytes, get them back, know how big they are. This
deliberately does **not** hash or verify anything -- SHA-256 integrity
verification is Phase 4 (Evidence Integrity). PostgreSQL's `evidence.
storage_path` column stores only the reference this module returns, never
the bytes themselves (see `app/db/models.py:Evidence`).

`LocalFileStorage` is the only implementation today (a local directory --
fine for a prototype/single-instance deployment) but every caller depends
on the small `Storage` protocol below, not on `LocalFileStorage` directly,
so swapping in an S3/object-storage-backed implementation later is a
one-file change, not a call-site rewrite.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    def save(self, investigation_id: str, original_filename: str, data: bytes) -> str:
        """Persist `data`, return an opaque storage reference (path/key)."""
        ...

    def read(self, storage_ref: str) -> bytes:
        """Return the bytes previously saved at `storage_ref`."""
        ...


class LocalFileStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, investigation_id: str, original_filename: str, data: bytes) -> str:
        safe_name = Path(original_filename).name  # strip any path components -- no traversal
        unique = f"{uuid.uuid4().hex[:12]}_{safe_name}"
        directory = self.root / investigation_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / unique
        target.write_bytes(data)
        return str(target.relative_to(self.root))

    def read(self, storage_ref: str) -> bytes:
        path = self.root / storage_ref
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Refusing to read outside the evidence storage root.")
        return path.read_bytes()


_storage: LocalFileStorage | None = None


def get_storage() -> LocalFileStorage:
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = LocalFileStorage(settings.evidence_storage_dir)
    return _storage
