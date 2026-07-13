from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.analysis_services import activate_validated_models, run_published_apis_reference_analysis
from wing_repository.config import get_settings
from wing_repository.enums import SpeciesIdentificationMethod, TemplateStatus
from wing_repository.errors import ValidationError
from wing_repository.image_store import LocalImageStore
from wing_repository.models import (
    AnalysisModel,
    Assignment,
    ExternalReferenceImportIssue,
    ExternalReferenceShape,
    LandmarkTemplate,
    RepositoryRecord,
    User,
)
from wing_repository.reference_data import (
    build_analysis_models,
    ensure_apis_19_template,
    import_algeria,
    import_kaur_india,
    import_kazakhstan,
    import_mexico,
    import_nawrocka,
    import_northwestern_europe,
    import_oleksa,
    import_queens_drones,
    import_serbia,
    import_southwest_asia,
    inspect_algeria,
    inspect_kaur_india,
    inspect_kazakhstan,
    inspect_mexico,
    inspect_nawrocka,
    inspect_northwestern_europe,
    inspect_oleksa,
    inspect_queens_drones,
    inspect_serbia,
    inspect_southwest_asia,
)
from wing_repository.services import (
    approve_annotation,
    create_draft_annotation,
    create_specimen_with_image,
    place_annotation_point,
    submit_annotation,
)
from wing_repository.ui.analysis_pages import _lineage_table, _nearest_table, _region_table
from wing_repository.ui.analysis_pages import analysis_activation_readiness


def _base_shape() -> np.ndarray:
    angles = np.linspace(0, 2 * np.pi, 19, endpoint=False)
    return np.column_stack((np.cos(angles) + 0.05 * np.arange(19), 0.45 * np.sin(angles)))


def _deformed_shape(region_index: int, lineage_index: int, replicate: int) -> np.ndarray:
    shape = _base_shape().copy()
    shape[:, 0] += 0.025 * region_index * np.sin(np.linspace(0, np.pi, 19))
    shape[:, 1] += 0.025 * lineage_index * np.cos(np.linspace(0, np.pi, 19))
    shape[::3, 0] += 0.005 * replicate
    return shape


def _coordinate_columns(shape: np.ndarray) -> dict[str, float]:
    values: dict[str, float] = {}
    for ordinal, (x, y) in enumerate(shape, start=1):
        values[f"x{ordinal}"] = float(x)
        values[f"y{ordinal}"] = float(y)
    return values


def _write_synthetic_oleksa_csv(directory: Path) -> Path:
    rows = []
    regions = ["ES-PT", "HR-SI"]
    lineages = ["A", "C", "M", "O"]
    for sample_index in range(8):
        region = regions[sample_index % len(regions)]
        lineage = lineages[sample_index % len(lineages)]
        for replicate in range(2):
            shape = _deformed_shape(
                regions.index(region),
                lineages.index(lineage),
                replicate,
            )
            rows.append(
                {
                    "record_id": f"wing-{sample_index}-{replicate}",
                    "sample": f"sample-{sample_index}",
                    "country": region.split("-")[0],
                    "region": region,
                    "lineage": lineage,
                    **_coordinate_columns(shape),
                }
            )
    malformed = rows[0].copy()
    malformed["record_id"] = "malformed-wing"
    malformed["x19"] = "not-a-number"
    rows.append(malformed)
    path = directory / "EU-raw-coordinates.csv"
    import pandas as pd

    pd.DataFrame(rows).to_csv(path, index=False)
    (directory / "EU-geo-data.csv").write_text("sample,country\n", encoding="utf-8")
    (directory / "EU-lineage-classification.csv").write_text(
        "sample,lineage\n",
        encoding="utf-8",
    )
    (directory / "EU-aligned-coordinates.csv").write_text("sample\n", encoding="utf-8")
    (directory / "readme.txt").write_text("synthetic fixture\n", encoding="utf-8")
    return path


def _write_synthetic_kaur_india_csv(directory: Path) -> None:
    rows = []
    metadata_rows = []
    for sample_index in range(2):
        for side in ("L", "R"):
            shape = _deformed_shape(0, sample_index, 0)
            filename = f"IN-000{sample_index + 1}-synthetic-{side}.dw.png"
            rows.append(
                {
                    "file": filename,
                    **_coordinate_columns(shape),
                }
            )
            metadata_rows.append(
                {
                    "file": filename,
                    "sample": f"IN-000{sample_index + 1}",
                    "latitude": 34.2713,
                    "longitude": 74.7533,
                    "date": 2022,
                    "resolution": 94488,
                    "notes": "synthetic",
                }
            )
    import pandas as pd

    pd.DataFrame(rows).to_csv(directory / "IN-raw-coordinates.csv", index=False)
    pd.DataFrame(metadata_rows).to_csv(directory / "IN-data.csv", index=False)


