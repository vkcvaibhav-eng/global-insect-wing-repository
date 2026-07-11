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
DEFAULT_AUTO_BOOTSTRAP_DEMO = False
DEFAULT_STORAGE_BACKEND = "local"


def _environment_bool(value: str, variable_name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{variable_name} must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str = DEFAULT_DATABASE_URL
    data_dir: Path = DEFAULT_DATA_DIR
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    auto_bootstrap_demo: bool = DEFAULT_AUTO_BOOTSTRAP_DEMO
    storage_backend: str = DEFAULT_STORAGE_BACKEND
    r2_endpoint_url: str | None = None
    r2_bucket_name: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_key_prefix: str = "originals/"

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
        storage_backend = os.getenv("WBR_STORAGE_BACKEND", DEFAULT_STORAGE_BACKEND)
        storage_backend = storage_backend.strip().casefold()
        if storage_backend not in {"local", "r2"}:
            raise ValueError("WBR_STORAGE_BACKEND must be either 'local' or 'r2'")

        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            data_dir=Path(os.getenv("WBR_DATA_DIR", str(DEFAULT_DATA_DIR))),
            max_upload_mb=max_upload_mb,
            auto_bootstrap_demo=_environment_bool(
                os.getenv(
                    "WBR_AUTO_BOOTSTRAP_DEMO",
                    str(DEFAULT_AUTO_BOOTSTRAP_DEMO),
                ),
                "WBR_AUTO_BOOTSTRAP_DEMO",
            ),
            storage_backend=storage_backend,
            r2_endpoint_url=os.getenv("WBR_R2_ENDPOINT_URL"),
            r2_bucket_name=os.getenv("WBR_R2_BUCKET_NAME"),
            r2_access_key_id=os.getenv("WBR_R2_ACCESS_KEY_ID"),
            r2_secret_access_key=os.getenv("WBR_R2_SECRET_ACCESS_KEY"),
            r2_key_prefix=os.getenv("WBR_R2_KEY_PREFIX", "originals/"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings object."""

    return Settings.from_env()
