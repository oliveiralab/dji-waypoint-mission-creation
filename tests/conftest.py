"""Shared pytest fixtures for dji-waypoints tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from dji_waypoints.readers import Point

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

SAMPLE_CSV     = EXAMPLES / "sample_points.csv"
SAMPLE_GEOJSON = EXAMPLES / "sample_points.geojson"
SAMPLE_KML     = EXAMPLES / "sample_points.kml"


@pytest.fixture
def sample_points() -> list[Point]:
    """Six Nebraska survey waypoints mirroring examples/sample_points.csv."""
    return [
        Point(1, 40.617288, -96.179573, 327.83),
        Point(2, 40.617450, -96.179620, 328.10),
        Point(3, 40.617612, -96.179667, 328.42),
        Point(4, 40.617774, -96.179714, 328.71),
        Point(5, 40.617936, -96.179761, 329.05),
        Point(6, 40.618098, -96.179808, 329.38),
    ]


@pytest.fixture
def two_points() -> list[Point]:
    """Minimal two-point route with elevation, useful for mission builder tests."""
    return [
        Point(1, 40.617288, -96.179573, 327.83),
        Point(2, 40.617450, -96.179620, 328.10),
    ]
