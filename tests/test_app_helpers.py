"""Unit tests for the pure helpers in app/streamlit_app.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dji_waypoints.readers import Point

# Load the app module without triggering Streamlit's runtime.
_APP_PATH = Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py"
_spec = importlib.util.spec_from_file_location("streamlit_app", _APP_PATH)
streamlit_app = importlib.util.module_from_spec(_spec)
sys.modules["streamlit_app"] = streamlit_app
_spec.loader.exec_module(streamlit_app)  # type: ignore[union-attr]


def test_haversine_known_distance():
    # Lincoln to Omaha, NE: ~80 km.
    d = streamlit_app.haversine_m(40.8136, -96.7026, 41.2565, -95.9345)
    assert 75_000 < d < 90_000


def test_path_length_sums_segments():
    a = Point(1, 40.6, -96.1, None)
    b = Point(2, 40.6, -96.0, None)
    c = Point(3, 40.5, -96.0, None)
    total = streamlit_app.path_length_m([a, b, c])
    seg1 = streamlit_app.haversine_m(a.lat, a.lon, b.lat, b.lon)
    seg2 = streamlit_app.haversine_m(b.lat, b.lon, c.lat, c.lon)
    assert abs(total - (seg1 + seg2)) < 1e-6


def test_path_length_single_point_is_zero():
    assert streamlit_app.path_length_m([Point(1, 40.6, -96.1)]) == 0.0
    assert streamlit_app.path_length_m([]) == 0.0


def test_estimate_flight_seconds_includes_hover_and_overhead():
    pts = [Point(1, 40.6, -96.1), Point(2, 40.6, -96.0)]
    distance = streamlit_app.path_length_m(pts)
    eta = streamlit_app.estimate_flight_seconds(pts, speed_mps=5.0, hover_sec=2.0)
    expected = distance / 5.0 + (2.0 + streamlit_app.PHOTO_OVERHEAD_S) * 2
    assert abs(eta - expected) < 1e-6


def test_estimate_flight_seconds_handles_edge_cases():
    assert streamlit_app.estimate_flight_seconds([], 5.0, 2.0) == 0.0
    assert streamlit_app.estimate_flight_seconds(
        [Point(1, 0.0, 0.0)], 0.0, 2.0
    ) == 0.0


def test_format_duration():
    assert streamlit_app.format_duration(0) == "0m 00s"
    assert streamlit_app.format_duration(75) == "1m 15s"
    assert streamlit_app.format_duration(3725) == "1h 02m 05s"


def test_elevation_range():
    pts = [
        Point(1, 0, 0, 100.0),
        Point(2, 0, 0, 110.0),
        Point(3, 0, 0, None),
        Point(4, 0, 0, 95.0),
    ]
    assert streamlit_app.elevation_range(pts) == (95.0, 110.0)
    assert streamlit_app.elevation_range([Point(1, 0, 0, None)]) is None
    assert streamlit_app.elevation_range([]) is None
