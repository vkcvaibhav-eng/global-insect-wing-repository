from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from wing_repository.ui.image_overlay import (
    ImageViewport,
    OverlayError,
    OverlayPoint,
    build_numbered_overlay,
    build_numbered_viewport_overlay,
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


def test_viewport_overlay_crops_and_offsets_points() -> None:
    overlay = build_numbered_viewport_overlay(
        _png_bytes(120, 80),
        [OverlayPoint(ordinal=1, x_pixel=60, y_pixel=40)],
        expected_width=120,
        expected_height=80,
        viewport=ImageViewport(left=40, top=20, width=40, height=40),
        max_display_width=80,
    )

    assert overlay.size == (80, 80)
    # Original point (60, 40) is center of the 40x40 viewport, displayed at 80x80.
    center_pixel = overlay.getpixel((40, 40))
    assert center_pixel[0] > 150
    assert center_pixel != (255, 255, 255)


def test_viewport_overlay_rejects_out_of_bounds_viewport() -> None:
    with pytest.raises(OverlayError):
        build_numbered_viewport_overlay(
            _png_bytes(120, 80),
            [],
            expected_width=120,
            expected_height=80,
            viewport=ImageViewport(left=100, top=20, width=40, height=40),
        )


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
