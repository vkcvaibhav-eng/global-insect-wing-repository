"""In-memory display derivatives for digitization and review.

The stored original is never changed. These helpers deliberately do not apply
EXIF orientation so display coordinates continue to refer to the encoded source
raster documented by ``WingImage.width`` and ``WingImage.height``.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Literal

from PIL import Image, ImageDraw, UnidentifiedImageError


MarkerStyle = Literal["landmark", "scale_endpoint"]


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
    marker_style: MarkerStyle = "landmark",
) -> Image.Image:
    """Return a resized RGB proxy with precise numbered markers.

    Point positions are scaled from the authoritative source-raster dimensions.
    The proxy is only a view; click conversion uses the browser event's actual
    rendered width and height rather than assuming this Pillow size.
    """

    if expected_width <= 0 or expected_height <= 0 or max_display_width <= 0:
        raise OverlayError("Image and display dimensions must be positive.")
    if marker_style not in {"landmark", "scale_endpoint"}:
        raise OverlayError("Unsupported overlay marker style.")

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

    for point in sorted(points, key=lambda item: item.ordinal):
        x = point.x_pixel * scale_x
        y = point.y_pixel * scale_y
        if marker_style == "scale_endpoint":
            _draw_scale_endpoint_marker(draw, proxy, x, y, str(point.ordinal))
        else:
            _draw_landmark_marker(draw, proxy, x, y, str(point.ordinal))

    return proxy


def _label_position(
    image: Image.Image,
    x: float,
    y: float,
    text_width: int,
    text_height: int,
    *,
    offset: int,
) -> tuple[float, float]:
    """Place a label near, but not on top of, the exact point."""

    label_x = x + offset
    if label_x + text_width >= image.width:
        label_x = x - offset - text_width
    label_y = y - offset - text_height
    if label_y < 0:
        label_y = y + offset
    return (
        max(0, min(label_x, image.width - text_width)),
        max(0, min(label_y, image.height - text_height)),
    )


def _draw_offset_label(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    x: float,
    y: float,
    label: str,
    *,
    offset: int,
    fill: tuple[int, int, int],
    stroke_fill: tuple[int, int, int],
) -> None:
    text_box = draw.textbbox((0, 0), label)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    draw.text(
        _label_position(image, x, y, text_width, text_height, offset=offset),
        label,
        fill=fill,
        stroke_width=2,
        stroke_fill=stroke_fill,
    )


def _draw_landmark_marker(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    x: float,
    y: float,
    label: str,
) -> None:
    """Draw a small exact dot, with its number outside the clicked location."""

    radius = max(2, round(min(image.width, image.height) * 0.0035))
    outline = max(1, radius // 2)
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=(215, 35, 35),
        outline=(255, 255, 255),
        width=outline,
    )
    _draw_offset_label(
        draw,
        image,
        x,
        y,
        label,
        offset=max(6, radius + 5),
        fill=(215, 35, 35),
        stroke_fill=(255, 255, 255),
    )


def _draw_scale_endpoint_marker(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    x: float,
    y: float,
    label: str,
) -> None:
    """Draw a thin cursor-like endpoint marker for scale calibration."""

    tick = max(8, round(min(image.width, image.height) * 0.018))
    center_tick = max(3, tick // 3)
    outline_width = 3
    marker_width = 1
    # White under-stroke keeps the red cursor visible on dark wing images.
    draw.line((x, y - tick, x, y + tick), fill=(255, 255, 255), width=outline_width)
    draw.line(
        (x - center_tick, y, x + center_tick, y),
        fill=(255, 255, 255),
        width=outline_width,
    )
    draw.line((x, y - tick, x, y + tick), fill=(215, 35, 35), width=marker_width)
    draw.line(
        (x - center_tick, y, x + center_tick, y),
        fill=(215, 35, 35),
        width=marker_width,
    )
    _draw_offset_label(
        draw,
        image,
        x,
        y,
        label,
        offset=tick + 4,
        fill=(215, 35, 35),
        stroke_fill=(255, 255, 255),
    )
