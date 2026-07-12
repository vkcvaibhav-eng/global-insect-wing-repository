from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from wing_repository.analysis_services import activate_validated_models, run_published_apis_reference_analysis
from wing_repository.config import get_settings
from wing_repository.enums import TemplateStatus
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
from wing_repository.reference_data import build_analysis_models, ensure_apis_19_template, import_oleksa
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
