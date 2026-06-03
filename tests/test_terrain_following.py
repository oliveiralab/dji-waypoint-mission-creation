"""Tests for terrain-following logic: elevation fetch, mission height calculation."""
from __future__ import annotations

import io
import json
import pathlib
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from dji_waypoints.config import MissionConfig
from dji_waypoints.readers import Point, fetch_elevations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_points(elevations):
    return [Point(i + 1, 41.0 + i * 0.01, -96.0, elev) for i, elev in enumerate(elevations)]


def _opentopodata_response(elevations):
    results = [{"dataset": "srtm90m", "elevation": e, "location": {}} for e in elevations]
    return json.dumps({"status": "OK", "results": results}).encode()


@contextmanager
def _mock_urlopen(body):
    with patch("dji_waypoints.readers.urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__ = lambda s: io.BytesIO(body)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_open


def _make_height_capture_fake():
    heights = []

    class _FakeChain:
        def name(self, *a, **kw): return self
        def speed(self, *a, **kw): return self
        def altitude(self, *a, **kw): return self
        def fly_to(self, *a, **kw): return self
        def height(self, h):
            heights.append(h)
            return self
        def heading(self, *a, **kw): return self
        def gimbal_pitch(self, *a, **kw): return self
        def hover(self, *a, **kw): return self
        def take_photo(self, *a, **kw): return self
        def to_kmz(self, *a, **kw): pass

    return _FakeChain(), heights


# ---------------------------------------------------------------------------
# fetch_elevations
# ---------------------------------------------------------------------------

class TestFetchElevations:
    def test_elevations_set_from_api(self):
        points = _make_points([None, None])
        body = _opentopodata_response([350.0, 355.5])
        with _mock_urlopen(body):
            result = fetch_elevations(points)
        assert result[0].elevation_m == 350.0
        assert result[1].elevation_m == 355.5

    def test_null_elevation_stays_none(self):
        points = _make_points([None])
        body = _opentopodata_response([None])
        with _mock_urlopen(body):
            result = fetch_elevations(points)
        assert result[0].elevation_m is None

    def test_skips_already_populated_points(self):
        points = [Point(1, 41.0, -96.0, 300.0), Point(2, 41.1, -96.1, None)]
        body = _opentopodata_response([400.0])
        with _mock_urlopen(body) as mock_open:
            result = fetch_elevations(points)
        mock_open.assert_called_once()
        assert result[0].elevation_m == 300.0
        assert result[1].elevation_m == 400.0

    def test_mutates_in_place_and_returns_same_list(self):
        points = _make_points([None])
        body = _opentopodata_response([123.4])
        with _mock_urlopen(body):
            returned = fetch_elevations(points)
        assert returned is points
        assert points[0].elevation_m == 123.4

    def test_noop_when_all_elevations_present(self):
        points = _make_points([100.0, 200.0])
        with patch("dji_waypoints.readers.urllib.request.urlopen") as mock_open:
            result = fetch_elevations(points)
        mock_open.assert_not_called()
        assert result == points

    def test_raises_on_api_error_status(self):
        points = _make_points([None])
        body = json.dumps({"status": "QUERY_DENIED", "error": "Rate limit"}).encode()
        with _mock_urlopen(body):
            with pytest.raises(ValueError, match="Elevation lookup failed"):
                fetch_elevations(points)

    def test_raises_on_unsupported_source(self):
        with pytest.raises(ValueError, match="Unsupported elevation source"):
            fetch_elevations(_make_points([None]), source="invalid_dem")


# ---------------------------------------------------------------------------
# Mission height calculation with terrain following
# ---------------------------------------------------------------------------

class TestTerrainFollowingMission:

    def test_terrain_follow_requires_elevations(self, tmp_path):
        points = _make_points([None, None, None])
        config = MissionConfig(terrain_follow=True, takeoff_elevation_m=None)
        with pytest.raises(ValueError, match="terrain_follow=True requires"):
            from dji_waypoints.mission import build_mission
            build_mission(points, config, tmp_path / "out.kmz")

    def test_terrain_follow_uses_takeoff_elevation_m(self):
        from dji_waypoints.mission import build_mission
        elevations = [300.0, 305.0, 295.0]
        takeoff, agl = 300.0, 25.0
        points = _make_points(elevations)
        config = MissionConfig(terrain_follow=True, takeoff_elevation_m=takeoff, agl_m=agl)
        fake, heights = _make_height_capture_fake()
        with patch("djikmz.DroneTask", return_value=fake):
            with tempfile.TemporaryDirectory() as td:
                build_mission(points, config, pathlib.Path(td) / "m.kmz")
        assert heights == pytest.approx([(e - takeoff) + agl for e in elevations])

    def test_terrain_follow_falls_back_to_min_elevation(self):
        from dji_waypoints.mission import build_mission
        elevations = [310.0, 300.0, 305.0]
        agl = 20.0
        points = _make_points(elevations)
        config = MissionConfig(terrain_follow=True, takeoff_elevation_m=None, agl_m=agl)
        fake, heights = _make_height_capture_fake()
        with patch("djikmz.DroneTask", return_value=fake):
            with tempfile.TemporaryDirectory() as td:
                build_mission(points, config, pathlib.Path(td) / "m.kmz")
        assert heights == pytest.approx([(e - 300.0) + agl for e in elevations])

    def test_sea_level_takeoff_elevation_is_not_dropped(self):
        """Regression: takeoff_elevation_m=0.0 must not be treated as None."""
        from dji_waypoints.mission import build_mission
        elevations = [0.0, 5.0, 10.0]
        agl = 30.0
        points = _make_points(elevations)
        config = MissionConfig(terrain_follow=True, takeoff_elevation_m=0.0, agl_m=agl)
        fake, heights = _make_height_capture_fake()
        with patch("djikmz.DroneTask", return_value=fake):
            with tempfile.TemporaryDirectory() as td:
                build_mission(points, config, pathlib.Path(td) / "m.kmz")
        assert heights == pytest.approx([(e - 0.0) + agl for e in elevations])

    def test_no_terrain_follow_constant_height(self):
        from dji_waypoints.mission import build_mission
        elevations = [300.0, 350.0, 400.0]
        agl = 25.0
        points = _make_points(elevations)
        config = MissionConfig(terrain_follow=False, agl_m=agl)
        fake, heights = _make_height_capture_fake()
        with patch("djikmz.DroneTask", return_value=fake):
            with tempfile.TemporaryDirectory() as td:
                build_mission(points, config, pathlib.Path(td) / "m.kmz")
        assert heights == pytest.approx([agl, agl, agl])
