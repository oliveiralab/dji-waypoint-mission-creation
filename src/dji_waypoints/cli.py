"""Command-line entry point: ``dji-mission build INPUT --out OUTPUT [opts]``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import FT_TO_M, MissionConfig
from .mission import build_mission
from .readers import load_points


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dji-mission",
        description="Convert GIS sampling points into DJI Pilot 2 waypoint mission KMZ.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build a KMZ mission from a point file.")
    b.add_argument("input", help="Input file (.kml, .shp, .geojson, .csv).")
    b.add_argument("--out", "-o", required=True, help="Output KMZ path.")
    b.add_argument("--drone", default="M3M", help="DJI drone model (default: M3M).")
    b.add_argument("--pilot", default="pilot", help="Pilot name (default: pilot).")
    b.add_argument("--mission-name", default="Waypoint Survey")

    g = b.add_mutually_exclusive_group()
    g.add_argument("--agl-m", type=float, help="Flight height above ground in metres.")
    g.add_argument("--agl-ft", type=float, help="Flight height above ground in feet.")

    b.add_argument("--speed", type=float, default=5.0, help="Cruise speed m/s (default: 5).")
    b.add_argument("--hover", type=float, default=2.0, help="Hover seconds per point (default: 2).")
    b.add_argument("--gimbal-pitch", type=float, default=-90.0, help="Gimbal pitch deg (default: -90 nadir).")
    b.add_argument("--heading", type=float, default=0.0, help="Heading deg (default: 0).")
    b.add_argument("--terrain-follow", action="store_true",
                   help="Adjust per-point height so AGL is constant above local ground.")
    b.add_argument("--takeoff-elevation-m", type=float, default=None,
                   help="AMSL elevation of takeoff spot (required for --terrain-follow without per-point elevation).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "build":  # pragma: no cover
        return 1

    agl_m = args.agl_m if args.agl_m is not None else (
        args.agl_ft * FT_TO_M if args.agl_ft is not None else 25.908
    )

    config = MissionConfig(
        drone_model=args.drone,
        pilot_name=args.pilot,
        mission_name=args.mission_name,
        agl_m=agl_m,
        speed_mps=args.speed,
        hover_sec=args.hover,
        gimbal_pitch=args.gimbal_pitch,
        heading_deg=args.heading,
        terrain_follow=args.terrain_follow,
        takeoff_elevation_m=args.takeoff_elevation_m,
    )

    points = load_points(args.input)
    if not points:
        print(f"No points found in {args.input}", file=sys.stderr)
        return 2

    out = build_mission(points, config, args.out)
    print(f"Wrote {out}  ({Path(out).stat().st_size:,} bytes, {len(points)} waypoints)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
