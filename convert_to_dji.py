"""Convert a generic point KML (e.g. QGIS export with elevation) into a
DJI Pilot-compatible waypoint mission KMZ using the `djikmz` package.

Designed for stand-count ground-truth comparison with Sentera FieldAgent:
- Constant AGL across all waypoints (terrain-following) -> constant GSD
- Nadir gimbal (-90 deg) -> identical look angle every shot
- Brief hover before each photo -> sharp images, no motion blur
- Fixed heading -> repeatable image orientation

Usage:  py convert_to_dji.py
"""
from __future__ import annotations

import re
from pathlib import Path

from djikmz import DroneTask

HERE = Path(__file__).parent
SRC_KML = HERE / "samplingpoints_with_elevation.kml"
OUT_KMZ = HERE / "samplingpoints_dji_mission_M3M.kmz"

# --- Mission parameters (edit as needed) -------------------------------------
DRONE_MODEL = "M3M"
PILOT_NAME = "ofrn"
MISSION_NAME = "SamplingPoints Survey"
SPEED_MPS = 5.0           # slower = sharper photos; 5 m/s is good for stand counts
AGL_M = 25.908            # CONSTANT height above the ground at every waypoint (85 ft = 25.908 m)
HOVER_SEC = 2.0           # hover at each point before taking photo
GIMBAL_PITCH = -90.0      # -90 = straight down (nadir) for stand counting
HEADING_DEG = 0.0         # fixed compass heading for repeatable image orientation

# Elevation (m AMSL) of the spot you will take off from.
# Takeoff location: lat 40.617288, lon -96.179573 (USGS 3DEP DEM = 327.83 m)
TAKEOFF_ELEVATION_M: float | None = 327.83
# -----------------------------------------------------------------------------


def parse_points(kml_path: Path) -> list[tuple[int, float, float, float]]:
    """Return list of (id, lat, lon, elevation_m_AMSL)."""
    text = kml_path.read_text(encoding="utf-8")

    placemark_re = re.compile(r'<Placemark[^>]*>(.*?)</Placemark>', re.DOTALL)
    id_re = re.compile(r'<SimpleData name="id">([\d.]+)</SimpleData>')
    elev_re = re.compile(r'<SimpleData name="elevation">([\d.\-]+)</SimpleData>')
    coord_re = re.compile(r'<coordinates>\s*([\-\d.]+),([\-\d.]+)')

    points = []
    for body in placemark_re.findall(text):
        coord_m = coord_re.search(body)
        if not coord_m:
            continue
        id_m = id_re.search(body)
        elev_m = elev_re.search(body)
        pid = int(float(id_m.group(1))) if id_m else len(points) + 1
        lon = float(coord_m.group(1))
        lat = float(coord_m.group(2))
        elev = float(elev_m.group(1)) if elev_m else 0.0
        points.append((pid, lat, lon, elev))
    return points


def main() -> None:
    points = parse_points(SRC_KML)
    elevations = [p[3] for p in points]
    e_min, e_max = min(elevations), max(elevations)
    print(f"Parsed {len(points)} waypoints. Ground elevation range: "
          f"{e_min:.2f} - {e_max:.2f} m  (delta {e_max - e_min:.2f} m)")

    takeoff_elev = TAKEOFF_ELEVATION_M if TAKEOFF_ELEVATION_M is not None else e_min
    if TAKEOFF_ELEVATION_M is None:
        low_pid = min(points, key=lambda p: p[3])[0]
        print(f"Using lowest-point elevation as takeoff reference: "
              f"{takeoff_elev:.2f} m (point #{low_pid}). "
              f"Take off near that point, or set TAKEOFF_ELEVATION_M explicitly.")

    # Heights above takeoff so each waypoint sits AGL_M above its own ground.
    # height_above_takeoff = (point_ground_elev - takeoff_ground_elev) + AGL_M
    mission = (
        DroneTask(DRONE_MODEL, PILOT_NAME)
        .name(MISSION_NAME)
        .speed(SPEED_MPS)
        .altitude(AGL_M)  # global default; overridden per waypoint below
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
          f"-> constant {AGL_M:.1f} m AGL at every point.")


if __name__ == "__main__":
    main()
