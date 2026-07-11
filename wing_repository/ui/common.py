"""Shared Streamlit presentation helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from wing_repository.config import get_settings
from wing_repository.image_store import ImageStore, image_store_from_settings
from wing_repository.models import Annotation
from wing_repository.ui.image_overlay import OverlayPoint, build_numbered_overlay


@st.cache_resource
def image_store() -> ImageStore:
    """Return the process-wide immutable image store."""

    settings = get_settings()
    return image_store_from_settings(settings)


def annotation_point_rows(annotation: Annotation) -> list[dict[str, Any]]:
    """Return display/export-friendly rows ordered by template ordinal."""

    points = sorted(
        annotation.points,
        key=lambda point: point.template_landmark.ordinal,
    )
    return [
        {
            "landmark": point.template_landmark.ordinal,
            "label": point.template_landmark.label,
            "x_pixel": point.x_pixel,
            "y_pixel": point.y_pixel,
            "x_normalized": point.x_normalized,
            "y_normalized": point.y_normalized,
        }
        for point in points
    ]


def annotation_dataframe(annotation: Annotation) -> pd.DataFrame:
    """Build an ordered pandas table from NumPy coordinate matrices."""

    rows = annotation_point_rows(annotation)
    frame = pd.DataFrame(
        rows,
        columns=[
            "landmark",
            "label",
            "x_pixel",
            "y_pixel",
            "x_normalized",
            "y_normalized",
        ],
    )
    if rows:
        pixel_coordinates = np.asarray(
            [(row["x_pixel"], row["y_pixel"]) for row in rows],
            dtype=np.float64,
        )
        normalized_coordinates = np.asarray(
            [
                (row["x_normalized"], row["y_normalized"])
                for row in rows
            ],
            dtype=np.float64,
        )
        frame[["x_pixel", "y_pixel"]] = pixel_coordinates
        frame[["x_normalized", "y_normalized"]] = normalized_coordinates
    return frame


def annotation_overlay(annotation: Annotation):
    """Load the immutable original and render its numbered point overlay."""

    original = image_store().load_original(annotation.wing_image.storage_key)
    points = [
        OverlayPoint(
            ordinal=point.template_landmark.ordinal,
            x_pixel=point.x_pixel,
            y_pixel=point.y_pixel,
        )
        for point in annotation.points
    ]
    return build_numbered_overlay(
        original,
        points,
        expected_width=annotation.image_width,
        expected_height=annotation.image_height,
        max_display_width=800,
    )


def format_template(template: Any) -> str:
    """Return an explicit genus/template/version label."""

    return f"{template.taxon.genus} · {template.name} · v{template.version}"


def move_to_page(page_name: str) -> None:
    """Select another role-visible page on the next Streamlit run."""

    st.session_state["wbr_page"] = page_name
    st.rerun()
