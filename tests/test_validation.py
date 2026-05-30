"""Tests for input validation and KMZ reader."""
from __future__ import annotations

import zipfile

import pytest

from dji_waypoints.readers import (
    MAX_WAYPOINTS,
    Point,
    load_points,
    read_kmz,
    validate_points,
)


def test_validate_points_good():
    points = [
        Point(1, 40.0, -96.0),
        Point(2, 41.0, -95.0),
    ]
    result = validate_points(points)
    assert result == points


def test_validate_lat_out_of_range():
    points = [Point(1, 91.0, -96.0)]
    with pytest.raises(ValueError, match="latitude"):
        validate_points(points)


def test_validate_lat_negative_out_of_range():
    points = [Point(1, -91.0, -96.0)]
    with pytest.raises(ValueError, match="latitude"):
        validate_points(points)


def test_validate_lon_out_of_range():
    points = [Point(1, 40.0, 181.0)]
    with pytest.raises(ValueError, match="longitude"):
        validate_points(points)


def test_validate_lon_negative_out_of_range():
    points = [Point(1, 40.0, -181.0)]
    with pytest.raises(ValueError, match="longitude"):
        validate_points(points)


def test_validate_too_many_waypoints():
    points = [Point(i, 40.0 + i * 0.0001, -96.0) for i in range(MAX_WAYPOINTS + 1)]
    with pytest.raises(ValueError, match="Too many waypoints"):
        validate_points(points)


def test_validate_duplicate_warns():
    points = [
        Point(1, 40.0, -96.0),
        Point(2, 40.0, -96.0),  # duplicate
    ]
    with pytest.warns(UserWarning, match="Duplicate coordinates"):
        validate_points(points)


def test_validate_boundary_values():
    """Boundary lat/lon values should pass."""
    points = [
        Point(1, 90.0, 180.0),
        Point(2, -90.0, -180.0),
        Point(3, 0.0, 0.0),
    ]
    result = validate_points(points)
    assert len(result) == 3


def test_read_kmz(tmp_path):
    """Create a minimal KMZ and read it."""
    kml_content = (
        '<?xml version="1.0"?><kml><Document>'
        '<Placemark><ExtendedData><SchemaData>'
        '<SimpleData name="id">1</SimpleData>'
        '<SimpleData name="elevation">327.83</SimpleData>'
        '</SchemaData></ExtendedData>'
        '<Point><coordinates>-96.179573,40.617288,0</coordinates></Point>'
        '</Placemark></Document></kml>'
    )
    kmz_path = tmp_path / "test.kmz"
    with zipfile.ZipFile(kmz_path, "w") as zf:
        zf.writestr("doc.kml", kml_content)

    points = read_kmz(kmz_path)
    assert len(points) == 1
    assert points[0].id == 1
    assert points[0].elevation_m == 327.83


def test_load_points_kmz(tmp_path):
    """load_points dispatches .kmz correctly."""
    kml_content = (
        '<?xml version="1.0"?><kml><Document>'
        '<Placemark>'
        '<Point><coordinates>-96.0,40.0,0</coordinates></Point>'
        '</Placemark></Document></kml>'
    )
    kmz_path = tmp_path / "test.kmz"
    with zipfile.ZipFile(kmz_path, "w") as zf:
        zf.writestr("doc.kml", kml_content)

    points = load_points(kmz_path)
    assert len(points) == 1
    assert points[0].lat == pytest.approx(40.0)
    assert points[0].lon == pytest.approx(-96.0)


def test_read_kmz_no_kml_inside(tmp_path):
    """KMZ without a .kml raises ValueError."""
    kmz_path = tmp_path / "bad.kmz"
    with zipfile.ZipFile(kmz_path, "w") as zf:
        zf.writestr("readme.txt", "no kml here")
    with pytest.raises(ValueError, match="No .kml file found"):
        read_kmz(kmz_path)
