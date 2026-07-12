from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from wing_repository.ui.image_overlay import (
    OverlayError,
    OverlayPoint,
    build_numbered_overlay,
)


def _png_bytes(width: int = 100, height: int = 60) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


def test_landmark_overlay_uses_small_dot_and_offset_label() -> None:
    overlay = build_numbered_overlay(
        _png_bytes(),
        [OverlayPoint(ordinal=1, x_pixel=50, y_pixel=30)],
        expected_width=100,
        expected_height=60,
        max_display_width=100,
    )

    center_pixel = overlay.getpixel((50, 30))
    assert center_pixel[0] > 150
    # The exact landmark location remains the red point, not white label text.
    assert center_pixel != (255, 255, 255)


def test_scale_endpoint_overlay_accepts_cursor_marker_style() -> None:
    overlay = build_numbered_overlay(
        _png_bytes(),
        [OverlayPoint(ordinal=1, x_pixel=50, y_pixel=30)],
        expected_width=100,
        expected_height=60,
        max_display_width=100,
        marker_style="scale_endpoint",
    )

    assert overlay.getpixel((50, 20))[0] > 150
    assert overlay.getpixel((50, 40))[0] > 150


def test_overlay_rejects_unknown_marker_style() -> None:
    with pytest.raises(OverlayError):
        build_numbered_overlay(
            _png_bytes(),
            [OverlayPoint(ordinal=1, x_pixel=50, y_pixel=30)],
            expected_width=100,
            expected_height=60,
            max_display_width=100,
            marker_style="bad",  # type: ignore[arg-type]
        )
