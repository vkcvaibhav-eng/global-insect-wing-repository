"""Provenance helpers for external source files and model builds."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import platform
from typing import Iterable

import numpy as np
import pandas as pd


def file_sha256(path: Path) -> str:
    """Return SHA-256 for a source or artifact file."""

    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_hashes(paths: Iterable[Path]) -> dict[str, str]:
    """Return source-file hashes keyed by filename."""

    return {path.name: file_sha256(path) for path in sorted(paths)}


def software_versions() -> dict[str, str]:
    """Return software versions needed for reproducing a model build."""

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


__all__ = ["file_sha256", "software_versions", "source_hashes"]
