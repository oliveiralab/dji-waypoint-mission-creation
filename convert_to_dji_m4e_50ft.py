"""Generate a Matrice 4E (M4E) waypoint mission at 50 ft AGL.

Reuses the parsing logic and mission settings from convert_to_dji.py but
overrides drone model, output filename, and altitude.

NOTE: djikmz does not yet support M4E in its drone enum table, so the file is
built as M3E (closest supported). All flight content (waypoints, heights,
gimbal, hover, photos) is identical; only the drone enum differs.
DJI Pilot 2 may prompt to re-bind the mission to your connected M4E -- accept.
"""
from __future__ import annotations

from pathlib import Path

from djikmz import DroneTask

from convert_to_dji import (
    parse_points,
    SRC_KML,
    PILOT_NAME,
    HOVER_SEC,
    GIMBAL_PITCH,
    HEADING_DEG,
    TAKEOFF_ELEVATION_M,
)

HERE = Path(__file__).parent
OUT_KMZ = HERE / "samplingpoints_dji_mission_M4E_road_50ft.kmz"

DRONE_MODEL = "M3E"  # M4E not in djikmz; M3E is closest supported
MISSION_NAME = "SamplingPoints Survey M4E 50ft"
AGL_M = 15.24  # 50 ft = 15.24 m
SPEED_MPS = 12.0  # cruise speed between waypoints (drone still hovers HOVER_SEC at each)


def main() -> None:
    points = parse_points(SRC_KML)
    elevations = [p[3] for p in points]
    e_min, e_max = min(elevations), max(elevations)
    print(f"Parsed {len(points)} waypoints. Ground elevation range: "
          f"{e_min:.2f} - {e_max:.2f} m  (delta {e_max - e_min:.2f} m)")

    takeoff_elev = TAKEOFF_ELEVATION_M if TAKEOFF_ELEVATION_M is not None else e_min
    print(f"Takeoff reference elevation: {takeoff_elev:.2f} m")

    mission = (
        DroneTask(DRONE_MODEL, PILOT_NAME)
        .name(MISSION_NAME)
        .speed(SPEED_MPS)
        .altitude(AGL_M)
    )

    for pid, lat, lon, elev in points:
        h = (elev - takeoff_elev) + AGL_M
        mission = (
            mission
            .fly_to(lat, lon)
            .height(h)
            .heading(HEADING_DEG)
            .gimbal_pitch(GIMBAL_PITCH)
            .hover(HOVER_SEC)
            .take_photo(f"pt{pid}")
        )

    mission.to_kmz(str(OUT_KMZ))
    h_min = min((p[3] - takeoff_elev) + AGL_M for p in points)
    h_max = max((p[3] - takeoff_elev) + AGL_M for p in points)
    print(f"Wrote {OUT_KMZ.name} ({OUT_KMZ.stat().st_size:,} bytes)")
    print(f"Per-waypoint heights above takeoff: {h_min:.2f} - {h_max:.2f} m  "
          f"-> constant {AGL_M:.2f} m AGL (50 ft) at every point.")


if __name__ == "__main__":
    main()
