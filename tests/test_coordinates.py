from __future__ import annotations

import math

import pytest

from wing_repository.coordinates import (
    click_event_token,
    coordinate_from_click_event,
    coordinate_from_viewport_click_event,
    map_rendered_click,
    map_rendered_viewport_click,
    normalize_coordinates,
)
from wing_repository.errors import ValidationError


def test_normalize_coordinates_preserves_pixels_and_calculates_fractions() -> None:
    coordinate = normalize_coordinates(20.5, 15.25, 100, 61)

    assert coordinate.x_pixel == 20.5
    assert coordinate.y_pixel == 15.25
    assert coordinate.x_normalized == pytest.approx(0.205)
    assert coordinate.y_normalized == pytest.approx(0.25)


@pytest.mark.parametrize(
    ("x", "y", "width", "height"),
    [
        (-0.001, 0, 100, 100),
        (0, -0.001, 100, 100),
        (100, 0, 100, 100),
        (0, 100, 100, 100),
        (0, 0, 0, 100),
        (0, 0, 100, -1),
        (math.nan, 0, 100, 100),
        (0, math.inf, 100, 100),
        (True, 0, 100, 100),
    ],
)
def test_normalize_coordinates_rejects_invalid_inputs(
    x: object,
    y: object,
    width: object,
    height: object,
) -> None:
    with pytest.raises(ValidationError):
        normalize_coordinates(x, y, width, height)  # type: ignore[arg-type]


def test_map_rendered_click_scales_to_original_raster() -> None:
    coordinate = map_rendered_click(
        click_x=25,
        click_y=10,
        rendered_width=50,
        rendered_height=20,
        original_width=100,
        original_height=80,
    )

    assert coordinate.x_pixel == pytest.approx(50)
    assert coordinate.y_pixel == pytest.approx(40)
    assert coordinate.x_normalized == pytest.approx(0.5)
    assert coordinate.y_normalized == pytest.approx(0.5)


def test_map_rendered_viewport_click_adds_viewport_offset() -> None:
    coordinate = map_rendered_viewport_click(
        click_x=25,
        click_y=10,
        rendered_width=50,
        rendered_height=20,
        original_width=200,
        original_height=160,
        viewport_left=40,
        viewport_top=30,
        viewport_width=100,
        viewport_height=80,
    )

    assert coordinate.x_pixel == pytest.approx(90)
    assert coordinate.y_pixel == pytest.approx(70)
    assert coordinate.x_normalized == pytest.approx(0.45)
    assert coordinate.y_normalized == pytest.approx(0.4375)


def test_viewport_click_rejects_invalid_viewport() -> None:
    with pytest.raises(ValidationError):
        map_rendered_viewport_click(
            click_x=0,
            click_y=0,
            rendered_width=50,
            rendered_height=20,
            original_width=200,
            original_height=160,
            viewport_left=150,
            viewport_top=0,
            viewport_width=100,
            viewport_height=80,
        )


@pytest.mark.parametrize(("x", "y"), [(50, 0), (0, 20), (-1, 0), (0, -1)])
def test_map_rendered_click_uses_half_open_display_bounds(x: float, y: float) -> None:
    with pytest.raises(ValidationError):
        map_rendered_click(x, y, 50, 20, 100, 80)


def test_coordinate_from_click_event_validates_and_maps_event() -> None:
    event = {"unix_time": 1234, "x": 12.5, "y": 5, "width": 25, "height": 10}

    assert click_event_token(event) == (1234, 12.5, 5.0, 25.0, 10.0)
    coordinate = coordinate_from_click_event(
        event,
        original_width=200,
        original_height=100,
    )
    assert coordinate.x_pixel == pytest.approx(100)
    assert coordinate.y_pixel == pytest.approx(50)


def test_coordinate_from_viewport_click_event_validates_and_maps_event() -> None:
    event = {"unix_time": 1234, "x": 12.5, "y": 5, "width": 25, "height": 10}

    coordinate = coordinate_from_viewport_click_event(
        event,
        original_width=200,
        original_height=100,
        viewport_left=20,
        viewport_top=10,
        viewport_width=100,
        viewport_height=50,
    )
    assert coordinate.x_pixel == pytest.approx(70)
    assert coordinate.y_pixel == pytest.approx(35)


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"unix_time": -1, "x": 1, "y": 1, "width": 10, "height": 10},
        {"unix_time": 1, "x": 1, "y": 1, "width": 0, "height": 10},
        {"unix_time": 1, "x": "1", "y": 1, "width": 10, "height": 10},
    ],
)
def test_click_event_token_rejects_malformed_component_events(
    event: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        click_event_token(event)
