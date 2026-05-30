"""Tests for mission builder (build_mission)."""
from __future__ import annotations

import zipfile

import pytest

from dji_waypoints import MissionConfig, Point, build_mission


def test_build_mission_creates_kmz(tmp_path, two_points):
    config = MissionConfig(drone_model="M3M", pilot_name="test")
    out = tmp_path / "mission.kmz"
    result = build_mission(two_points, config, out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0
    # KMZ is a zip file
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        # Should contain at least one KML file
        assert any(n.lower().endswith(".kml") for n in names)


def test_build_mission_terrain_follow(tmp_path, two_points):
    config = MissionConfig(
        terrain_follow=True,
        takeoff_elevation_m=327.83,
        agl_m=25.0,
    )
    out = tmp_path / "terrain.kmz"
    result = build_mission(two_points, config, out)
    assert result.exists()


def test_build_mission_terrain_follow_uses_min_elevation(tmp_path, two_points):
    config = MissionConfig(terrain_follow=True, agl_m=25.0)
    out = tmp_path / "terrain2.kmz"
    result = build_mission(two_points, config, out)
    assert result.exists()


def test_build_mission_terrain_follow_no_elevation_raises(tmp_path):
    points = [
        Point(1, 40.617288, -96.179573),
        Point(2, 40.617450, -96.179620),
    ]
    config = MissionConfig(terrain_follow=True, agl_m=25.0)
    with pytest.raises(ValueError, match="terrain_follow"):
        build_mission(points, config, tmp_path / "bad.kmz")


def test_build_mission_empty_points_raises(tmp_path):
    config = MissionConfig()
    with pytest.raises(ValueError, match="zero waypoints"):
        build_mission([], config, tmp_path / "empty.kmz")