def _write_synthetic_nawrocka_csv(directory: Path) -> None:
    import pandas as pd

    rows = []
    geo_rows = []
    aligned_rows = []
    fixtures = [
        ("A-ada-0698", "adansonii", "A", "Guinea", 10.0, -12.25),
        ("C-car-0501", "carnica", "C", "Austria", 47.5, 14.5),
        ("M-mel-0101", "mellifera", "M", "France", 46.2, 2.2),
        ("O-syr-0497", "syriaca", "O", "Syria", 35.0, 38.5),
    ]
    for sample_index, (
        sample,
        subspecies,
        lineage,
        country,
        latitude,
        longitude,
    ) in enumerate(fixtures):
        geo_rows.append(
            {
                "sample": sample,
                "subspecies": subspecies,
                "lineage": lineage,
                "country": country,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        aligned_rows.append(
            {
                "sample": sample,
                "subspecies": subspecies,
                "lineage": lineage,
                **_coordinate_columns(_deformed_shape(sample_index, sample_index, 0)),
            }
        )
        for replicate in range(2):
            rows.append(
                {
                    "file": f"{sample}-{replicate + 1:02d}.dw.png",
                    **_coordinate_columns(_deformed_shape(sample_index, sample_index, replicate)),
                }
            )
    pd.DataFrame(rows).to_csv(directory / "Nawrocka_et_al2018.csv", index=False)
    pd.DataFrame(geo_rows).to_csv(
        directory / "Nawrocka_et_al2018-geo-data.csv",
        index=False,
    )
    pd.DataFrame(aligned_rows).to_csv(
        directory / "Nawrocka_et_al2018-sample-aligned.csv",
        index=False,
    )
    (directory / "apis-wing-landmarks600.png").write_bytes(b"synthetic guide")


def _write_synthetic_queens_drones_csv(directory: Path) -> None:
    import pandas as pd

    for prefix, filename in (
        ("DD", "drones-raw-coordinates.csv"),
        ("QQ", "queens-raw-coordinates.csv"),
    ):
        rows = []
        for sample_index in range(2):
            for side in ("L", "R"):
                shape = _deformed_shape(0, sample_index, 0)
                rows.append(
                    {
                        "file": f"{prefix}-000{sample_index + 1}-synthetic-{side}.dw.png",
                        **_coordinate_columns(shape),
                    }
                )
        pd.DataFrame(rows).to_csv(directory / filename, index=False)
    pd.DataFrame(
        [
            {"file": "QX-0001-L.dw.png", "length": 9.5},
            {"file": "QX-0001-R.dw.png", "length": 9.6},
        ]
    ).to_csv(directory / "queens-wing-length.csv", index=False)
    pd.DataFrame([{"ind": "QX-0001", "weight": 140}]).to_csv(
        directory / "queens-weight.csv",
        index=False,
    )


def _write_synthetic_southwest_asia_csv(directory: Path) -> None:
    import pandas as pd

    for code in ("AZ", "CY", "GE", "IR", "IQ", "SA", "TJ", "TR"):
        rows = []
        metadata_rows = []
        for sample_index in range(1):
            for replicate in range(2):
                filename = f"{code}-000{sample_index + 1}-synthetic-{replicate}.dw.png"
                rows.append(
                    {
                        "file": filename,
                        **_coordinate_columns(_deformed_shape(replicate, 0, 0)),
                    }
                )
                metadata_rows.append(
                    {
                        "file": filename,
                        "sample": f"{code}-000{sample_index + 1}",
                        "latitude": 40.0 + replicate,
                        "longitude": 45.0 + replicate,
                        "date": 2025,
                        "resolution": 94488,
                        "notes": "synthetic",
                    }
                )
        pd.DataFrame(rows).to_csv(directory / f"{code}-raw-coordinates.csv", index=False)
        pd.DataFrame(metadata_rows).to_csv(directory / f"{code}-data.csv", index=False)
    pd.DataFrame(
        [{"file": "GE-0001-extra.dw.png", **_coordinate_columns(_base_shape())}]
    ).to_csv(directory / "GE-30-3x.csv", index=False)
    (directory / "_map.png").write_bytes(b"synthetic map")


def _write_synthetic_kazakhstan_csv(directory: Path) -> None:
    import pandas as pd

    rows = []
    metadata_rows = []
    for replicate in range(2):
        filename = f"KZ-0001-synthetic-{replicate}.dw.png"
        rows.append(
            {
                "file": filename,
                **_coordinate_columns(_deformed_shape(replicate, 0, 0)),
            }
        )
        metadata_rows.append(
            {
                "file": filename,
                "sample": "KZ-0001",
                "latitude": 49.5836,
                "longitude": 72.5732,
                "date": 2022,
                "resolution": 125984,
                "group": "carnica",
            }
        )
    pd.DataFrame(rows).to_csv(directory / "KZ-raw-coordinates.csv", index=False)
    pd.DataFrame(metadata_rows).to_csv(directory / "KZ-data.csv", index=False)


def _write_synthetic_serbia_csv(directory: Path) -> None:
    import pandas as pd

    rows = []
    metadata_rows = []
    for replicate in range(2):
        filename = f"RS-0021-01-synthetic-{replicate}-R.dw.png"
        rows.append(
            {
                "file": filename,
                **_coordinate_columns(_deformed_shape(replicate, 0, 0)),
            }
        )
        metadata_rows.append(
            {
                "file": filename,
                "sample": "RS-0021",
                " latitude ": 44.3574,
                " longitude ": 21.0863,
                "date": 2022,
                "resolution": 94488,
                "notes": "synthetic",
            }
        )
    pd.DataFrame(rows).to_csv(directory / "RS_21_80-raw-coordinates.csv", index=False)
    pd.DataFrame(metadata_rows).to_csv(directory / "RS_21_80-data.csv", index=False)
    (directory / "RS-map.png").write_bytes(b"synthetic serbia map")


def _write_synthetic_mexico_csv(directory: Path) -> None:
    import pandas as pd

    rows = []
    metadata_rows = []
    for replicate in range(2):
        filename = f"MX-0001-synthetic-{replicate}.dw.png"
        rows.append(
            {
                "file": filename,
                **_coordinate_columns(_deformed_shape(replicate, 0, 0)),
            }
        )
        metadata_rows.append(
            {
                "file": filename,
                "sample": "MX-0001",
                "latitude": 18.1465,
                "longitude": -92.7892,
                "date": 2021,
                "resolution": "",
                "notes": "synthetic",
            }
        )
    pd.DataFrame(rows).to_csv(directory / "MX-raw-coordinates.csv", index=False)
    pd.DataFrame(metadata_rows).to_csv(directory / "MX-data.csv", index=False)


def _write_synthetic_northwestern_europe_csv(directory: Path) -> None:
    import pandas as pd

    file_pairs = {
        "BY": ("BY-raw-coordinates.csv", "BY-data.csv", "Belarus", 53.9, 27.6),
        "DE": ("DE-raw-coordinates.csv", "DE-data.csv", "Germany", 51.1, 10.4),
        "ES": (
            "ES_517_573-raw-coordinates.csv",
            "ES_517_573-data.csv",
            "Spain",
            40.4,
            -3.7,
        ),
        "FR": ("FR-raw-coordinates.csv", "FR-data.csv", "France", 46.2, 2.2),
        "GB": ("GB-raw-coordinates.csv", "GB-data.csv", "United Kingdom", 54.0, -2.0),
        "IE": ("IE-raw-coordinates.csv", "IE-data.csv", "Ireland", 53.4, -8.2),
        "LT": ("LT-raw-coordinates.csv", "LT-data.csv", "Lithuania", 55.2, 23.9),
        "NL": ("NL-raw-coordinates.csv", "NL-data.csv", "Netherlands", 52.1, 5.3),
        "NO": ("NO-raw-coordinates.csv", "NO-data.csv", "Norway", 60.5, 8.5),
        "PL": (
            "PL_254_922-raw-coordinates.csv",
            "PL_254_922-data.csv",
            "Poland",
            52.0,
            19.1,
        ),
    }
    for index, (
        country_code,
        (raw_filename, data_filename, _country_name, latitude, longitude),
    ) in enumerate(file_pairs.items()):
        filename = f"{country_code}-0001-synthetic-{index}.dw.png"
        metadata_filename = filename
        if country_code == "DE":
            metadata_filename = filename.replace(".dw.png", "_0.dw.png")
        raw_rows = [
            {
                "file": filename,
                **_coordinate_columns(_deformed_shape(index, 0, 0)),
            }
        ]
        metadata_row = {
            "file": metadata_filename,
            "sample": f"{country_code}-0001",
            "date": 2025,
            "resolution": 125000,
            "notes": "synthetic northwestern Europe",
        }
        if country_code in {"DE", "ES", "PL"}:
            metadata_row[" latitude "] = latitude
            metadata_row[" longitude "] = longitude
        else:
            metadata_row["latitude"] = latitude
            metadata_row["longitude"] = longitude
        pd.DataFrame(raw_rows).to_csv(directory / raw_filename, index=False)
        pd.DataFrame([metadata_row]).to_csv(directory / data_filename, index=False)
    (directory / "_map.png").write_bytes(b"synthetic northwestern Europe map")


def _write_synthetic_algeria_csv(directory: Path) -> None:
    import pandas as pd

    rows = []
    metadata_rows = []
    for replicate, side in enumerate(("L", "R")):
        filename = f"DZ-0060-ALG-000629-{side}.dw.png"
        rows.append(
            {
                "file": filename,
                **_coordinate_columns(_deformed_shape(replicate, 0, 0)),
            }
        )
        metadata_rows.append(
            {
                "file": filename,
                "sample": "DZ-0060",
                "latitude": 36.736273,
                "longitude": 3.265224,
                "date": 2025,
                "resolution": 94488,
                "notes": "Mediterranean",
            }
        )
    pd.DataFrame(rows).to_csv(directory / "DZ-2025-raw-coordinates.csv", index=False)
    pd.DataFrame(metadata_rows).to_csv(directory / "DZ-2025-data.csv", index=False)


def _published_apis_template(
    db_session: Session,
    administrator: User,
) -> LandmarkTemplate:
    template = ensure_apis_19_template(db_session)
    template.status = TemplateStatus.PUBLISHED
    db_session.commit()
    db_session.refresh(template)
    return template


def test_analysis_activation_readiness_lists_inactive_prerequisites(
    db_session: Session,
    administrator: User,
) -> None:
    ready, missing = analysis_activation_readiness(db_session)

    assert ready is False
    assert "publish the Version 2 landmark template" in missing
    assert "build and activate the models" in missing

    _published_apis_template(db_session, administrator)
    ready_after_template, missing_after_template = analysis_activation_readiness(db_session)

    assert ready_after_template is False
    assert "publish the Version 2 landmark template" not in missing_after_template
    assert missing_after_template == ["build and activate the models"]


def test_oleksa_inspection_reports_optional_full_archive_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_dir = tmp_path / "oleksa"
    source_dir.mkdir()
    _write_synthetic_oleksa_csv(source_dir)
    (source_dir / "AT-raw-coordinates.csv").write_text(
        (source_dir / "EU-raw-coordinates.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (source_dir / "AT-data.csv").write_text("sample,country\n", encoding="utf-8")
    (source_dir / "AT-wing-images.zip").write_bytes(b"PK synthetic zip placeholder")
    (source_dir / "_sample-map.png").write_bytes(b"synthetic png placeholder")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(source_dir))
    get_settings.cache_clear()

    report = inspect_oleksa(get_settings())

    assert report["missing_files"] == []
    assert report["required_files"]["missing_count"] == 0
    assert report["optional_archive_files"]["present_count"] == 4
    assert report["optional_archive_files"]["missing_count"] > 0
    assert report["complete_country_archives_present"] is False
    assert report["country_coordinate_files_present"] == ["AT-raw-coordinates.csv"]
    assert report["country_image_archives_present"] == ["AT-wing-images.zip"]
    get_settings.cache_clear()


def test_nawrocka_import_merges_raw_wings_with_lineage_metadata(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    source_dir = tmp_path / "nawrocka"
    source_dir.mkdir()
    _write_synthetic_nawrocka_csv(source_dir)
    monkeypatch.setenv("WBR_NAWROCKA_REFERENCE_DIR", str(source_dir))
    get_settings.cache_clear()

    inspection = inspect_nawrocka(get_settings())
    imported = import_nawrocka(get_settings(), db_session)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    first_shape = next(
        shape
        for shape in shapes
        if shape.source_record_identifier == "A-ada-0698-01.dw.png"
    )
    first_metadata = json.loads(first_shape.source_metadata_json)
    assert inspection["missing_files"] == []
    assert inspection["optional_files"]["missing_count"] == 0
    assert "provenance only" in inspection["import_scope"]
    assert imported["dataset_code"] == "NAWROCKA_APIS_LINEAGE_2018"
    assert imported["imported_records"] == 8
    assert imported["samples"] == 4
    assert imported["lineages"] == ["A", "C", "M", "O"]
    assert imported["regions"] == ["Austria", "France", "Guinea", "Syria"]
    assert first_shape.source_sample_identifier == "A-ada-0698"
    assert first_shape.country_code is None
    assert first_shape.published_region == "Guinea"
    assert first_shape.published_lineage == "A"
    assert first_metadata["subspecies"] == "adansonii"
    assert first_metadata["reference_country"] == "Guinea"
    get_settings.cache_clear()


def test_kaur_india_coordinate_only_import_preserves_metadata(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    source_dir = tmp_path / "kaur-india"
    source_dir.mkdir()
    _write_synthetic_kaur_india_csv(source_dir)
    (source_dir / "IN-wing-images.zip").write_bytes(b"ignored image archive")
    monkeypatch.setenv("WBR_KAUR_INDIA_REFERENCE_DIR", str(source_dir))
    get_settings.cache_clear()

    inspection = inspect_kaur_india(get_settings())
    imported = import_kaur_india(get_settings(), db_session)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    assert inspection["missing_files"] == []
    assert inspection["ignored_image_archive"]["present"] is True
    assert imported["dataset_code"] == "KAUR_JAMMU_KASHMIR_APIS_2023"
    assert imported["imported_records"] == 4
    assert imported["countries"] == ["IN"]
    assert imported["regions"] == ["Jammu and Kashmir, India"]
    assert imported["samples"] == 2
    assert {shape.source_sample_identifier for shape in shapes} == {"IN-0001", "IN-0002"}
    assert all(shape.country_code == "IN" for shape in shapes)
    assert all(shape.published_region == "Jammu and Kashmir, India" for shape in shapes)
    assert "resolution" in json.loads(shapes[0].source_metadata_json)
    get_settings.cache_clear()


def test_southwest_asia_coordinate_only_import_is_worker_model_source(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    oleksa_dir = tmp_path / "oleksa"
    oleksa_dir.mkdir()
    _write_synthetic_oleksa_csv(oleksa_dir)
    source_dir = tmp_path / "southwest-asia"
    source_dir.mkdir()
    _write_synthetic_southwest_asia_csv(source_dir)
    (source_dir / "TR-wing-images.zip").write_bytes(b"ignored turkey images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(oleksa_dir))
    monkeypatch.setenv("WBR_SOUTHWEST_ASIA_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_southwest_asia(get_settings())
    oleksa_import = import_oleksa(get_settings(), db_session)
    imported = import_southwest_asia(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    assert inspection["missing_files"] == []
    assert inspection["optional_files"]["missing_count"] == 0
    assert any(item["name"] == "TR-wing-images.zip" and item["present"] for item in inspection["ignored_image_archives"])
    assert oleksa_import["imported_records"] == 16
    assert imported["dataset_code"] == "MACHLOWSKA_SW_ASIA_APIS_2025"
    assert imported["imported_records"] == 16
    assert imported["countries"] == ["AZ", "CY", "GE", "IQ", "IR", "SA", "TJ", "TR"]
    assert imported["regions"] == [
        "Azerbaijan",
        "Cyprus",
        "Georgia",
        "Iran",
        "Iraq",
        "Saudi Arabia",
        "Tajikistan",
        "Turkey",
    ]
    assert imported["samples"] == 8
    assert built["reference_wings"] == 32
    assert {shape.published_region for shape in shapes} >= {"Azerbaijan", "Turkey"}
    southwest_shape = next(
        shape
        for shape in shapes
        if shape.source_filename == "AZ-raw-coordinates.csv"
    )
    assert "resolution" in json.loads(southwest_shape.source_metadata_json)
    get_settings.cache_clear()


def test_kazakhstan_coordinate_only_import_is_worker_model_source(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    oleksa_dir = tmp_path / "oleksa"
    oleksa_dir.mkdir()
    _write_synthetic_oleksa_csv(oleksa_dir)
    source_dir = tmp_path / "kazakhstan"
    source_dir.mkdir()
    _write_synthetic_kazakhstan_csv(source_dir)
    (source_dir / "KZ-wing-images.zip").write_bytes(b"ignored kazakhstan images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(oleksa_dir))
    monkeypatch.setenv("WBR_KAZAKHSTAN_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_kazakhstan(get_settings())
    oleksa_import = import_oleksa(get_settings(), db_session)
    imported = import_kazakhstan(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    kazakhstan_shape = next(
        shape
        for shape in shapes
        if shape.source_filename == "KZ-raw-coordinates.csv"
    )
    kazakhstan_metadata = json.loads(kazakhstan_shape.source_metadata_json)
    assert inspection["missing_files"] == []
    assert inspection["ignored_image_archive"]["present"] is True
    assert oleksa_import["imported_records"] == 16
    assert imported["dataset_code"] == "TEMIRBAYEVA_KAZAKHSTAN_APIS_2023"
    assert imported["imported_records"] == 2
    assert imported["countries"] == ["KZ"]
    assert imported["regions"] == ["Kazakhstan"]
    assert imported["samples"] == 1
    assert built["reference_wings"] == 18
    assert kazakhstan_shape.country_code == "KZ"
    assert kazakhstan_shape.published_region == "Kazakhstan"
    assert kazakhstan_metadata["resolution"] == 125984
    assert kazakhstan_metadata["source_group"] == "carnica"
    get_settings.cache_clear()


def test_serbia_coordinate_only_import_is_worker_model_source(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    oleksa_dir = tmp_path / "oleksa"
    oleksa_dir.mkdir()
    _write_synthetic_oleksa_csv(oleksa_dir)
    source_dir = tmp_path / "serbia"
    source_dir.mkdir()
    _write_synthetic_serbia_csv(source_dir)
    (source_dir / "RS_21_80-wing-images.zip").write_bytes(b"ignored serbia images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(oleksa_dir))
    monkeypatch.setenv("WBR_SERBIA_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_serbia(get_settings())
    oleksa_import = import_oleksa(get_settings(), db_session)
    imported = import_serbia(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    serbia_shape = next(
        shape
        for shape in shapes
        if shape.source_filename == "RS_21_80-raw-coordinates.csv"
    )
    serbia_metadata = json.loads(serbia_shape.source_metadata_json)
    assert inspection["missing_files"] == []
    assert inspection["optional_files"]["missing_count"] == 0
    assert inspection["ignored_image_archive"]["present"] is True
    assert oleksa_import["imported_records"] == 16
    assert imported["dataset_code"] == "KAUR_SERBIA_APIS_2023"
    assert imported["imported_records"] == 2
    assert imported["countries"] == ["RS"]
    assert imported["regions"] == ["Serbia"]
    assert imported["samples"] == 1
    assert built["reference_wings"] == 18
    assert serbia_shape.country_code == "RS"
    assert serbia_shape.published_region == "Serbia"
    assert serbia_metadata["resolution"] == 94488
    assert serbia_metadata[" latitude "] == 44.3574
    get_settings.cache_clear()


def test_mexico_coordinate_only_import_is_worker_model_source(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    oleksa_dir = tmp_path / "oleksa"
    oleksa_dir.mkdir()
    _write_synthetic_oleksa_csv(oleksa_dir)
    source_dir = tmp_path / "mexico"
    source_dir.mkdir()
    _write_synthetic_mexico_csv(source_dir)
    (source_dir / "MX-wing-images.zip").write_bytes(b"ignored mexico images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(oleksa_dir))
    monkeypatch.setenv("WBR_MEXICO_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_mexico(get_settings())
    oleksa_import = import_oleksa(get_settings(), db_session)
    imported = import_mexico(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    mexico_shape = next(
        shape
        for shape in shapes
        if shape.source_filename == "MX-raw-coordinates.csv"
    )
    mexico_metadata = json.loads(mexico_shape.source_metadata_json)
    assert inspection["missing_files"] == []
    assert inspection["ignored_image_archive"]["present"] is True
    assert oleksa_import["imported_records"] == 16
    assert imported["dataset_code"] == "PAYRO_TABASCO_MEXICO_APIS_2024"
    assert imported["imported_records"] == 2
    assert imported["countries"] == ["MX"]
    assert imported["regions"] == ["Tabasco, Mexico"]
    assert imported["samples"] == 1
    assert built["reference_wings"] == 18
    assert mexico_shape.country_code == "MX"
    assert mexico_shape.published_region == "Tabasco, Mexico"
    assert mexico_metadata["date"] == 2021
    assert mexico_metadata["notes"] == "synthetic"
    get_settings.cache_clear()


def test_northwestern_europe_coordinate_only_import_is_worker_model_source(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    oleksa_dir = tmp_path / "oleksa"
    oleksa_dir.mkdir()
    _write_synthetic_oleksa_csv(oleksa_dir)
    source_dir = tmp_path / "northwestern-europe"
    source_dir.mkdir()
    _write_synthetic_northwestern_europe_csv(source_dir)
    (source_dir / "PL_254_922.zip").write_bytes(b"ignored northwestern Europe images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(oleksa_dir))
    monkeypatch.setenv("WBR_NORTHWESTERN_EUROPE_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_northwestern_europe(get_settings())
    oleksa_import = import_oleksa(get_settings(), db_session)
    imported = import_northwestern_europe(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    poland_shape = next(
        shape
        for shape in shapes
        if shape.source_filename == "PL_254_922-raw-coordinates.csv"
    )
    poland_metadata = json.loads(poland_shape.source_metadata_json)
    assert inspection["missing_files"] == []
    assert inspection["optional_files"]["missing_count"] == 0
    assert any(
        archive["name"] == "PL_254_922.zip" and archive["present"] is True
        for archive in inspection["ignored_image_archives"]
    )
    assert oleksa_import["imported_records"] == 16
    assert imported["dataset_code"] == "MACHLOWSKA_NORTHWESTERN_EUROPE_APIS_2026"
    assert imported["imported_records"] == 10
    assert imported["countries"] == ["BY", "DE", "ES", "FR", "GB", "IE", "LT", "NL", "NO", "PL"]
    assert imported["regions"] == [
        "Belarus",
        "France",
        "Germany",
        "Ireland",
        "Lithuania",
        "Netherlands",
        "Norway",
        "Poland",
        "Spain",
        "United Kingdom",
    ]
    assert imported["samples"] == 10
    assert built["reference_wings"] == 26
    assert poland_shape.country_code == "PL"
    assert poland_shape.published_region == "Poland"
    assert poland_metadata[" latitude "] == 52.0
    assert poland_metadata["notes"] == "synthetic northwestern Europe"
    get_settings.cache_clear()


def test_algeria_coordinate_only_import_is_worker_model_source(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    oleksa_dir = tmp_path / "oleksa"
    oleksa_dir.mkdir()
    _write_synthetic_oleksa_csv(oleksa_dir)
    source_dir = tmp_path / "algeria"
    source_dir.mkdir()
    _write_synthetic_algeria_csv(source_dir)
    (source_dir / "DZ-2025-wing-images.zip").write_bytes(b"ignored algeria images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(oleksa_dir))
    monkeypatch.setenv("WBR_ALGERIA_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_algeria(get_settings())
    oleksa_import = import_oleksa(get_settings(), db_session)
    imported = import_algeria(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    algeria_shape = next(
        shape
        for shape in shapes
        if shape.source_filename == "DZ-2025-raw-coordinates.csv"
    )
    algeria_metadata = json.loads(algeria_shape.source_metadata_json)
    assert inspection["missing_files"] == []
    assert inspection["ignored_image_archive"]["present"] is True
    assert oleksa_import["imported_records"] == 16
    assert imported["dataset_code"] == "YAMINA_ALGERIA_APIS_2026"
    assert imported["imported_records"] == 2
    assert imported["countries"] == ["DZ"]
    assert imported["regions"] == ["Algeria"]
    assert imported["samples"] == 1
    assert built["reference_wings"] == 18
    assert algeria_shape.country_code == "DZ"
    assert algeria_shape.published_region == "Algeria"
    assert algeria_metadata["resolution"] == 94488
    assert algeria_metadata["notes"] == "Mediterranean"
    get_settings.cache_clear()


def test_queens_drones_import_is_excluded_from_worker_model(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    worker_dir = tmp_path / "oleksa"
    worker_dir.mkdir()
    _write_synthetic_oleksa_csv(worker_dir)
    caste_dir = tmp_path / "queens-drones"
    caste_dir.mkdir()
    _write_synthetic_queens_drones_csv(caste_dir)
    (caste_dir / "drones-wing-images.zip").write_bytes(b"ignored drone images")
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(worker_dir))
    monkeypatch.setenv("WBR_QUEENS_DRONES_REFERENCE_DIR", str(caste_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    inspection = inspect_queens_drones(get_settings())
    worker_import = import_oleksa(get_settings(), db_session)
    caste_import = import_queens_drones(get_settings(), db_session)
    built = build_analysis_models(db_session, model_version=1)

    assert inspection["missing_files"] == []
    assert inspection["optional_metadata_files"]["missing_count"] == 0
    assert inspection["ignored_image_archives"][0]["present"] is True
    assert worker_import["imported_records"] == 16
    assert caste_import["dataset_code"] == "TOFILSKI_QUEENS_DRONES_APIS_2023"
    assert caste_import["imported_records"] == 8
    assert caste_import["analysis_inclusion"] == "excluded_from_worker_analysis_model"
    assert built["reference_wings"] == 16
    shapes = list(db_session.scalars(select(ExternalReferenceShape)).all())
    caste_metadata = [
        json.loads(shape.source_metadata_json)
        for shape in shapes
        if shape.source_filename in {"drones-raw-coordinates.csv", "queens-raw-coordinates.csv"}
    ]
    assert {metadata["caste"] for metadata in caste_metadata} == {"drone", "queen"}
    assert {metadata["sex"] for metadata in caste_metadata} == {"male", "female"}
    get_settings.cache_clear()


def _query_annotation(
    db_session: Session,
    student: User,
    administrator: User,
    template: LandmarkTemplate,
    image_store: LocalImageStore,
    image_bytes: bytes,
):
    assignment = Assignment(
        student_id=student.id,
        taxon_id=template.taxon_id,
        template_id=template.id,
        assigned_by_id=administrator.id,
    )
    db_session.add(assignment)
    db_session.commit()
    _specimen, image = create_specimen_with_image(
        db_session,
        student,
        image_store,
        specimen_code="APIS-MELLIFERA-QUERY",
        species_text="Apis mellifera worker",
        species_identification_method=SpeciesIdentificationMethod.DICHOTOMOUS_KEY,
        sex="worker",
        collection_date=date(2026, 1, 1),
        country="India",
        locality="Test locality",
        locality_sample_code="APIS-MELLIFERA-QUERY-LOC",
        locality_sample_size=15,
        locality_sample_number=1,
        collector_name="Test Collector",
        image_bytes=image_bytes,
        original_filename="query.png",
        assignment_id=assignment.id,
    )
    draft = create_draft_annotation(db_session, student, wing_image_id=image.id)
    for landmark, (x_value, y_value) in zip(template.landmarks, _base_shape() + 10, strict=True):
        place_annotation_point(
            db_session,
            student,
            annotation_id=draft.id,
            template_landmark_id=landmark.id,
            x_pixel=float(x_value),
            y_pixel=float(y_value),
        )
    return submit_annotation(db_session, student, annotation_id=draft.id)


def test_external_import_is_idempotent_and_quarantines_malformed_rows(
    db_session: Session,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _published_apis_template(db_session, administrator)
    source_dir = tmp_path / "oleksa"
    source_dir.mkdir()
    _write_synthetic_oleksa_csv(source_dir)
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(source_dir))
    get_settings.cache_clear()

    first = import_oleksa(get_settings(), db_session)
    second = import_oleksa(get_settings(), db_session)

    assert first["imported_records"] == 16
    assert first["rejected_records"] == 1
    assert second["duplicate_records"] == 16
    assert len(db_session.scalars(select(ExternalReferenceShape)).all()) == 16
    assert len(db_session.scalars(select(ExternalReferenceImportIssue)).all()) == 1
    get_settings.cache_clear()


def test_model_build_run_and_result_tables_are_reproducible(
    db_session: Session,
    student: User,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    template = _published_apis_template(db_session, administrator)
    source_dir = tmp_path / "oleksa"
    source_dir.mkdir()
    _write_synthetic_oleksa_csv(source_dir)
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(artifact_dir))
    get_settings.cache_clear()
    import_oleksa(get_settings(), db_session)

    built = build_analysis_models(db_session, model_version=1)
    activate_validated_models(db_session, model_version=1, template_id=template.id)
    annotation = _query_annotation(
        db_session,
        student,
        administrator,
        template,
        image_store,
        image_bytes,
    )
    run = run_published_apis_reference_analysis(
        db_session,
        student,
        annotation_id=annotation.id,
        nearest_limit=3,
    )

    assert built["model_version"] == 1
    assert run.model.model_version == 1
    assert sum(row.probability for row in run.region_probabilities) == pytest.approx(1.0)
    assert sum(row.probability for row in run.lineage_probabilities) == pytest.approx(1.0)
    assert {row.lineage_code for row in run.lineage_probabilities} == {"A", "C", "M", "O"}
    assert len(run.published_shape_matches) == 3
    assert _region_table(run).shape[1] == 5
    assert _lineage_table(run).shape[0] == 4
    assert _nearest_table(run).shape[0] == 3

    model = db_session.scalar(select(AnalysisModel).where(AnalysisModel.id == run.model_id))
    assert model is not None
    assert model.artifact_sha256 is not None
    artifact_path = artifact_dir / str(model.artifact_storage_key)
    artifact_path.write_bytes(artifact_path.read_bytes() + b"corrupt")
    with pytest.raises(ValidationError):
        run_published_apis_reference_analysis(
            db_session,
            student,
            annotation_id=annotation.id,
            nearest_limit=3,
        )
    get_settings.cache_clear()


def test_external_records_never_receive_wbr_accessions_and_native_accessions_remain(
    db_session: Session,
    student: User,
    reviewer: User,
    administrator: User,
    tmp_path: Path,
    monkeypatch,
    image_store: LocalImageStore,
    image_bytes: bytes,
) -> None:
    template = _published_apis_template(db_session, administrator)
    source_dir = tmp_path / "oleksa"
    source_dir.mkdir()
    _write_synthetic_oleksa_csv(source_dir)
    monkeypatch.setenv("WBR_OLEKSA_REFERENCE_DIR", str(source_dir))
    monkeypatch.setenv("WBR_ANALYSIS_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    import_oleksa(get_settings(), db_session)
    build_analysis_models(db_session, model_version=1)
    activate_validated_models(db_session, model_version=1, template_id=template.id)
    submitted = _query_annotation(
        db_session,
        student,
        administrator,
        template,
        image_store,
        image_bytes,
    )
    record = approve_annotation(db_session, reviewer, annotation_id=submitted.id)
    run = run_published_apis_reference_analysis(
        db_session,
        student,
        annotation_id=submitted.id,
        nearest_limit=1,
    )

    assert record.accession_number == "WBR-HYM-APIS-000001"
    assert db_session.scalar(select(RepositoryRecord)).accession_number == record.accession_number
    assert not hasattr(run.published_shape_matches[0].external_reference_shape, "accession_number")
    get_settings.cache_clear()
