"""Generate a Mavic 3 Multispectral (M3M) waypoint mission at 30 ft AGL.

Source: east butler/samplingpoints_volitant/brucetest22/2025_wilber_clatonia_points.shp
        WGS-84 geographic (EPSG:4326) -- no reprojection needed.

Flat field, no terrain following: all waypoints fly at a constant 9.144 m
(30 ft) above the takeoff point.  Uses AGL altitude mode.

Usage:  py convert_to_dji_m3m_30ft_brucetest22.py
"""
from __future__ import annotations

from pathlib import Path

import shapefile
from djikmz import DroneTask

HERE = Path(__file__).parent
SHP = (
    HERE
    / "east butler"
    / "samplingpoints_volitant"
    / "brucetest22"
    / "2025_wilber_clatonia_points.shp"
)
OUT_KMZ = SHP.parent / "2025_wilber_clatonia_M3M_30ft.kmz"

# --- Mission parameters ------------------------------------------------------
DRONE_MODEL   = "M3M"
PILOT_NAME    = "ofrn"
MISSION_NAME  = "Wilber-Clatonia M3M 30 ft AGL"
SPEED_MPS     = 5.0     # m/s cruise speed between waypoints
AGL_M         = 9.144   # 30 ft = 9.144 m, constant height above takeoff
HOVER_SEC     = 2.0     # hover before each photo (reduces motion blur)
GIMBAL_PITCH  = -90.0   # nadir (straight down)
HEADING_DEG   = 0.0     # fixed north-facing heading
# -----------------------------------------------------------------------------


def read_points(shp_path: Path) -> list[tuple[int, float, float]]:
    """Return list of (id, lat, lon) from a WGS-84 point shapefile."""
    sf = shapefile.Reader(str(shp_path))
    field_names = [f[0] for f in sf.fields[1:]]
    id_idx = field_names.index("id") if "id" in field_names else None

    points: list[tuple[int, float, float]] = []
    for i, sr in enumerate(sf.iterShapeRecords()):
        lon, lat = sr.shape.points[0]
        pid = int(sr.record[id_idx]) if id_idx is not None else i + 1
        points.append((pid, lat, lon))
    return points


def main() -> None:
    points = read_points(SHP)
    print(f"Loaded {len(points)} waypoints from {SHP.name}")
    print(f"Constant AGL: {AGL_M:.3f} m  ({AGL_M / 0.3048:.1f} ft)")

    mission = (
        DroneTask(DRONE_MODEL, PILOT_NAME)
        .name(MISSION_NAME)
        .speed(SPEED_MPS)
        .altitude(AGL_M)
    )

    for pid, lat, lon in points:
        mission = (
            mission
            .fly_to(lat, lon)
            .height(AGL_M)        # flat field -> constant height above takeoff
            .heading(HEADING_DEG)
            .gimbal_pitch(GIMBAL_PITCH)
            .hover(HOVER_SEC)
            .take_photo(f"pt{pid}")
        )

    mission.to_kmz(str(OUT_KMZ))
    print(f"Wrote {OUT_KMZ}  ({OUT_KMZ.stat().st_size:,} bytes)")
    print("Load in DJI Pilot 2 -> Waypoint Mission -> Import KMZ/KML.")


if __name__ == "__main__":
    main()
