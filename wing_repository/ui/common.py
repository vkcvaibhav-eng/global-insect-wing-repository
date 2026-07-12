"""Shared Streamlit presentation helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from wing_repository.config import get_settings
from wing_repository.image_store import ImageStore, image_store_from_settings
from wing_repository.models import Annotation
from wing_repository.ui.navigation import move_to_page
from wing_repository.ui.image_overlay import OverlayPoint, build_numbered_overlay


@st.cache_resource
def image_store() -> ImageStore:
    """Return the process-wide immutable image store."""

    settings = get_settings()
    return image_store_from_settings(settings)


def annotation_point_rows(annotation: Annotation) -> list[dict[str, Any]]:
    """Return display/export-friendly rows ordered by template ordinal."""

    mm_per_pixel = annotation.wing_image.scale_mm_per_pixel
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
            "x_mm": (
                point.x_pixel * mm_per_pixel
                if mm_per_pixel is not None
                else np.nan
            ),
            "y_mm": (
                point.y_pixel * mm_per_pixel
                if mm_per_pixel is not None
                else np.nan
            ),
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
            "x_mm",
            "y_mm",
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
        if annotation.wing_image.scale_mm_per_pixel is not None:
            millimeter_coordinates = np.asarray(
                [(row["x_mm"], row["y_mm"]) for row in rows],
                dtype=np.float64,
            )
            frame[["x_mm", "y_mm"]] = millimeter_coordinates
    return frame


def annotation_overlay(
    annotation: Annotation,
    *,
    max_display_width: int = 800,
    allow_upscale: bool = False,
):
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
        max_display_width=max_display_width,
        allow_upscale=allow_upscale,
    )


def format_template(template: Any) -> str:
    """Return an explicit genus/template/version label."""

    return f"{template.taxon.genus} · {template.name} · v{template.version}"


def format_image_scale(image: Any) -> str:
    """Return a concise image-scale calibration label."""

    if image.scale_mm_per_pixel is None:
        return "Not calibrated"
    return (
        f"{image.scale_mm_per_pixel:.8g} mm/pixel "
        f"({1 / image.scale_mm_per_pixel:.3f} pixels/mm)"
    )
