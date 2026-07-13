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
    / "repository_assets"
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
KAUR_INDIA_DATASET = {
    "dataset_code": "KAUR_JAMMU_KASHMIR_APIS_2023",
    "title": "Fore wings of honey bees (Apis mellifera) from Jammu and Kashmir, India",
    "authors": "Kaur, Ganie and Tofilski",
    "publication_year": 2023,
    "dataset_doi": "10.5281/zenodo.8071014",
    "article_doi": None,
    "workflow_doi": None,
    "version": "v2",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Jammu and Kashmir, India",
}
SOUTHWEST_ASIA_DATASET = {
    "dataset_code": "MACHLOWSKA_SW_ASIA_APIS_2025",
    "title": "Fore wings of honey bees (Apis mellifera) from southwestern Asia",
    "authors": "Machlowska, Kandemir, Koca, Kakhniashvili, Alattal, Alghamdi and Tofilski",
    "publication_year": 2025,
    "dataset_doi": "10.5281/zenodo.17075125",
    "article_doi": "10.1038/s41597-025-06234-8",
    "workflow_doi": "10.5281/zenodo.17077351",
    "version": "published Zenodo record",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Southwestern Asia",
}
KAZAKHSTAN_DATASET = {
    "dataset_code": "TEMIRBAYEVA_KAZAKHSTAN_APIS_2023",
    "title": "Fore wings of honey bees (Apis mellifera) from Kazakhstan",
    "authors": "Temirbayeva, Torekhanov, Nuralieva, Sheralieva and Tofilski",
    "publication_year": 2023,
    "dataset_doi": "10.5281/zenodo.8128010",
    "article_doi": "10.3390/life13091860",
    "workflow_doi": None,
    "version": "published Zenodo record",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Kazakhstan",
}
SERBIA_DATASET = {
    "dataset_code": "KAUR_SERBIA_APIS_2023",
    "title": "Fore wing images of honey bees (Apis mellifera) from Serbia",
    "authors": "Kaur, Nedic and Tofilski",
    "publication_year": 2023,
    "dataset_doi": "10.5281/zenodo.10389960",
    "article_doi": None,
    "workflow_doi": None,
    "version": "published Zenodo record",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Serbia",
}
MEXICO_DATASET = {
    "dataset_code": "PAYRO_TABASCO_MEXICO_APIS_2024",
    "title": "Fore wings of honey bees (Apis mellifera) from Tabasco, Mexico",
    "authors": "Payro de la Cruz, Valencia Dominguez, Ramos Reyes and Tofilski",
    "publication_year": 2024,
    "dataset_doi": "10.5281/zenodo.13884732",
    "article_doi": None,
    "workflow_doi": None,
    "version": "published Zenodo record",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker right forewings",
    "geographic_scope": "Tabasco, Mexico",
}
NORTHWESTERN_EUROPE_DATASET = {
    "dataset_code": "MACHLOWSKA_NORTHWESTERN_EUROPE_APIS_2026",
    "title": "Fore wings of honey bees (Apis mellifera) from northwestern Europe",
    "authors": (
        "Machlowska, Gerula, Oleksa, Kok, McCormack, Valentine, Kirkerud, "
        "Kryger, Blazyte-Cereskiene, Hasselmann, Hailu, Rutschmann and Tofilski"
    ),
    "publication_year": 2026,
    "dataset_doi": "10.5281/zenodo.18845767",
    "article_doi": None,
    "workflow_doi": None,
    "version": "v2",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Northwestern Europe",
}
ALGERIA_DATASET = {
    "dataset_code": "YAMINA_ALGERIA_APIS_2026",
    "title": "Fore wing images of honey bees (Apis mellifera) from Algeria 2025",
    "authors": "Yamina and Tofilski",
    "publication_year": 2026,
    "dataset_doi": "10.5281/zenodo.18360081",
    "article_doi": None,
    "workflow_doi": None,
    "version": "v1",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera worker forewings",
    "geographic_scope": "Algeria",
}
QUEENS_DRONES_DATASET = {
    "dataset_code": "TOFILSKI_QUEENS_DRONES_APIS_2023",
    "title": "Fore wings of queens and drones of honey bees (Apis mellifera)",
    "authors": "Tofilski, Kaur and Łopuch",
    "publication_year": 2023,
    "dataset_doi": "10.5281/zenodo.8396176",
    "article_doi": None,
    "workflow_doi": None,
    "version": "published Zenodo record",
    "licence": "ODC Open Database License v1.0",
    "taxonomic_scope": "Apis mellifera queen and drone forewings",
    "geographic_scope": None,
}
APIS_WORKER_ANALYSIS_DATASET_CODES = {
    OLEKSA_DATASET["dataset_code"],
    NAWROCKA_DATASET["dataset_code"],
    KAUR_INDIA_DATASET["dataset_code"],
    SOUTHWEST_ASIA_DATASET["dataset_code"],
    KAZAKHSTAN_DATASET["dataset_code"],
    SERBIA_DATASET["dataset_code"],
    MEXICO_DATASET["dataset_code"],
    NORTHWESTERN_EUROPE_DATASET["dataset_code"],
    ALGERIA_DATASET["dataset_code"],
}

