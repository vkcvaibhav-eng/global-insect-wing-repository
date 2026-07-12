"""Versioned model artifact persistence and checksum validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import pickle
from pathlib import Path
from typing import Any

from wing_repository.errors import ValidationError


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """A saved model artifact with its storage key and checksum."""

    storage_key: str
    sha256: str
    byte_size: int


def artifact_path(root: Path, storage_key: str) -> Path:
    """Resolve a relative artifact storage key under a configured root."""

    if Path(storage_key).is_absolute() or ".." in Path(storage_key).parts:
        raise ValidationError("Artifact storage key must be a safe relative path.")
    return root / storage_key


def save_pickle_artifact(
    payload: dict[str, Any],
    *,
    root: Path,
    storage_key: str,
) -> StoredArtifact:
    """Save a deterministic pickle artifact without overwriting active versions."""

    path = artifact_path(root, storage_key)
    if path.exists():
        raise ValidationError("Model artifact already exists and will not be overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    path.write_bytes(data)
    return StoredArtifact(
        storage_key=storage_key,
        sha256=sha256(data).hexdigest(),
        byte_size=len(data),
    )


def load_pickle_artifact(
    *,
    root: Path,
    storage_key: str,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load and verify a saved model artifact."""

    data = artifact_path(root, storage_key).read_bytes()
    digest = sha256(data).hexdigest()
    if digest != expected_sha256:
        raise ValidationError("Model artifact checksum validation failed.")
    payload = pickle.loads(data)
    if not isinstance(payload, dict):
        raise ValidationError("Model artifact payload is invalid.")
    return payload


__all__ = [
    "StoredArtifact",
    "artifact_path",
    "load_pickle_artifact",
    "save_pickle_artifact",
]
