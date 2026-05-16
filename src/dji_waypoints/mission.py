"""Build a DJI Pilot-compatible waypoint mission KMZ from a list of points."""
from __future__ import annotations

from pathlib import Path

from .config import MissionConfig
from .readers import Point


def build_mission(
    points: list[Point],
    config: MissionConfig,
    output_path: str | Path,
) -> Path:
    """Write a DJI Pilot 2 waypoint mission KMZ to ``output_path``.

    Parameters
    ----------
    points : list[Point]
        Waypoints in WGS-84 (lat, lon, optional AMSL elevation).
    config : MissionConfig
        Mission parameters (drone, AGL, speed, hover, etc.).
    output_path : str | Path
        Destination KMZ file.

    Returns
    -------
    Path
        The written KMZ file.
    """
    from djikmz import DroneTask  # imported lazily so tests can run without it

    if not points:
        raise ValueError("Cannot build a mission with zero waypoints.")

    out = Path(output_path)

    # Determine takeoff elevation for terrain-following missions.
    takeoff_elev: float | None = None
    if config.terrain_follow:
        if config.takeoff_elevation_m is not None:
            takeoff_elev = config.takeoff_elevation_m
        else:
            elevs = [p.elevation_m for p in points if p.elevation_m is not None]
            if not elevs:
                raise ValueError(
                    "terrain_follow=True requires either "
                    "config.takeoff_elevation_m or per-point elevations."
                )
            takeoff_elev = min(elevs)

    mission = (
        DroneTask(config.drone_model, config.pilot_name)
        .name(config.mission_name)
        .speed(config.speed_mps)
        .altitude(config.agl_m)
    )

    for p in points:
        if config.terrain_follow and p.elevation_m is not None and takeoff_elev is not None:
            height = (p.elevation_m - takeoff_elev) + config.agl_m
        else:
            height = config.agl_m

        mission = (
            mission.fly_to(p.lat, p.lon)
            .height(height)
            .heading(config.heading_deg)
            .gimbal_pitch(config.gimbal_pitch)
            .hover(config.hover_sec)
            .take_photo(f"pt{p.id}")
        )

    mission.to_kmz(str(out))
    return out