OLEKSA_COUNTRY_CODES = (
    "AT",
    "ES",
    "GR",
    "HR",
    "HU",
    "MD",
    "ME",
    "PL",
    "PT",
    "RO",
    "RS",
    "SI",
    "TR",
)
OLEKSA_REQUIRED_FILES = (
    "EU-raw-coordinates.csv",
    "EU-geo-data.csv",
    "EU-lineage-classification.csv",
    "EU-aligned-coordinates.csv",
    "readme.txt",
)
OLEKSA_COUNTRY_DATA_FILES = tuple(
    filename
    for country_code in OLEKSA_COUNTRY_CODES
    for filename in (
        f"{country_code}-raw-coordinates.csv",
        f"{country_code}-data.csv",
    )
)
OLEKSA_IMAGE_ARCHIVE_FILES = tuple(
    f"{country_code}-wing-images.zip"
    for country_code in OLEKSA_COUNTRY_CODES
)
OLEKSA_OPTIONAL_ARCHIVE_FILES = (
    *OLEKSA_COUNTRY_DATA_FILES,
    *OLEKSA_IMAGE_ARCHIVE_FILES,
    "_sample-map.png",
)
NAWROCKA_REQUIRED_FILES = (
    "Nawrocka_et_al2018.csv",
    "Nawrocka_et_al2018-geo-data.csv",
)
NAWROCKA_OPTIONAL_FILES = (
    "Nawrocka_et_al2018-sample-aligned.csv",
    "apis-wing-landmarks600.png",
)
KAUR_INDIA_REQUIRED_FILES = (
    "IN-raw-coordinates.csv",
    "IN-data.csv",
)
KAUR_INDIA_IGNORED_IMAGE_ARCHIVE = "IN-wing-images.zip"
SOUTHWEST_ASIA_COUNTRY_NAMES = {
    "AZ": "Azerbaijan",
    "CY": "Cyprus",
    "GE": "Georgia",
    "IR": "Iran",
    "IQ": "Iraq",
    "SA": "Saudi Arabia",
    "TJ": "Tajikistan",
    "TR": "Turkey",
}
SOUTHWEST_ASIA_COUNTRY_CODES = tuple(SOUTHWEST_ASIA_COUNTRY_NAMES)
SOUTHWEST_ASIA_REQUIRED_FILES = tuple(
    filename
    for country_code in SOUTHWEST_ASIA_COUNTRY_CODES
    for filename in (
        f"{country_code}-raw-coordinates.csv",
        f"{country_code}-data.csv",
    )
)
SOUTHWEST_ASIA_OPTIONAL_FILES = (
    "GE-30-3x.csv",
    "_map.png",
)
SOUTHWEST_ASIA_IGNORED_IMAGE_ARCHIVES = tuple(
    f"{country_code}-wing-images.zip"
    for country_code in SOUTHWEST_ASIA_COUNTRY_CODES
)
KAZAKHSTAN_REQUIRED_FILES = (
    "KZ-raw-coordinates.csv",
    "KZ-data.csv",
)
KAZAKHSTAN_IGNORED_IMAGE_ARCHIVE = "KZ-wing-images.zip"
SERBIA_REQUIRED_FILES = (
    "RS_21_80-raw-coordinates.csv",
    "RS_21_80-data.csv",
)
SERBIA_OPTIONAL_FILES = (
    "RS-map.png",
)
SERBIA_IGNORED_IMAGE_ARCHIVE = "RS_21_80-wing-images.zip"
MEXICO_REQUIRED_FILES = (
    "MX-raw-coordinates.csv",
    "MX-data.csv",
)
MEXICO_IGNORED_IMAGE_ARCHIVE = "MX-wing-images.zip"
NORTHWESTERN_EUROPE_COUNTRY_FILES = {
    "BY": ("Belarus", "BY-raw-coordinates.csv", "BY-data.csv", "BY.zip"),
    "DE": ("Germany", "DE-raw-coordinates.csv", "DE-data.csv", "DE.zip"),
    "ES": (
        "Spain",
        "ES_517_573-raw-coordinates.csv",
        "ES_517_573-data.csv",
        "ES_517_573.zip",
    ),
    "FR": ("France", "FR-raw-coordinates.csv", "FR-data.csv", "FR.zip"),
    "GB": ("United Kingdom", "GB-raw-coordinates.csv", "GB-data.csv", "GB.zip"),
    "IE": ("Ireland", "IE-raw-coordinates.csv", "IE-data.csv", "IE.zip"),
    "LT": ("Lithuania", "LT-raw-coordinates.csv", "LT-data.csv", "LT.zip"),
    "NL": ("Netherlands", "NL-raw-coordinates.csv", "NL-data.csv", "NL.zip"),
    "NO": ("Norway", "NO-raw-coordinates.csv", "NO-data.csv", "NO.zip"),
    "PL": (
        "Poland",
        "PL_254_922-raw-coordinates.csv",
        "PL_254_922-data.csv",
        "PL_254_922.zip",
    ),
}
NORTHWESTERN_EUROPE_COUNTRY_CODES = tuple(NORTHWESTERN_EUROPE_COUNTRY_FILES)
NORTHWESTERN_EUROPE_REQUIRED_FILES = tuple(
    filename
    for _, raw_filename, data_filename, _ in NORTHWESTERN_EUROPE_COUNTRY_FILES.values()
    for filename in (raw_filename, data_filename)
)
NORTHWESTERN_EUROPE_OPTIONAL_FILES = ("_map.png",)
NORTHWESTERN_EUROPE_IGNORED_IMAGE_ARCHIVES = tuple(
    archive_filename
    for _, _, _, archive_filename in NORTHWESTERN_EUROPE_COUNTRY_FILES.values()
)
ALGERIA_REQUIRED_FILES = (
    "DZ-2025-raw-coordinates.csv",
    "DZ-2025-data.csv",
)
ALGERIA_IGNORED_IMAGE_ARCHIVE = "DZ-2025-wing-images.zip"
QUEENS_DRONES_REQUIRED_FILES = (
    "drones-raw-coordinates.csv",
    "queens-raw-coordinates.csv",
)
QUEENS_DRONES_OPTIONAL_METADATA_FILES = (
    "queens-wing-length.csv",
    "queens-weight.csv",
)
QUEENS_DRONES_IGNORED_IMAGE_ARCHIVES = (
    "drones-wing-images.zip",
    "queens-wing-images.zip",
)


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
    """Create or return the bundled published Apis 19-landmark template."""

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


