"""Environment-backed application configuration.

Configuration is intentionally small in version 0.1.  Callers may construct a
``Settings`` object directly in tests, while the running application uses
``get_settings`` to read the process environment once.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_DATABASE_URL = "sqlite:///data/wing_repository.db"
DEFAULT_DATA_DIR = Path("data")
DEFAULT_MAX_UPLOAD_MB = 25


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str = DEFAULT_DATABASE_URL
    data_dir: Path = DEFAULT_DATA_DIR
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB

    @property
    def original_image_dir(self) -> Path:
        """Directory containing write-once original image uploads."""

        return self.data_dir / "originals"

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the environment.

        A local ``.env`` file is useful for the demonstration; deployments
        should inject the same variables through their secret manager.
        """

        load_dotenv()
        raw_limit = os.getenv("WBR_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
        try:
            max_upload_mb = int(raw_limit)
        except ValueError as exc:
            raise ValueError("WBR_MAX_UPLOAD_MB must be an integer") from exc
        if max_upload_mb <= 0:
            raise ValueError("WBR_MAX_UPLOAD_MB must be positive")

        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            data_dir=Path(os.getenv("WBR_DATA_DIR", str(DEFAULT_DATA_DIR))),
            max_upload_mb=max_upload_mb,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings object."""

    return Settings.from_env()
