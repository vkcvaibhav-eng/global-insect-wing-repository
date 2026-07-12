"""In-memory display derivatives for digitization and review.

The stored original is never changed. These helpers deliberately do not apply
EXIF orientation so display coordinates continue to refer to the encoded source
raster documented by ``WingImage.width`` and ``WingImage.height``.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from PIL import Image, ImageDraw, UnidentifiedImageError


@dataclass(frozen=True, slots=True)
class OverlayPoint:
    """A landmark location in original-raster pixel coordinates."""

    ordinal: int
    x_pixel: float
    y_pixel: float


class OverlayError(ValueError):
    """Raised when an image cannot be rendered consistently."""


def build_numbered_overlay(
    original_bytes: bytes,
    points: Iterable[OverlayPoint],
    *,
    expected_width: int,
    expected_height: int,
    max_display_width: int = 1_100,
    allow_upscale: bool = False,
) -> Image.Image:
    """Return a resized RGB proxy with numbered landmark markers.

    Point positions are scaled from the authoritative source-raster dimensions.
    The proxy is only a view; click conversion uses the browser event's actual
    rendered width and height rather than assuming this Pillow size.
    """

    if expected_width <= 0 or expected_height <= 0 or max_display_width <= 0:
        raise OverlayError("Image and display dimensions must be positive.")

    try:
        with Image.open(BytesIO(original_bytes)) as source:
            source.load()
            if source.width != expected_width or source.height != expected_height:
                raise OverlayError(
                    "Stored image dimensions no longer match the original metadata."
                )
            proxy = source.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise OverlayError("The stored original image cannot be decoded.") from exc

    should_resize = proxy.width > max_display_width or (
        allow_upscale and proxy.width != max_display_width
    )
    if should_resize:
        display_height = max(1, round(proxy.height * max_display_width / proxy.width))
        proxy = proxy.resize(
            (max_display_width, display_height),
            resample=Image.Resampling.LANCZOS,
        )

    scale_x = proxy.width / expected_width
    scale_y = proxy.height / expected_height
    draw = ImageDraw.Draw(proxy)
    radius = max(5, round(min(proxy.width, proxy.height) * 0.009))

    for point in sorted(points, key=lambda item: item.ordinal):
        x = point.x_pixel * scale_x
        y = point.y_pixel * scale_y
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(215, 35, 35),
            outline=(255, 255, 255),
            width=max(1, radius // 3),
        )
        label = str(point.ordinal)
        text_box = draw.textbbox((0, 0), label)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        draw.text(
            (x - text_width / 2, y - text_height / 2 - 1),
            label,
            fill=(255, 255, 255),
            stroke_width=1,
            stroke_fill=(90, 0, 0),
        )

    return proxy