def _file_inventory(directory: Path, names: tuple[str, ...]) -> dict[str, Any]:
    present: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in names:
        path = directory / name
        if path.exists():
            present.append({"name": name, "bytes": path.stat().st_size})
        else:
            missing.append(name)
    return {
        "present": present,
        "missing": missing,
        "present_count": len(present),
        "missing_count": len(missing),
    }


def _sample_id_from_wing_filename(filename: str) -> str | None:
    stem = Path(str(filename)).stem
    if stem.endswith(".dw"):
        stem = stem.removesuffix(".dw")
    for suffix in ("-L", "-R"):
        if stem.endswith(suffix):
            return stem.removesuffix(suffix)
    return stem or None


def _side_from_wing_filename(filename: str) -> str | None:
    stem = Path(str(filename)).stem
    if stem.endswith(".dw"):
        stem = stem.removesuffix(".dw")
    if stem.endswith("-L"):
        return "L"
    if stem.endswith("-R"):
        return "R"
    return None


def inspect_oleksa(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(settings.oleksa_reference_dir, "WBR_OLEKSA_REFERENCE_DIR")
    files = _expected_files(directory, OLEKSA_REQUIRED_FILES)
    required_inventory = _file_inventory(directory, OLEKSA_REQUIRED_FILES)
    optional_archive_inventory = _file_inventory(directory, OLEKSA_OPTIONAL_ARCHIVE_FILES)
    reports = [
        inspect_csv_schema(path)
        for path in files
        if path.suffix.casefold() == ".csv"
    ]
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "optional_archive_files": optional_archive_inventory,
        "complete_country_archives_present": optional_archive_inventory["missing_count"] == 0,
        "country_codes": list(OLEKSA_COUNTRY_CODES),
        "country_coordinate_files_present": [
            item["name"]
            for item in optional_archive_inventory["present"]
            if item["name"].endswith("-raw-coordinates.csv")
        ],
        "country_image_archives_present": [
            item["name"]
            for item in optional_archive_inventory["present"]
            if item["name"].endswith("-wing-images.zip")
        ],
        "schema_reports": reports,
    }


