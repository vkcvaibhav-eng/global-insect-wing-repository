"""CLI for published Apis external reference data and model artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wing_repository.analysis_services import (
    activate_validated_models,
    build_reference_payload,
    save_reference_payload_models,
)
from wing_repository.config import Settings, get_settings
from wing_repository.db import SessionLocal
from wing_repository.enums import Role
from wing_repository.errors import NotFoundError, ValidationError
from wing_repository.models import (
    AnalysisModel,
    ExternalReferenceDataset,
    ExternalReferenceImportIssue,
    ExternalReferenceShape,
    LandmarkTemplate,
    User,
)
from wing_repository.morphometrics.coordinate_io import (
    detect_coordinate_columns,
    inspect_csv_schema,
    parse_reference_row,
    row_identity_hash,
)
from wing_repository.morphometrics.provenance import file_sha256
from wing_repository.security import normalize_email
from wing_repository.template_loader import create_template, load_template_definition

APIS_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "demo_data"
    / "templates"
    / "apis_standard_19_v2.json"
)

OLEKSA_DATASET = {
    "dataset_code": "OLEKSA_EU_APIS_2022",
    "title": "Collection of wing images for conservation of honey bees (Apis mellifera) biodiversity in Europe",
    "authors": "Oleksa et al.",
    "publication_year": 2023,
    "dataset_doi": "10.5281/zenodo.7244070",
    "article_doi": "10.1093/gigascience/giad019",
    "workflow_doi": "10.48546/workflowhub.workflow.422.1",
    "version": "v2",
    "licence": "Other (Public Domain) as listed by Zenodo",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Europe",
}
NAWROCKA_DATASET = {
    "dataset_code": "NAWROCKA_APIS_LINEAGE_2018",
    "title": "Fore wings of honey bees (Apis mellifera): 19-landmark lineage reference coordinates",
    "authors": "Nawrocka, Kandemir, Fuchs and Tofilski",
    "publication_year": 2018,
    "dataset_doi": "10.5281/zenodo.7567336",
    "article_doi": "10.1007/s13592-017-0538-y",
    "workflow_doi": "10.48546/workflowhub.workflow.422.1",
    "version": "published Zenodo record",
    "licence": "See source dataset record",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "A, C, M and O evolutionary lineages",
}


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _configured_dir(value: Path | None, variable_name: str) -> Path:
    if value is None:
        raise ValidationError(f"{variable_name} is not configured.")
    if not value.exists() or not value.is_dir():
        raise ValidationError(f"{variable_name} must point to an existing directory.")
    return value


def _first_active_admin(session: Session) -> User:
    admin = session.scalar(
        select(User).where(User.role == Role.ADMINISTRATOR, User.is_active.is_(True)).order_by(User.id)
    )
    if admin is None:
        raise NotFoundError("Create an active administrator before importing templates.")
    return admin


def ensure_apis_19_template(session: Session, *, admin_email: str | None = None) -> LandmarkTemplate:
    """Create or return the draft v2 Apis 19-landmark template."""

    existing = session.scalar(
        select(LandmarkTemplate)
        .join(LandmarkTemplate.taxon)
        .where(
            LandmarkTemplate.version == 2,
            LandmarkTemplate.name == "Apis right forewing standard 19-landmark template",
        )
    )
    if existing is not None:
        return existing
    if admin_email:
        admin = session.scalar(
            select(User).where(User.email == normalize_email(admin_email), User.is_active.is_(True))
        )
        if admin is None:
            raise NotFoundError("Configured administrator email was not found.")
    else:
        admin = _first_active_admin(session)
    template = create_template(
        session,
        load_template_definition(APIS_TEMPLATE_PATH),
        created_by=admin,
    )
    session.commit()
    return template


def _ensure_dataset(
    session: Session,
    *,
    metadata: dict[str, Any],
    template_id: int,
    manifest: dict[str, Any],
) -> ExternalReferenceDataset:
    dataset = session.scalar(
        select(ExternalReferenceDataset).where(
            ExternalReferenceDataset.dataset_code == metadata["dataset_code"]
        )
    )
    manifest_json = json.dumps(manifest, sort_keys=True, default=str)
    if dataset is None:
        dataset = ExternalReferenceDataset(
            template_id=template_id,
            manifest_json=manifest_json,
            **metadata,
        )
        session.add(dataset)
        session.flush()
    else:
        dataset.template_id = template_id
        dataset.manifest_json = manifest_json
    return dataset


def _expected_files(directory: Path, names: tuple[str, ...]) -> list[Path]:
    return [directory / name for name in names if (directory / name).exists()]


def inspect_oleksa(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(settings.oleksa_reference_dir, "WBR_OLEKSA_REFERENCE_DIR")
    files = _expected_files(
        directory,
        (
            "EU-raw-coordinates.csv",
            "EU-geo-data.csv",
            "EU-lineage-classification.csv",
            "EU-aligned-coordinates.csv",
            "readme.txt",
        ),
    )
    reports = [
        inspect_csv_schema(path)
        for path in files
        if path.suffix.casefold() == ".csv"
    ]
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": [
            name
            for name in (
                "EU-raw-coordinates.csv",
                "EU-geo-data.csv",
                "EU-lineage-classification.csv",
                "EU-aligned-coordinates.csv",
                "readme.txt",
            )
            if not (directory / name).exists()
        ],
        "schema_reports": reports,
    }


def inspect_nawrocka(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(settings.nawrocka_reference_dir, "WBR_NAWROCKA_REFERENCE_DIR")
    csv_files = sorted(directory.glob("*.csv"))
    return {
        "source_dir": str(directory),
        "csv_files": [path.name for path in csv_files],
        "schema_reports": [inspect_csv_schema(path) for path in csv_files],
    }


def _import_coordinate_csv(
    session: Session,
    *,
    dataset: ExternalReferenceDataset,
    path: Path,
    fallback_country_code: str | None = None,
) -> dict[str, Any]:
    frame = pd.read_csv(path)
    layout = detect_coordinate_columns(frame)
    if len(layout.pairs) != 19:
        raise ValidationError(f"{path.name} does not contain 19 coordinate pairs.")
    counts = Counter()
    countries: set[str] = set()
    samples: set[str] = set()
    lineages: set[str] = set()
    regions: set[str] = set()
    for _, row in frame.iterrows():
        counts["total_records"] += 1
        row_hash = row_identity_hash(row)
        try:
            parsed = parse_reference_row(
                row,
                layout,
                source_filename=path.name,
                fallback_country_code=fallback_country_code,
            )
            existing = session.scalar(
                select(ExternalReferenceShape).where(
                    ExternalReferenceShape.external_dataset_id == dataset.id,
                    ExternalReferenceShape.source_row_hash == parsed.row_hash,
                )
            )
            existing_identifier = session.scalar(
                select(ExternalReferenceShape).where(
                    ExternalReferenceShape.external_dataset_id == dataset.id,
                    ExternalReferenceShape.source_record_identifier
                    == parsed.source_record_identifier,
                )
            )
            if existing is not None or existing_identifier is not None:
                counts["duplicate_records"] += 1
                continue
            shape = ExternalReferenceShape(
                external_dataset_id=dataset.id,
                source_record_identifier=parsed.source_record_identifier,
                source_filename=path.name,
                source_sample_identifier=parsed.source_sample_identifier,
                taxon_name="Apis mellifera",
                country_code=parsed.country_code,
                published_region=parsed.published_region or parsed.country_code,
                published_lineage=parsed.published_lineage,
                wing_type="forewing",
                original_side=parsed.original_side,
                coordinate_json=json.dumps(parsed.coordinates.tolist()),
                analytical_coordinate_json=json.dumps(parsed.coordinates.tolist()),
                coordinate_count=19,
                source_metadata_json=json.dumps(parsed.metadata, sort_keys=True, default=str),
                source_row_hash=parsed.row_hash,
            )
            session.add(shape)
            counts["imported_records"] += 1
            if shape.country_code:
                countries.add(shape.country_code)
            if shape.source_sample_identifier:
                samples.add(shape.source_sample_identifier)
            if shape.published_lineage:
                lineages.add(shape.published_lineage)
            if shape.published_region:
                regions.add(shape.published_region)
        except Exception as exc:
            issue = session.scalar(
                select(ExternalReferenceImportIssue).where(
                    ExternalReferenceImportIssue.external_dataset_id == dataset.id,
                    ExternalReferenceImportIssue.source_row_hash == row_hash,
                )
            )
            if issue is None:
                issue = ExternalReferenceImportIssue(
                    external_dataset_id=dataset.id,
                    source_filename=path.name,
                    source_row_identifier=str(row.name),
                    reason=str(exc),
                    raw_json=json.dumps(row.to_dict(), sort_keys=True, default=str),
                    source_row_hash=row_hash,
                )
                session.add(issue)
            counts["rejected_records"] += 1
            counts["coordinate_validation_failures"] += 1
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ValidationError("Import conflicted with existing external reference rows.")
    return {
        **counts,
        "countries": sorted(countries),
        "samples": len(samples),
        "lineages": sorted(lineages),
        "regions": sorted(regions),
        "source_file_sha256": file_sha256(path),
        "coordinate_detection_method": layout.detection_method,
    }


def import_oleksa(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(settings.oleksa_reference_dir, "WBR_OLEKSA_REFERENCE_DIR")
    path = directory / "EU-raw-coordinates.csv"
    if not path.exists():
        raise ValidationError("EU-raw-coordinates.csv is required for Oleksa import.")
    template = ensure_apis_19_template(session)
    manifest = inspect_oleksa(settings)
    manifest["source_file_sha256"] = file_sha256(path)
    dataset = _ensure_dataset(
        session,
        metadata=OLEKSA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_csv(session, dataset=dataset, path=path)
    return {"dataset_code": dataset.dataset_code, **summary}


def import_nawrocka(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.nawrocka_reference_dir,
        "WBR_NAWROCKA_REFERENCE_DIR",
    )
    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        raise ValidationError("At least one Nawrocka CSV file is required.")
    template = ensure_apis_19_template(session)
    manifest = inspect_nawrocka(settings)
    dataset = _ensure_dataset(
        session,
        metadata=NAWROCKA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summaries = [
        _import_coordinate_csv(session, dataset=dataset, path=path)
        for path in csv_files
    ]
    combined = Counter()
    for summary in summaries:
        combined.update(
            {
                key: value
                for key, value in summary.items()
                if isinstance(value, int)
            }
        )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [path.name for path in csv_files],
        **combined,
    }


def validate_import(session: Session) -> dict[str, Any]:
    return {
        "external_datasets": session.scalar(select(func.count()).select_from(ExternalReferenceDataset)),
        "external_shapes": session.scalar(select(func.count()).select_from(ExternalReferenceShape)),
        "quarantined_rows": session.scalar(select(func.count()).select_from(ExternalReferenceImportIssue)),
        "analysis_models": session.scalar(select(func.count()).select_from(AnalysisModel)),
    }


def build_analysis_models(session: Session, *, model_version: int | None = None) -> dict[str, Any]:
    template = session.scalar(
        select(LandmarkTemplate).where(
            LandmarkTemplate.name == "Apis right forewing standard 19-landmark template",
            LandmarkTemplate.version == 2,
        )
    )
    if template is None:
        raise NotFoundError("Import the Apis 19-landmark template first.")
    shapes = list(
        session.scalars(
            select(ExternalReferenceShape).order_by(ExternalReferenceShape.id)
        )
    )
    if not shapes:
        raise ValidationError("No external reference shapes have been imported.")
    version = model_version or (
        int(session.scalar(select(func.max(AnalysisModel.model_version))) or 0) + 1
    )
    coordinates = np.asarray([json.loads(shape.coordinate_json) for shape in shapes], dtype=float)
    payload = build_reference_payload(
        coordinates=coordinates,
        external_shape_ids=[shape.id for shape in shapes],
        sample_ids=[
            shape.source_sample_identifier or shape.source_record_identifier
            for shape in shapes
        ],
        region_labels=[shape.published_region for shape in shapes],
        lineage_labels=[shape.published_lineage for shape in shapes],
        source_hashes={
            shape.source_filename: shape.source_row_hash
            for shape in shapes
        },
    )
    models = save_reference_payload_models(
        session,
        template_id=template.id,
        payload=payload,
        artifact_root=get_settings().analysis_artifact_dir,
        model_version=version,
        source_dataset_ids=sorted({shape.external_dataset_id for shape in shapes}),
    )
    return {
        "model_version": version,
        "model_ids": [model.id for model in models],
        "status": "validated",
        "reference_wings": len(shapes),
        "reference_samples": len(payload["model_sample_ids"]),
    }


def activate_models(session: Session, *, model_version: int) -> dict[str, Any]:
    template = session.scalar(
        select(LandmarkTemplate).where(
            LandmarkTemplate.name == "Apis right forewing standard 19-landmark template",
            LandmarkTemplate.version == 2,
        )
    )
    if template is None:
        raise NotFoundError("The Apis 19-landmark template does not exist.")
    models = activate_validated_models(
        session,
        model_version=model_version,
        template_id=template.id,
    )
    return {
        "activated_model_version": model_version,
        "model_ids": [model.id for model in models],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect-oleksa")
    subparsers.add_parser("import-oleksa")
    subparsers.add_parser("inspect-nawrocka")
    subparsers.add_parser("import-nawrocka")
    subparsers.add_parser("validate-import")
    subparsers.add_parser("ensure-apis-template")
    build_parser = subparsers.add_parser("build-analysis-models")
    build_parser.add_argument("--model-version", type=int)
    activate_parser = subparsers.add_parser("activate-models")
    activate_parser.add_argument("--model-version", type=int, required=True)
    args = parser.parse_args(argv)
    settings = get_settings()
    with SessionLocal() as session:
        if args.command == "inspect-oleksa":
            _print_json(inspect_oleksa(settings))
        elif args.command == "import-oleksa":
            _print_json(import_oleksa(settings, session))
        elif args.command == "inspect-nawrocka":
            _print_json(inspect_nawrocka(settings))
        elif args.command == "import-nawrocka":
            _print_json(import_nawrocka(settings, session))
        elif args.command == "validate-import":
            _print_json(validate_import(session))
        elif args.command == "ensure-apis-template":
            template = ensure_apis_19_template(session)
            _print_json({"template_id": template.id, "status": template.status.value})
        elif args.command == "build-analysis-models":
            _print_json(build_analysis_models(session, model_version=args.model_version))
        elif args.command == "activate-models":
            _print_json(activate_models(session, model_version=args.model_version))


if __name__ == "__main__":
    main()
