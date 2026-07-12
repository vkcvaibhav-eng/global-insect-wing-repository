"""Source-coordinate CSV inspection and row parsing."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from wing_repository.errors import ValidationError
from wing_repository.morphometrics.validation import as_coordinate_array

_COORDINATE_PATTERNS = (
    re.compile(r"^(?:lm|landmark)?0?(\d{1,2})[_ .-]*([xy])$", re.IGNORECASE),
    re.compile(r"^([xy])[_ .-]*(?:lm|landmark)?0?(\d{1,2})$", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class CoordinateColumnLayout:
    """Detected source columns for 19 x,y coordinate pairs."""

    pairs: tuple[tuple[str, str], ...]
    detection_method: str


@dataclass(frozen=True, slots=True)
class ParsedReferenceRow:
    """A parsed external reference row ready for validation/import."""

    source_record_identifier: str
    source_sample_identifier: str | None
    country_code: str | None
    published_region: str | None
    published_lineage: str | None
    original_side: str | None
    coordinates: np.ndarray
    metadata: dict[str, Any]
    row_hash: str


def inspect_csv_schema(path: Path) -> dict[str, object]:
    """Return a non-mutating schema report for a CSV file."""

    frame = pd.read_csv(path, nrows=10)
    layout = detect_coordinate_columns(frame)
    return {
        "filename": path.name,
        "columns": list(frame.columns),
        "coordinate_detection_method": layout.detection_method,
        "coordinate_pair_count": len(layout.pairs),
        "coordinate_columns": [column for pair in layout.pairs for column in pair],
        "preview_rows": len(frame),
    }


def _coordinate_match(column: str) -> tuple[int, str] | None:
    normalized = str(column).strip()
    for pattern in _COORDINATE_PATTERNS:
        match = pattern.match(normalized)
        if match is None:
            continue
        if match.group(1).isdigit():
            ordinal = int(match.group(1))
            axis = match.group(2).lower()
        else:
            axis = match.group(1).lower()
            ordinal = int(match.group(2))
        if 1 <= ordinal <= 19:
            return ordinal, axis
    return None


def detect_coordinate_columns(frame: pd.DataFrame) -> CoordinateColumnLayout:
    """Detect 19 ordered x,y coordinate columns without hard-coding names."""

    by_ordinal: dict[int, dict[str, str]] = {}
    for column in frame.columns:
        matched = _coordinate_match(str(column))
        if matched is None:
            continue
        ordinal, axis = matched
        by_ordinal.setdefault(ordinal, {})[axis] = str(column)
    if all(index in by_ordinal and {"x", "y"} <= set(by_ordinal[index]) for index in range(1, 20)):
        return CoordinateColumnLayout(
            pairs=tuple((by_ordinal[index]["x"], by_ordinal[index]["y"]) for index in range(1, 20)),
            detection_method="named_landmark_xy_columns",
        )

    numeric_columns = [
        str(column)
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
    ]
    if len(numeric_columns) >= 38:
        return CoordinateColumnLayout(
            pairs=tuple(
                (numeric_columns[index], numeric_columns[index + 1])
                for index in range(0, 38, 2)
            ),
            detection_method="first_38_numeric_columns",
        )
    return CoordinateColumnLayout(pairs=(), detection_method="not_detected")


def _first_present(row: pd.Series, names: tuple[str, ...]) -> str | None:
    lower_to_column = {str(column).strip().casefold(): column for column in row.index}
    for name in names:
        column = lower_to_column.get(name.casefold())
        if column is not None and pd.notna(row[column]):
            value = str(row[column]).strip()
            if value:
                return value
    return None


def row_identity_hash(row: pd.Series) -> str:
    """Hash a source row independent of pandas object identity."""

    raw = {
        str(column): (None if pd.isna(value) else value)
        for column, value in row.to_dict().items()
    }
    return sha256(
        json.dumps(raw, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def parse_reference_row(
    row: pd.Series,
    layout: CoordinateColumnLayout,
    *,
    source_filename: str,
    fallback_country_code: str | None = None,
) -> ParsedReferenceRow:
    """Parse one external source row and preserve unrecognized metadata."""

    if len(layout.pairs) != 19:
        raise ValidationError("No complete 19-landmark coordinate layout was detected.")
    coordinates = []
    for x_column, y_column in layout.pairs:
        coordinates.append((float(row[x_column]), float(row[y_column])))
    coordinate_array = as_coordinate_array(coordinates)
    row_hash = row_identity_hash(row)
    record_id = _first_present(
        row,
        (
            "id",
            "ID",
            "record_id",
            "source_record_identifier",
            "filename",
            "file",
            "image",
            "name",
        ),
    ) or f"{source_filename}:{row.name}"
    sample_id = _first_present(
        row,
        ("sample", "sample_id", "colony", "colony_id", "locality_id", "apiary"),
    )
    country = _first_present(row, ("country", "country_code", "origin")) or fallback_country_code
    region = _first_present(row, ("region", "reference_group", "group"))
    lineage = _first_present(row, ("lineage", "published_lineage", "class"))
    side = _first_present(row, ("side", "wing_side", "orientation"))
    coordinate_columns = {column for pair in layout.pairs for column in pair}
    recognized = coordinate_columns | {
        "id",
        "ID",
        "record_id",
        "source_record_identifier",
        "filename",
        "file",
        "image",
        "name",
        "sample",
        "sample_id",
        "colony",
        "colony_id",
        "locality_id",
        "apiary",
        "country",
        "country_code",
        "origin",
        "region",
        "reference_group",
        "group",
        "lineage",
        "published_lineage",
        "class",
        "side",
        "wing_side",
        "orientation",
    }
    metadata = {
        str(column): (None if pd.isna(value) else value)
        for column, value in row.to_dict().items()
        if str(column) not in recognized
    }
    return ParsedReferenceRow(
        source_record_identifier=str(record_id),
        source_sample_identifier=sample_id,
        country_code=country.upper() if country is not None and len(country) <= 3 else country,
        published_region=region,
        published_lineage=(
            lineage.upper()
            if lineage is not None and lineage.casefold() in {"a", "c", "m", "o"}
            else lineage
        ),
        original_side=side,
        coordinates=coordinate_array,
        metadata=metadata,
        row_hash=row_hash,
    )


__all__ = [
    "CoordinateColumnLayout",
    "ParsedReferenceRow",
    "detect_coordinate_columns",
    "inspect_csv_schema",
    "parse_reference_row",
    "row_identity_hash",
]