def inspect_nawrocka(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(settings.nawrocka_reference_dir, "WBR_NAWROCKA_REFERENCE_DIR")
    required_inventory = _file_inventory(directory, NAWROCKA_REQUIRED_FILES)
    optional_inventory = _file_inventory(directory, NAWROCKA_OPTIONAL_FILES)
    files = _expected_files(directory, (*NAWROCKA_REQUIRED_FILES, *NAWROCKA_OPTIONAL_FILES))
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "optional_files": optional_inventory,
        "import_scope": (
            "Nawrocka_et_al2018.csv is imported after merging sample lineage "
            "metadata from Nawrocka_et_al2018-geo-data.csv. The sample-aligned "
            "CSV and landmark PNG are retained for provenance only."
        ),
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_kaur_india(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.kaur_india_reference_dir,
        "WBR_KAUR_INDIA_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, KAUR_INDIA_REQUIRED_FILES)
    files = _expected_files(directory, KAUR_INDIA_REQUIRED_FILES)
    image_archive = directory / KAUR_INDIA_IGNORED_IMAGE_ARCHIVE
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "ignored_image_archive": {
            "name": KAUR_INDIA_IGNORED_IMAGE_ARCHIVE,
            "present": image_archive.exists(),
            "bytes": image_archive.stat().st_size if image_archive.exists() else 0,
            "reason": "Coordinate-only import; original images are not imported.",
        },
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_southwest_asia(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.southwest_asia_reference_dir,
        "WBR_SOUTHWEST_ASIA_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, SOUTHWEST_ASIA_REQUIRED_FILES)
    optional_inventory = _file_inventory(directory, SOUTHWEST_ASIA_OPTIONAL_FILES)
    files = _expected_files(
        directory,
        (*SOUTHWEST_ASIA_REQUIRED_FILES, *SOUTHWEST_ASIA_OPTIONAL_FILES),
    )
    ignored_archives = []
    for name in SOUTHWEST_ASIA_IGNORED_IMAGE_ARCHIVES:
        path = directory / name
        ignored_archives.append(
            {
                "name": name,
                "present": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "reason": "Coordinate-only import; original images are not imported.",
            }
        )
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "optional_files": optional_inventory,
        "ignored_image_archives": ignored_archives,
        "country_codes": list(SOUTHWEST_ASIA_COUNTRY_CODES),
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_kazakhstan(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.kazakhstan_reference_dir,
        "WBR_KAZAKHSTAN_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, KAZAKHSTAN_REQUIRED_FILES)
    files = _expected_files(directory, KAZAKHSTAN_REQUIRED_FILES)
    image_archive = directory / KAZAKHSTAN_IGNORED_IMAGE_ARCHIVE
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "ignored_image_archive": {
            "name": KAZAKHSTAN_IGNORED_IMAGE_ARCHIVE,
            "present": image_archive.exists(),
            "bytes": image_archive.stat().st_size if image_archive.exists() else 0,
            "reason": "Coordinate-only import; original images are not imported.",
        },
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_serbia(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.serbia_reference_dir,
        "WBR_SERBIA_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, SERBIA_REQUIRED_FILES)
    optional_inventory = _file_inventory(directory, SERBIA_OPTIONAL_FILES)
    files = _expected_files(directory, (*SERBIA_REQUIRED_FILES, *SERBIA_OPTIONAL_FILES))
    image_archive = directory / SERBIA_IGNORED_IMAGE_ARCHIVE
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "optional_files": optional_inventory,
        "ignored_image_archive": {
            "name": SERBIA_IGNORED_IMAGE_ARCHIVE,
            "present": image_archive.exists(),
            "bytes": image_archive.stat().st_size if image_archive.exists() else 0,
            "reason": "Coordinate-only import; original images are not imported.",
        },
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_mexico(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.mexico_reference_dir,
        "WBR_MEXICO_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, MEXICO_REQUIRED_FILES)
    files = _expected_files(directory, MEXICO_REQUIRED_FILES)
    image_archive = directory / MEXICO_IGNORED_IMAGE_ARCHIVE
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "ignored_image_archive": {
            "name": MEXICO_IGNORED_IMAGE_ARCHIVE,
            "present": image_archive.exists(),
            "bytes": image_archive.stat().st_size if image_archive.exists() else 0,
            "reason": "Coordinate-only import; original images are not imported.",
        },
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_northwestern_europe(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.northwestern_europe_reference_dir,
        "WBR_NORTHWESTERN_EUROPE_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, NORTHWESTERN_EUROPE_REQUIRED_FILES)
    optional_inventory = _file_inventory(directory, NORTHWESTERN_EUROPE_OPTIONAL_FILES)
    files = _expected_files(
        directory,
        (*NORTHWESTERN_EUROPE_REQUIRED_FILES, *NORTHWESTERN_EUROPE_OPTIONAL_FILES),
    )
    ignored_archives = []
    for name in NORTHWESTERN_EUROPE_IGNORED_IMAGE_ARCHIVES:
        path = directory / name
        ignored_archives.append(
            {
                "name": name,
                "present": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "reason": "Coordinate-only import; original images are not imported.",
            }
        )
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "optional_files": optional_inventory,
        "ignored_image_archives": ignored_archives,
        "country_codes": list(NORTHWESTERN_EUROPE_COUNTRY_CODES),
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_algeria(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.algeria_reference_dir,
        "WBR_ALGERIA_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, ALGERIA_REQUIRED_FILES)
    files = _expected_files(directory, ALGERIA_REQUIRED_FILES)
    image_archive = directory / ALGERIA_IGNORED_IMAGE_ARCHIVE
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "ignored_image_archive": {
            "name": ALGERIA_IGNORED_IMAGE_ARCHIVE,
            "present": image_archive.exists(),
            "bytes": image_archive.stat().st_size if image_archive.exists() else 0,
            "reason": "Coordinate-only import; original images are not imported.",
        },
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def inspect_queens_drones(settings: Settings) -> dict[str, Any]:
    directory = _configured_dir(
        settings.queens_drones_reference_dir,
        "WBR_QUEENS_DRONES_REFERENCE_DIR",
    )
    required_inventory = _file_inventory(directory, QUEENS_DRONES_REQUIRED_FILES)
    optional_metadata_inventory = _file_inventory(
        directory,
        QUEENS_DRONES_OPTIONAL_METADATA_FILES,
    )
    files = _expected_files(
        directory,
        (*QUEENS_DRONES_REQUIRED_FILES, *QUEENS_DRONES_OPTIONAL_METADATA_FILES),
    )
    ignored_archives = []
    for name in QUEENS_DRONES_IGNORED_IMAGE_ARCHIVES:
        path = directory / name
        ignored_archives.append(
            {
                "name": name,
                "present": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
                "reason": "Coordinate-only import; original images are not imported.",
            }
        )
    return {
        "source_dir": str(directory),
        "present_files": [path.name for path in files],
        "missing_files": required_inventory["missing"],
        "required_files": required_inventory,
        "optional_metadata_files": optional_metadata_inventory,
        "ignored_image_archives": ignored_archives,
        "schema_reports": [
            inspect_csv_schema(path)
            for path in files
            if path.suffix.casefold() == ".csv"
        ],
    }


def _import_coordinate_frame(
    session: Session,
    *,
    dataset: ExternalReferenceDataset,
    frame: pd.DataFrame,
    source_filename: str,
    source_file_for_hash: Path,
    fallback_country_code: str | None = None,
) -> dict[str, Any]:
    layout = detect_coordinate_columns(frame)
    if len(layout.pairs) != 19:
        raise ValidationError(f"{source_filename} does not contain 19 coordinate pairs.")
    counts = Counter()
    countries: set[str] = set()
    samples: set[str] = set()
    lineages: set[str] = set()
    regions: set[str] = set()
    existing_hashes = set(
        session.scalars(
            select(ExternalReferenceShape.source_row_hash).where(
                ExternalReferenceShape.external_dataset_id == dataset.id
            )
        )
    )
    existing_identifiers = set(
        session.scalars(
            select(ExternalReferenceShape.source_record_identifier).where(
                ExternalReferenceShape.external_dataset_id == dataset.id
            )
        )
    )
    for _, row in frame.iterrows():
        counts["total_records"] += 1
        row_hash = row_identity_hash(row)
        try:
            parsed = parse_reference_row(
                row,
                layout,
                source_filename=source_filename,
                fallback_country_code=fallback_country_code,
            )
            if (
                parsed.row_hash in existing_hashes
                or parsed.source_record_identifier in existing_identifiers
            ):
                counts["duplicate_records"] += 1
                continue
            existing_hashes.add(parsed.row_hash)
            existing_identifiers.add(parsed.source_record_identifier)
            shape = ExternalReferenceShape(
                external_dataset_id=dataset.id,
                source_record_identifier=parsed.source_record_identifier,
                source_filename=source_filename,
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
                    source_filename=source_filename,
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
        "source_file_sha256": file_sha256(source_file_for_hash),
        "coordinate_detection_method": layout.detection_method,
    }


def _import_coordinate_csv(
    session: Session,
    *,
    dataset: ExternalReferenceDataset,
    path: Path,
    fallback_country_code: str | None = None,
) -> dict[str, Any]:
    return _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=pd.read_csv(path),
        source_filename=path.name,
        source_file_for_hash=path,
        fallback_country_code=fallback_country_code,
    )


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
    raw_path = directory / "Nawrocka_et_al2018.csv"
    geo_path = directory / "Nawrocka_et_al2018-geo-data.csv"
    missing = [path.name for path in (raw_path, geo_path) if not path.exists()]
    if missing:
        raise ValidationError(
            f"Missing required Nawrocka files: {', '.join(missing)}."
        )
    raw_frame = pd.read_csv(raw_path)
    geo_frame = pd.read_csv(geo_path)
    if "file" not in raw_frame.columns or "sample" not in geo_frame.columns:
        raise ValidationError(
            "Nawrocka raw coordinates must contain file and geo-data must contain sample."
        )
    raw_frame = raw_frame.copy()
    geo_frame = geo_frame.copy()
    raw_frame["sample"] = raw_frame["file"].map(_nawrocka_sample_from_filename)
    if "country" in geo_frame.columns:
        geo_frame["reference_country"] = geo_frame["country"]
        geo_frame["region"] = geo_frame["country"]
        geo_frame = geo_frame.drop(columns=["country"])
    if geo_frame["sample"].duplicated().any():
        raise ValidationError("Nawrocka geo-data contains duplicate sample identifiers.")
    merged = raw_frame.merge(
        geo_frame,
        on="sample",
        how="left",
        validate="many_to_one",
        suffixes=("", "_metadata"),
    )
    template = ensure_apis_19_template(session)
    manifest = inspect_nawrocka(settings)
    manifest["source_file_sha256"] = file_sha256(raw_path)
    manifest["metadata_file_sha256"] = file_sha256(geo_path)
    for optional_name in NAWROCKA_OPTIONAL_FILES:
        optional_path = directory / optional_name
        if optional_path.exists():
            manifest.setdefault("optional_file_sha256", {})[optional_name] = file_sha256(optional_path)
    dataset = _ensure_dataset(
        session,
        metadata=NAWROCKA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=merged,
        source_filename=raw_path.name,
        source_file_for_hash=raw_path,
    )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [raw_path.name, geo_path.name],
        **summary,
    }


def _nawrocka_sample_from_filename(filename: object) -> str:
    stem = Path(str(filename)).stem
    if stem.endswith(".dw"):
        stem = stem.removesuffix(".dw")
    parts = stem.split("-")
    if len(parts) > 1 and parts[-1].isdigit():
        return "-".join(parts[:-1])
    return stem


def import_kaur_india(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.kaur_india_reference_dir,
        "WBR_KAUR_INDIA_REFERENCE_DIR",
    )
    raw_path = directory / "IN-raw-coordinates.csv"
    data_path = directory / "IN-data.csv"
    missing = [path.name for path in (raw_path, data_path) if not path.exists()]
    if missing:
        raise ValidationError(f"Missing required Kaur India files: {', '.join(missing)}.")
    raw_frame = pd.read_csv(raw_path)
    data_frame = pd.read_csv(data_path)
    if "file" not in raw_frame.columns or "file" not in data_frame.columns:
        raise ValidationError("Kaur India coordinate and metadata files must contain a file column.")
    merged = raw_frame.merge(
        data_frame,
        on="file",
        how="left",
        validate="one_to_one",
        suffixes=("", "_metadata"),
    )
    merged["country"] = "IN"
    merged["region"] = "Jammu and Kashmir, India"
    template = ensure_apis_19_template(session)
    manifest = inspect_kaur_india(settings)
    manifest["source_file_sha256"] = file_sha256(raw_path)
    manifest["metadata_file_sha256"] = file_sha256(data_path)
    dataset = _ensure_dataset(
        session,
        metadata=KAUR_INDIA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=merged,
        source_filename=raw_path.name,
        source_file_for_hash=raw_path,
        fallback_country_code="IN",
    )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [raw_path.name, data_path.name],
        **summary,
    }


def _merge_coordinate_metadata(
    *,
    raw_path: Path,
    data_path: Path,
    country_code: str,
    region_label: str,
    dataset_label: str,
    normalize_file_aliases: bool = False,
) -> pd.DataFrame:
    raw_frame = pd.read_csv(raw_path)
    data_frame = pd.read_csv(data_path)
    if "file" not in raw_frame.columns or "file" not in data_frame.columns:
        raise ValidationError(
            f"{dataset_label} coordinate and metadata files must contain a file column."
        )
    if "group" in data_frame.columns and "source_group" not in data_frame.columns:
        data_frame = data_frame.copy()
        data_frame["source_group"] = data_frame["group"]
    if normalize_file_aliases:
        raw_frame = raw_frame.copy()
        data_frame = data_frame.copy()
        merge_status = "__wbr_merge_status"
        merged = raw_frame.merge(
            data_frame,
            on="file",
            how="left",
            validate="one_to_one",
            suffixes=("", "_metadata"),
            indicator=merge_status,
        )
        unmatched_mask = merged[merge_status] == "left_only"
        if unmatched_mask.any():
            merge_key = "__wbr_file_merge_key"
            metadata_columns = [column for column in data_frame.columns if column != "file"]
            raw_alias_frame = raw_frame.loc[unmatched_mask, ["file"]].copy()
            raw_alias_frame[merge_key] = raw_alias_frame["file"].map(_reference_file_merge_key)
            data_alias_frame = data_frame.copy()
            data_alias_frame[merge_key] = data_alias_frame["file"].map(
                _reference_file_merge_key
            )
            data_alias_frame = data_alias_frame.drop_duplicates(
                subset=[merge_key],
                keep="first",
            )
            alias_merged = raw_alias_frame.merge(
                data_alias_frame,
                on=merge_key,
                how="left",
                validate="many_to_one",
                suffixes=("", "_metadata"),
            )
            for column in metadata_columns:
                if column in alias_merged.columns:
                    merged.loc[unmatched_mask, column] = list(alias_merged[column])
            if "file_metadata" in alias_merged.columns:
                merged.loc[unmatched_mask, "file_metadata"] = list(
                    alias_merged["file_metadata"]
                )
        merged = merged.drop(columns=[merge_status])
    else:
        merged = raw_frame.merge(
            data_frame,
            on="file",
            how="left",
            validate="one_to_one",
            suffixes=("", "_metadata"),
        )
    merged["country"] = country_code
    merged["region"] = region_label
    return merged


def _reference_file_merge_key(value: object) -> str:
    """Normalize known source filename aliases for metadata joins."""

    key = str(value).strip()
    for suffix in (".dw.png", ".png"):
        alias_suffix = f"_0{suffix}"
        if key.endswith(alias_suffix):
            return f"{key.removesuffix(alias_suffix)}{suffix}"
    return key


def import_southwest_asia(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.southwest_asia_reference_dir,
        "WBR_SOUTHWEST_ASIA_REFERENCE_DIR",
    )
    missing = [
        name
        for name in SOUTHWEST_ASIA_REQUIRED_FILES
        if not (directory / name).exists()
    ]
    if missing:
        raise ValidationError(
            f"Missing required Southwest Asia files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_southwest_asia(settings)
    manifest["source_file_sha256"] = {
        path.name: file_sha256(path)
        for path in _expected_files(
            directory,
            (*SOUTHWEST_ASIA_REQUIRED_FILES, *SOUTHWEST_ASIA_OPTIONAL_FILES),
        )
    }
    manifest["analysis_scope_note"] = (
        "Country raw-coordinate files are imported after merging their matching "
        "country data CSV. GE-30-3x.csv is retained for provenance and not "
        "imported by default."
    )
    dataset = _ensure_dataset(
        session,
        metadata=SOUTHWEST_ASIA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summaries = []
    for country_code, country_name in SOUTHWEST_ASIA_COUNTRY_NAMES.items():
        raw_path = directory / f"{country_code}-raw-coordinates.csv"
        data_path = directory / f"{country_code}-data.csv"
        summaries.append(
            _import_coordinate_frame(
                session,
                dataset=dataset,
                frame=_merge_coordinate_metadata(
                    raw_path=raw_path,
                    data_path=data_path,
                    country_code=country_code,
                    region_label=country_name,
                    dataset_label="Southwest Asia",
                ),
                source_filename=raw_path.name,
                source_file_for_hash=raw_path,
                fallback_country_code=country_code,
            )
        )
    combined = Counter()
    countries: set[str] = set()
    samples = 0
    lineages: set[str] = set()
    regions: set[str] = set()
    for summary in summaries:
        combined.update(
            {
                key: value
                for key, value in summary.items()
                if isinstance(value, int)
            }
        )
        countries.update(summary.get("countries", []))
        samples += int(summary.get("samples", 0))
        lineages.update(summary.get("lineages", []))
        regions.update(summary.get("regions", []))
    return {
        "dataset_code": dataset.dataset_code,
        "files": [
            filename
            for country_code in SOUTHWEST_ASIA_COUNTRY_CODES
            for filename in (
                f"{country_code}-raw-coordinates.csv",
                f"{country_code}-data.csv",
            )
        ],
        **combined,
        "countries": sorted(countries),
        "samples": samples,
        "lineages": sorted(lineages),
        "regions": sorted(regions),
    }


def import_kazakhstan(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.kazakhstan_reference_dir,
        "WBR_KAZAKHSTAN_REFERENCE_DIR",
    )
    raw_path = directory / "KZ-raw-coordinates.csv"
    data_path = directory / "KZ-data.csv"
    missing = [path.name for path in (raw_path, data_path) if not path.exists()]
    if missing:
        raise ValidationError(
            f"Missing required Kazakhstan files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_kazakhstan(settings)
    manifest["source_file_sha256"] = file_sha256(raw_path)
    manifest["metadata_file_sha256"] = file_sha256(data_path)
    dataset = _ensure_dataset(
        session,
        metadata=KAZAKHSTAN_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=_merge_coordinate_metadata(
            raw_path=raw_path,
            data_path=data_path,
            country_code="KZ",
            region_label="Kazakhstan",
            dataset_label="Kazakhstan",
        ),
        source_filename=raw_path.name,
        source_file_for_hash=raw_path,
        fallback_country_code="KZ",
    )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [raw_path.name, data_path.name],
        **summary,
    }


def import_serbia(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.serbia_reference_dir,
        "WBR_SERBIA_REFERENCE_DIR",
    )
    raw_path = directory / "RS_21_80-raw-coordinates.csv"
    data_path = directory / "RS_21_80-data.csv"
    missing = [path.name for path in (raw_path, data_path) if not path.exists()]
    if missing:
        raise ValidationError(
            f"Missing required Serbia files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_serbia(settings)
    manifest["source_file_sha256"] = file_sha256(raw_path)
    manifest["metadata_file_sha256"] = file_sha256(data_path)
    optional_map = directory / "RS-map.png"
    if optional_map.exists():
        manifest["map_file_sha256"] = file_sha256(optional_map)
    dataset = _ensure_dataset(
        session,
        metadata=SERBIA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=_merge_coordinate_metadata(
            raw_path=raw_path,
            data_path=data_path,
            country_code="RS",
            region_label="Serbia",
            dataset_label="Serbia",
        ),
        source_filename=raw_path.name,
        source_file_for_hash=raw_path,
        fallback_country_code="RS",
    )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [raw_path.name, data_path.name],
        **summary,
    }


def import_mexico(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.mexico_reference_dir,
        "WBR_MEXICO_REFERENCE_DIR",
    )
    raw_path = directory / "MX-raw-coordinates.csv"
    data_path = directory / "MX-data.csv"
    missing = [path.name for path in (raw_path, data_path) if not path.exists()]
    if missing:
        raise ValidationError(
            f"Missing required Mexico files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_mexico(settings)
    manifest["source_file_sha256"] = file_sha256(raw_path)
    manifest["metadata_file_sha256"] = file_sha256(data_path)
    dataset = _ensure_dataset(
        session,
        metadata=MEXICO_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=_merge_coordinate_metadata(
            raw_path=raw_path,
            data_path=data_path,
            country_code="MX",
            region_label="Tabasco, Mexico",
            dataset_label="Mexico",
        ),
        source_filename=raw_path.name,
        source_file_for_hash=raw_path,
        fallback_country_code="MX",
    )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [raw_path.name, data_path.name],
        **summary,
    }


def import_northwestern_europe(
    settings: Settings,
    session: Session,
) -> dict[str, Any]:
    directory = _configured_dir(
        settings.northwestern_europe_reference_dir,
        "WBR_NORTHWESTERN_EUROPE_REFERENCE_DIR",
    )
    missing = [
        name
        for name in NORTHWESTERN_EUROPE_REQUIRED_FILES
        if not (directory / name).exists()
    ]
    if missing:
        raise ValidationError(
            f"Missing required Northwestern Europe files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_northwestern_europe(settings)
    manifest["source_file_sha256"] = {
        path.name: file_sha256(path)
        for path in _expected_files(
            directory,
            (
                *NORTHWESTERN_EUROPE_REQUIRED_FILES,
                *NORTHWESTERN_EUROPE_OPTIONAL_FILES,
            ),
        )
    }
    manifest["analysis_scope_note"] = (
        "Country raw-coordinate files are imported after merging their matching "
        "country data CSV. Image ZIP files are retained for provenance only and "
        "are not imported by the coordinate-only workflow."
    )
    dataset = _ensure_dataset(
        session,
        metadata=NORTHWESTERN_EUROPE_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summaries = []
    for country_code, (
        country_name,
        raw_filename,
        data_filename,
        _archive_filename,
    ) in NORTHWESTERN_EUROPE_COUNTRY_FILES.items():
        raw_path = directory / raw_filename
        data_path = directory / data_filename
        summaries.append(
            _import_coordinate_frame(
                session,
                dataset=dataset,
                frame=_merge_coordinate_metadata(
                    raw_path=raw_path,
                    data_path=data_path,
                    country_code=country_code,
                    region_label=country_name,
                    dataset_label="Northwestern Europe",
                    normalize_file_aliases=True,
                ),
                source_filename=raw_path.name,
                source_file_for_hash=raw_path,
                fallback_country_code=country_code,
            )
        )
    combined = Counter()
    countries: set[str] = set()
    samples = 0
    lineages: set[str] = set()
    regions: set[str] = set()
    for summary in summaries:
        combined.update(
            {
                key: value
                for key, value in summary.items()
                if isinstance(value, int)
            }
        )
        countries.update(summary.get("countries", []))
        samples += int(summary.get("samples", 0))
        lineages.update(summary.get("lineages", []))
        regions.update(summary.get("regions", []))
    return {
        "dataset_code": dataset.dataset_code,
        "files": [
            filename
            for _, raw_filename, data_filename, _ in NORTHWESTERN_EUROPE_COUNTRY_FILES.values()
            for filename in (raw_filename, data_filename)
        ],
        **combined,
        "countries": sorted(countries),
        "samples": samples,
        "lineages": sorted(lineages),
        "regions": sorted(regions),
    }


def import_algeria(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.algeria_reference_dir,
        "WBR_ALGERIA_REFERENCE_DIR",
    )
    raw_path = directory / "DZ-2025-raw-coordinates.csv"
    data_path = directory / "DZ-2025-data.csv"
    missing = [path.name for path in (raw_path, data_path) if not path.exists()]
    if missing:
        raise ValidationError(
            f"Missing required Algeria files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_algeria(settings)
    manifest["source_file_sha256"] = file_sha256(raw_path)
    manifest["metadata_file_sha256"] = file_sha256(data_path)
    dataset = _ensure_dataset(
        session,
        metadata=ALGERIA_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summary = _import_coordinate_frame(
        session,
        dataset=dataset,
        frame=_merge_coordinate_metadata(
            raw_path=raw_path,
            data_path=data_path,
            country_code="DZ",
            region_label="Algeria",
            dataset_label="Algeria",
        ),
        source_filename=raw_path.name,
        source_file_for_hash=raw_path,
        fallback_country_code="DZ",
    )
    return {
        "dataset_code": dataset.dataset_code,
        "files": [raw_path.name, data_path.name],
        **summary,
    }


def _caste_coordinate_frame(path: Path, *, caste: str, sex: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "file" not in frame.columns:
        raise ValidationError(f"{path.name} must contain a file column.")
    frame["sample"] = frame["file"].map(_sample_id_from_wing_filename)
    frame["side"] = frame["file"].map(_side_from_wing_filename)
    frame["caste"] = caste
    frame["sex"] = sex
    return frame


def import_queens_drones(settings: Settings, session: Session) -> dict[str, Any]:
    directory = _configured_dir(
        settings.queens_drones_reference_dir,
        "WBR_QUEENS_DRONES_REFERENCE_DIR",
    )
    drone_path = directory / "drones-raw-coordinates.csv"
    queen_path = directory / "queens-raw-coordinates.csv"
    missing = [path.name for path in (drone_path, queen_path) if not path.exists()]
    if missing:
        raise ValidationError(
            f"Missing required queens/drones files: {', '.join(missing)}."
        )
    template = ensure_apis_19_template(session)
    manifest = inspect_queens_drones(settings)
    manifest["source_file_sha256"] = {
        path.name: file_sha256(path)
        for path in (
            drone_path,
            queen_path,
            directory / "queens-wing-length.csv",
            directory / "queens-weight.csv",
        )
        if path.exists()
    }
    manifest["analysis_scope_note"] = (
        "Queen and drone coordinates are imported as external reference records "
        "but excluded from the worker-only published Apis analysis model."
    )
    dataset = _ensure_dataset(
        session,
        metadata=QUEENS_DRONES_DATASET,
        template_id=template.id,
        manifest=manifest,
    )
    session.commit()
    summaries = [
        _import_coordinate_frame(
            session,
            dataset=dataset,
            frame=_caste_coordinate_frame(drone_path, caste="drone", sex="male"),
            source_filename=drone_path.name,
            source_file_for_hash=drone_path,
        ),
        _import_coordinate_frame(
            session,
            dataset=dataset,
            frame=_caste_coordinate_frame(queen_path, caste="queen", sex="female"),
            source_filename=queen_path.name,
            source_file_for_hash=queen_path,
        ),
    ]
    combined = Counter()
    countries: set[str] = set()
    samples = 0
    lineages: set[str] = set()
    regions: set[str] = set()
    for summary in summaries:
        combined.update(
            {
                key: value
                for key, value in summary.items()
                if isinstance(value, int)
            }
        )
        countries.update(summary.get("countries", []))
        samples += int(summary.get("samples", 0))
        lineages.update(summary.get("lineages", []))
        regions.update(summary.get("regions", []))
    return {
        "dataset_code": dataset.dataset_code,
        "files": [drone_path.name, queen_path.name],
        **combined,
        "countries": sorted(countries),
        "samples": samples,
        "lineages": sorted(lineages),
        "regions": sorted(regions),
        "analysis_inclusion": "excluded_from_worker_analysis_model",
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
            select(ExternalReferenceShape)
            .join(ExternalReferenceDataset)
            .where(ExternalReferenceDataset.dataset_code.in_(APIS_WORKER_ANALYSIS_DATASET_CODES))
            .order_by(ExternalReferenceShape.id)
        )
    )
    if not shapes:
        raise ValidationError(
            "No worker external reference shapes have been imported for the published Apis analysis."
        )
    template_id = template.id
    version = model_version or (
        int(session.scalar(select(func.max(AnalysisModel.model_version))) or 0) + 1
    )
    external_shape_ids = [shape.id for shape in shapes]
    sample_ids = [
        shape.source_sample_identifier or shape.source_record_identifier
        for shape in shapes
    ]
    region_labels = [shape.published_region for shape in shapes]
    lineage_labels = [shape.published_lineage for shape in shapes]
    source_hashes = {
        shape.source_filename: shape.source_row_hash
        for shape in shapes
    }
    source_dataset_ids = sorted({shape.external_dataset_id for shape in shapes})
    coordinates = np.asarray([json.loads(shape.coordinate_json) for shape in shapes], dtype=float)
    session.rollback()
    payload = build_reference_payload(
        coordinates=coordinates,
        external_shape_ids=external_shape_ids,
        sample_ids=sample_ids,
        region_labels=region_labels,
        lineage_labels=lineage_labels,
        source_hashes=source_hashes,
    )
    models = save_reference_payload_models(
        session,
        template_id=template_id,
        payload=payload,
        artifact_root=get_settings().analysis_artifact_dir,
        model_version=version,
        source_dataset_ids=source_dataset_ids,
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
    subparsers.add_parser("inspect-kaur-india")
    subparsers.add_parser("import-kaur-india")
    subparsers.add_parser("inspect-southwest-asia")
    subparsers.add_parser("import-southwest-asia")
    subparsers.add_parser("inspect-kazakhstan")
    subparsers.add_parser("import-kazakhstan")
    subparsers.add_parser("inspect-serbia")
    subparsers.add_parser("import-serbia")
    subparsers.add_parser("inspect-mexico")
    subparsers.add_parser("import-mexico")
    subparsers.add_parser("inspect-northwestern-europe")
    subparsers.add_parser("import-northwestern-europe")
    subparsers.add_parser("inspect-algeria")
    subparsers.add_parser("import-algeria")
    subparsers.add_parser("inspect-queens-drones")
    subparsers.add_parser("import-queens-drones")
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
        elif args.command == "inspect-kaur-india":
            _print_json(inspect_kaur_india(settings))
        elif args.command == "import-kaur-india":
            _print_json(import_kaur_india(settings, session))
        elif args.command == "inspect-southwest-asia":
            _print_json(inspect_southwest_asia(settings))
        elif args.command == "import-southwest-asia":
            _print_json(import_southwest_asia(settings, session))
        elif args.command == "inspect-kazakhstan":
            _print_json(inspect_kazakhstan(settings))
        elif args.command == "import-kazakhstan":
            _print_json(import_kazakhstan(settings, session))
        elif args.command == "inspect-serbia":
            _print_json(inspect_serbia(settings))
        elif args.command == "import-serbia":
            _print_json(import_serbia(settings, session))
        elif args.command == "inspect-mexico":
            _print_json(inspect_mexico(settings))
        elif args.command == "import-mexico":
            _print_json(import_mexico(settings, session))
        elif args.command == "inspect-northwestern-europe":
            _print_json(inspect_northwestern_europe(settings))
        elif args.command == "import-northwestern-europe":
            _print_json(import_northwestern_europe(settings, session))
        elif args.command == "inspect-algeria":
            _print_json(inspect_algeria(settings))
        elif args.command == "import-algeria":
            _print_json(import_algeria(settings, session))
        elif args.command == "inspect-queens-drones":
            _print_json(inspect_queens_drones(settings))
        elif args.command == "import-queens-drones":
            _print_json(import_queens_drones(settings, session))
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
