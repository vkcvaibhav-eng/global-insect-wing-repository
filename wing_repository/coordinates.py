"""Coordinate validation and rendered-image to source-image mapping."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Mapping, TypeAlias

from .errors import ValidationError

ClickEventToken: TypeAlias = tuple[int, float, float, float, float]


@dataclass(frozen=True, slots=True)
class Coordinate:
    """One landmark in source-image pixels and normalized coordinates."""

    x_pixel: float
    y_pixel: float
    x_normalized: float
    y_normalized: float


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValidationError(f"{name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{name} must be finite.")
    return number


def _positive_dimension(value: object, name: str) -> float:
    number = _finite_number(value, name)
    if number <= 0:
        raise ValidationError(f"{name} must be greater than zero.")
    return number


def normalize_coordinates(
    x_pixel: float,
    y_pixel: float,
    image_width: int,
    image_height: int,
) -> Coordinate:
    """Validate a source-pixel location and calculate normalized values.

    Coordinates use the raster convention: origin at the top-left, x grows to
    the right, and y grows down.  Values are floats because a downscaled display
    pixel can map to a subpixel location in the original raster.
    """

    x = _finite_number(x_pixel, "x_pixel")
    y = _finite_number(y_pixel, "y_pixel")
    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    if not 0 <= x < width or not 0 <= y < height:
        raise ValidationError("Landmark coordinates fall outside the original image.")
    return Coordinate(
        x_pixel=x,
        y_pixel=y,
        x_normalized=x / width,
        y_normalized=y / height,
    )


def map_rendered_click(
    click_x: float,
    click_y: float,
    rendered_width: float,
    rendered_height: float,
    original_width: int,
    original_height: int,
) -> Coordinate:
    """Map a component click in rendered CSS pixels to the source raster."""

    x = _finite_number(click_x, "click_x")
    y = _finite_number(click_y, "click_y")
    display_width = _positive_dimension(rendered_width, "rendered_width")
    display_height = _positive_dimension(rendered_height, "rendered_height")
    source_width = _positive_dimension(original_width, "original_width")
    source_height = _positive_dimension(original_height, "original_height")
    if not 0 <= x < display_width or not 0 <= y < display_height:
        raise ValidationError("Click falls outside the rendered image.")
    return normalize_coordinates(
        x * source_width / display_width,
        y * source_height / display_height,
        original_width,
        original_height,
    )


def map_rendered_viewport_click(
    click_x: float,
    click_y: float,
    rendered_width: float,
    rendered_height: float,
    original_width: int,
    original_height: int,
    viewport_left: int,
    viewport_top: int,
    viewport_width: int,
    viewport_height: int,
) -> Coordinate:
    """Map a click in a rendered cropped viewport to the full source raster."""

    x = _finite_number(click_x, "click_x")
    y = _finite_number(click_y, "click_y")
    display_width = _positive_dimension(rendered_width, "rendered_width")
    display_height = _positive_dimension(rendered_height, "rendered_height")
    source_width = _positive_dimension(original_width, "original_width")
    source_height = _positive_dimension(original_height, "original_height")
    left = _finite_number(viewport_left, "viewport_left")
    top = _finite_number(viewport_top, "viewport_top")
    width = _positive_dimension(viewport_width, "viewport_width")
    height = _positive_dimension(viewport_height, "viewport_height")
    if left < 0 or top < 0 or left + width > source_width or top + height > source_height:
        raise ValidationError("Viewport falls outside the original image.")
    if not 0 <= x < display_width or not 0 <= y < display_height:
        raise ValidationError("Click falls outside the rendered image.")
    return normalize_coordinates(
        left + (x * width / display_width),
        top + (y * height / display_height),
        original_width,
        original_height,
    )


def click_event_token(event: Mapping[str, object]) -> ClickEventToken:
    """Build a stable token used to ignore a component's replayed last click."""

    try:
        unix_time_value = event["unix_time"]
        if isinstance(unix_time_value, bool) or not isinstance(unix_time_value, Real):
            raise ValidationError("unix_time must be numeric.")
        unix_time_number = float(unix_time_value)
        if not math.isfinite(unix_time_number) or unix_time_number < 0:
            raise ValidationError("unix_time must be a non-negative finite value.")
        unix_time = int(unix_time_number)
        x = _finite_number(event["x"], "x")
        y = _finite_number(event["y"], "y")
        width = _positive_dimension(event["width"], "width")
        height = _positive_dimension(event["height"], "height")
    except KeyError as exc:
        raise ValidationError(f"Click event is missing {exc.args[0]!r}.") from exc
    return (unix_time, x, y, width, height)


def coordinate_from_click_event(
    event: Mapping[str, object],
    *,
    original_width: int,
    original_height: int,
) -> Coordinate:
    """Validate a component event and map it to the source raster."""

    click_event_token(event)
    return map_rendered_click(
        event["x"],  # type: ignore[arg-type]
        event["y"],  # type: ignore[arg-type]
        event["width"],  # type: ignore[arg-type]
        event["height"],  # type: ignore[arg-type]
        original_width,
        original_height,
    )


def coordinate_from_viewport_click_event(
    event: Mapping[str, object],
    *,
    original_width: int,
    original_height: int,
    viewport_left: int,
    viewport_top: int,
    viewport_width: int,
    viewport_height: int,
) -> Coordinate:
    """Validate a component event and map it from a viewport to the source raster."""

    click_event_token(event)
    return map_rendered_viewport_click(
        event["x"],  # type: ignore[arg-type]
        event["y"],  # type: ignore[arg-type]
        event["width"],  # type: ignore[arg-type]
        event["height"],  # type: ignore[arg-type]
        original_width,
        original_height,
        viewport_left,
        viewport_top,
        viewport_width,
        viewport_height,
    )
