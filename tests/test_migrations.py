from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from wing_repository.config import get_settings
from wing_repository.db import build_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_upgrades_an_empty_sqlite_database_to_head(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "migrated.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))

    try:
        command.upgrade(config, "head")
        engine = build_engine(database_url)
        try:
            expected_tables = {
                "users",
                "assignments",
                "taxa",
                "specimens",
                "wing_images",
                "landmark_templates",
                "template_landmarks",
                "annotations",
                "annotation_points",
                "reviews",
                "repository_records",
                "alembic_version",
            }
            assert expected_tables <= set(inspect(engine).get_table_names())
            with engine.connect() as connection:
                assert connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                ) == "0002_image_calibration"
                wing_columns = {
                    column["name"] for column in inspect(engine).get_columns("wing_images")
                }
                assert {
                    "scale_reference_length",
                    "scale_reference_unit",
                    "scale_reference_pixels",
                    "scale_mm_per_pixel",
                    "scale_x1_pixel",
                    "scale_y1_pixel",
                    "scale_x2_pixel",
                    "scale_y2_pixel",
                    "scale_calibrated_at",
                } <= wing_columns
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()
