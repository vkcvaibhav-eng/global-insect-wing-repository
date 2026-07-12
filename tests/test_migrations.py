from __future__ import annotations

from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from wing_repository.config import get_settings
from wing_repository.db import build_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IDENTIFIER_LIMIT = 63
ALEMBIC_VERSION_NUM_LIMIT = 32


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
                "external_reference_datasets",
                "external_reference_shapes",
                "external_reference_import_issues",
                "analysis_models",
                "wing_analysis_runs",
                "region_probabilities",
                "lineage_probabilities",
                "published_shape_matches",
                "alembic_version",
            }
            assert expected_tables <= set(inspect(engine).get_table_names())
            with engine.connect() as connection:
                assert connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                ) == "0006_retire_apis_v1"
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


def test_migration_0006_retires_old_apis_template_and_assignments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "retire-old-template.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))

    try:
        command.upgrade(config, "0005_apis_analysis")
        engine = build_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO users
                            (id, email, full_name, password_hash, role, is_active)
                        VALUES
                            (100, 'admin@example.test', 'Admin', 'hash',
                             'administrator', 1),
                            (101, 'student@example.test', 'Student', 'hash',
                             'student', 1)
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO taxa
                            (id, order_name, order_code, family, genus,
                             genus_code, next_accession_serial)
                        VALUES
                            (200, 'Hymenoptera', 'HYM', 'Apidae', 'Apis',
                             'APIS', 1)
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO landmark_templates
                            (id, taxon_id, version, name, side, wing_type,
                             status, created_by_id)
                        VALUES
                            (300, 200, 1, 'Apis right-forewing teaching template',
                             'right', 'forewing', 'published', 100)
                        """
                    )
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO assignments
                            (id, student_id, taxon_id, template_id,
                             assigned_by_id, is_active)
                        VALUES
                            (400, 101, 200, 300, 100, 1)
                        """
                    )
                )
            engine.dispose()

            command.upgrade(config, "head")
            engine = build_engine(database_url)
            with engine.connect() as connection:
                assert connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                ) == "0006_retire_apis_v1"
                assert connection.scalar(
                    text("SELECT status FROM landmark_templates WHERE id = 300")
                ) == "retired"
                row = connection.execute(
                    text("SELECT is_active, ended_at FROM assignments WHERE id = 400")
                ).one()
                assert row.is_active in (False, 0)
                assert row.ended_at is not None
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()


def test_migration_identifiers_fit_postgresql_limit() -> None:
    migration_paths = sorted((PROJECT_ROOT / "alembic" / "versions").glob("*.py"))
    assert migration_paths

    too_long: list[str] = []
    for migration_path in migration_paths:
        migration_text = migration_path.read_text(encoding="utf-8")
        names = set(re.findall(r'op\.f\("([^"]+)"\)', migration_text))
        names.update(re.findall(r'name="([^"]+)"', migration_text))
        too_long.extend(
            f"{migration_path.name}: {name} ({len(name)})"
            for name in sorted(names)
            if len(name) > POSTGRES_IDENTIFIER_LIMIT
        )

    assert too_long == []


def test_alembic_revision_ids_fit_default_version_table() -> None:
    migration_paths = sorted((PROJECT_ROOT / "alembic" / "versions").glob("*.py"))
    assert migration_paths

    too_long: list[str] = []
    for migration_path in migration_paths:
        migration_text = migration_path.read_text(encoding="utf-8")
        match = re.search(r'^revision:\s*str\s*=\s*"([^"]+)"', migration_text, re.M)
        assert match is not None, migration_path.name
        revision_id = match.group(1)
        if len(revision_id) > ALEMBIC_VERSION_NUM_LIMIT:
            too_long.append(
                f"{migration_path.name}: {revision_id} ({len(revision_id)})"
            )

    assert too_long == []
