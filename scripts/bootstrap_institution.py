"""Create or update the first real administrator and standard template."""

from __future__ import annotations

from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from wing_repository.config import get_settings
from wing_repository.db import SessionLocal, engine
from wing_repository.errors import RepositoryError
from wing_repository.institution_bootstrap import ensure_institution_bootstrap


def main() -> None:
    load_dotenv()
    if not inspect(engine).has_table("users"):
        raise SystemExit("Database schema is missing; run `alembic upgrade head` first.")

    settings = get_settings()
    try:
        with SessionLocal() as session:
            summary = ensure_institution_bootstrap(session, settings)
    except (RepositoryError, SQLAlchemyError) as exc:
        raise SystemExit(f"Institution bootstrap failed: {exc}") from exc

    if not summary:
        raise SystemExit(
            "No bootstrap administrator is configured. Set "
            "WBR_BOOTSTRAP_ADMIN_EMAIL and WBR_BOOTSTRAP_ADMIN_PASSWORD."
        )
    print("Institution bootstrap complete")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
