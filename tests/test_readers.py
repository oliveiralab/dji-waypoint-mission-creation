"""Tests for the input readers (no djikmz required)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dji_waypoints.readers import load_points, read_csv, read_geojson, read_kml


REPO = Path(__file__).resolve().parents[1]
SAMPLE_CSV = REPO / "examples" / "sample_points.csv"


def test_read_csv_sample():
    points = read_csv(SAMPLE_CSV)
    assert len(points) == 6
    assert points[0].id == 1
    assert points[0].lat == pytest.approx(40.617288)
    assert points[0].lon == pytest.approx(-96.179573)
    assert points[0].elevation_m == pytest.approx(327.83)


def test_load_points_dispatch_csv():
    points = load_points(SAMPLE_CSV)
    assert len(points) == 6


def test_load_points_unsupported(tmp_path):
    bad = tmp_path / "data.xyz"
    bad.write_text("nope")
    with pytest.raises(ValueError, match="Unsupported"):
        load_points(bad)


def test_read_csv_aliases(tmp_path):
    p = tmp_path / "alt.csv"
    p.write_text("FID,Latitude,Longitude,Z\n7,1.0,2.0,3.0\n")
    points = read_csv(p)
    assert len(points) == 1
    assert points[0].id == 7
    assert points[0].lat == 1.0
    assert points[0].lon == 2.0
    assert points[0].elevation_m == 3.0


def test_read_csv_missing_latlon(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("id,foo\n1,2\n")
    with pytest.raises(ValueError, match="lat/lon"):
        read_csv(p)


def test_read_geojson(tmp_path):
    p = tmp_path / "pts.geojson"
    p.write_text(
        '{"type":"FeatureCollection","features":['
        '{"type":"Feature","properties":{"id":1},'
        '"geometry":{"type":"Point","coordinates":[-96.1,40.6,330.0]}},'
        '{"type":"Feature","properties":{"id":2,"elevation":331.0},'
        '"geometry":{"type":"Point","coordinates":[-96.2,40.7]}}'
        "]}"
    )
    points = read_geojson(p)
    assert [pt.id for pt in points] == [1, 2]
    assert points[0].elevation_m == 330.0
    assert points[1].elevation_m == 331.0


def test_read_kml_minimal(tmp_path):
    p = tmp_path / "pts.kml"
    p.write_text(
        '<?xml version="1.0"?><kml><Document>'
        '<Placemark><ExtendedData><SchemaData>'
        '<SimpleData name="id">1</SimpleData>'
        '<SimpleData name="elevation">327.83</SimpleData>'
        '</SchemaData></ExtendedData>'
        '<Point><coordinates>-96.179573,40.617288,0</coordinates></Point>'
        '</Placemark></Document></kml>'
    )
    points = read_kml(p)
    assert len(points) == 1
    assert points[0].id == 1
    assert points[0].elevation_m == 327.83
