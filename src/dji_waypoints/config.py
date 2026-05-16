"""Mission configuration dataclass."""
from __future__ import annotations

from dataclasses import dataclass


FT_TO_M = 0.3048


@dataclass
class MissionConfig:
    """All knobs that control a generated DJI waypoint mission.

    Defaults are tuned for nadir stand-count photography on a Mavic 3
    Multispectral (M3M). Override any field for your own use case.
    """

    # Drone / pilot identity
    drone_model: str = "M3M"
    pilot_name: str = "pilot"
    mission_name: str = "Waypoint Survey"

    # Flight
    agl_m: float = 25.908          # constant height above ground (85 ft default)
    speed_mps: float = 5.0         # cruise speed between waypoints
    hover_sec: float = 2.0         # hover at each point before photo
    gimbal_pitch: float = -90.0    # -90 = nadir (straight down)
    heading_deg: float = 0.0       # fixed compass heading

    # Terrain handling
    # If True and points carry elevation, each waypoint height is adjusted so
    # that AGL is constant above the local ground (terrain following).
    # If False, every waypoint flies at agl_m above the takeoff point.
    terrain_follow: bool = False

    # Required for terrain_follow=True: AMSL elevation (m) of the takeoff spot.
    # If None, the lowest-elevation input point is used as the reference.
    takeoff_elevation_m: float | None = None

    @classmethod
    def from_ft(cls, agl_ft: float, **kwargs) -> "MissionConfig":
        """Convenience: build a config using feet for AGL."""
        return cls(agl_m=agl_ft * FT_TO_M, **kwargs)
