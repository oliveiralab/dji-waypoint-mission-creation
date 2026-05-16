"""Tests for MissionConfig defaults and conversions."""
from dji_waypoints import MissionConfig
from dji_waypoints.config import FT_TO_M


def test_defaults():
    c = MissionConfig()
    assert c.drone_model == "M3M"
    assert c.gimbal_pitch == -90.0
    assert c.terrain_follow is False
    assert c.takeoff_elevation_m is None


def test_from_ft():
    c = MissionConfig.from_ft(agl_ft=50.0, drone_model="M3E")
    assert c.drone_model == "M3E"
    assert c.agl_m == 50.0 * FT_TO_M
