"""Standalone mission-builder script.

This script exposes the same algorithm that powers the Streamlit web app so
you can integrate it directly into any Python workflow — no browser required.

Usage (from the repo root, with the package installed):
    pip install -e ".[dev]"
    python examples/build_mission.py

Or pass your own file and options:
    python examples/build_mission.py \
        --input examples/sample_points.csv \
        --out my_mission.kmz \
        --agl-ft 85 \
        --speed 5.0 \
        --terrain-follow

Requirements: the ``dji_waypoints`` package must be installed (``pip install -e .``
from the repo root installs it in editable mode).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The three building blocks you need
# ---------------------------------------------------------------------------
#   load_points      – reads CSV / KML / GeoJSON / Shapefile → list[Point]
#   fetch_elevations – fills missing elevation_m via OpenTopoData (optional)
#   MissionConfig    – all flight parameters in one dataclass
#   build_mission    – writes the DJI Pilot 2 KMZ file

from dji_waypoints import MissionConfig, build_mission, fetch_elevations, load_points
from dji_waypoints.config import FT_TO_M


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

def create_mission(
    input_path: str | Path,
    output_path: str | Path,
    *,
    agl_m: float = 25.908,          # 85 ft default
    speed_mps: float = 5.0,
    hover_sec: float = 2.0,
    gimbal_pitch: float = -90.0,    # nadir
    heading_deg: float = 0.0,
    drone_model: str = "M3M",
    pilot_name: str = "pilot",
    mission_name: str = "Waypoint Survey",
    terrain_follow: bool = False,
    takeoff_elevation_m: float | None = None,
    auto_fetch_elevations: bool = False,
) -> Path:
    """Build a DJI Pilot 2 KMZ mission file from a points file.

    Parameters
    ----------
    input_path:
        Path to a CSV, KML, GeoJSON, or Shapefile containing waypoints.
        CSVs must have columns: id, lat, lon[, elevation].
        Coordinates must be WGS-84 (EPSG:4326).
    output_path:
        Destination .kmz file (created or overwritten).
    agl_m:
        Flight height above ground in metres.
    speed_mps:
        Cruise speed between waypoints in m/s.
    hover_sec:
        Seconds to hover at each waypoint before taking a photo.
    gimbal_pitch:
        Camera pitch in degrees. -90 = straight down (nadir), 0 = horizon.
    heading_deg:
        Fixed compass heading for all waypoints (0 = North).
    drone_model:
        DJI drone model string accepted by djikmz ("M3M", "M3E", …).
    pilot_name:
        Pilot name embedded in the KMZ metadata.
    mission_name:
        Mission name embedded in the KMZ metadata.
    terrain_follow:
        When True, per-waypoint height is adjusted so AGL stays constant
        above the local ground surface.  Requires elevation data on the
        waypoints or a valid takeoff_elevation_m.
    takeoff_elevation_m:
        AMSL elevation of the takeoff location in metres.  Used as the
        reference datum for terrain-following.  If None, the lowest
        waypoint elevation is used automatically.
    auto_fetch_elevations:
        When True, query OpenTopoData (SRTM 90 m) to fill any missing
        elevation_m values before building.  Requires internet access.

    Returns
    -------
    Path
        The written KMZ file path.
    """
    # ── Step 1: load waypoints ────────────────────────────────────────────────
    points = load_points(str(input_path))
    if not points:
        raise ValueError(f"No waypoints found in {input_path!r}.")
    print(f"Loaded {len(points)} waypoint(s) from {Path(input_path).name}")

    # ── Step 2 (optional): fetch missing elevations from OpenTopoData ─────────
    # Required for terrain following when the input file has no elevation column.
    missing_elev = [p for p in points if p.elevation_m is None]
    if missing_elev:
        if auto_fetch_elevations or terrain_follow:
            print(f"Fetching elevations for {len(missing_elev)} point(s) via OpenTopoData …")
            points = fetch_elevations(points)
            filled = sum(1 for p in points if p.elevation_m is not None)
            print(f"  → {filled}/{len(points)} points now have elevation data.")
        else:
            print(
                f"  Warning: {len(missing_elev)} point(s) have no elevation. "
                "Pass auto_fetch_elevations=True or terrain_follow=True to fetch them."
            )

    # ── Step 3: configure the mission ─────────────────────────────────────────
    config = MissionConfig(
        drone_model=drone_model,
        pilot_name=pilot_name,
        mission_name=mission_name,
        agl_m=agl_m,
        speed_mps=speed_mps,
        hover_sec=hover_sec,
        gimbal_pitch=gimbal_pitch,
        heading_deg=heading_deg,
        terrain_follow=terrain_follow,
        takeoff_elevation_m=takeoff_elevation_m,
    )

    # ── Step 4: build the KMZ ─────────────────────────────────────────────────
    # Terrain-following mode: each waypoint's MSL altitude is computed as
    #   alt_msl = (point_elevation_m - takeoff_elevation_m) + agl_m
    # Flat mode: every waypoint flies at exactly agl_m above the takeoff point.
    out = build_mission(points, config, output_path)
    print(f"Built {out.name} with {len(points)} waypoint(s).")
    if terrain_follow:
        print("  Terrain-following enabled — per-waypoint heights adjusted.")
    return out


# ---------------------------------------------------------------------------
# CLI wrapper (optional — use create_mission() directly from your own code)
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a DJI Pilot 2 waypoint mission KMZ from a points file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--input", "-i",
        default=str(Path(__file__).parent / "sample_points.csv"),
        help="Input file (.csv, .kml, .geojson, or .shp inside a .zip).",
    )
    p.add_argument(
        "--out", "-o",
        default="mission_output.kmz",
        help="Output KMZ path.",
    )

    alt = p.add_mutually_exclusive_group()
    alt.add_argument("--agl-m", type=float, help="Flight height above ground in metres.")
    alt.add_argument("--agl-ft", type=float, default=85.0,
                     help="Flight height above ground in feet.")

    p.add_argument("--speed", type=float, default=5.0, metavar="M/S",
                   help="Cruise speed between waypoints.")
    p.add_argument("--hover", type=float, default=2.0, metavar="SEC",
                   help="Hover seconds at each waypoint before photo.")
    p.add_argument("--gimbal-pitch", type=float, default=-90.0,
                   help="Gimbal pitch in degrees (-90 = nadir).")
    p.add_argument("--heading", type=float, default=0.0,
                   help="Fixed compass heading for all waypoints.")
    p.add_argument("--drone", default="M3M",
                   help="DJI drone model (M3M, M3E, …).")
    p.add_argument("--pilot", default="pilot")
    p.add_argument("--mission-name", default="Waypoint Survey")
    p.add_argument("--terrain-follow", action="store_true",
                   help="Enable terrain-following (adjusts per-waypoint AGL).")
    p.add_argument("--takeoff-elevation-m", type=float, default=None,
                   help="AMSL elevation (m) of takeoff spot for terrain-following.")
    p.add_argument("--fetch-elevations", action="store_true",
                   help="Query OpenTopoData to fill missing elevation values.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    agl_m = args.agl_m if args.agl_m is not None else args.agl_ft * FT_TO_M

    try:
        create_mission(
            input_path=args.input,
            output_path=args.out,
            agl_m=agl_m,
            speed_mps=args.speed,
            hover_sec=args.hover,
            gimbal_pitch=args.gimbal_pitch,
            heading_deg=args.heading,
            drone_model=args.drone,
            pilot_name=args.pilot,
            mission_name=args.mission_name,
            terrain_follow=args.terrain_follow,
            takeoff_elevation_m=args.takeoff_elevation_m,
            auto_fetch_elevations=args.fetch_elevations,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
