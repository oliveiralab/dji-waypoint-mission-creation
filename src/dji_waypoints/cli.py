"""Command-line entry point: ``dji-mission build INPUT --out OUTPUT [opts]``."""
from __future__ import annotations

import argparse
import logging
import zipfile
from pathlib import Path

from .config import FT_TO_M, MissionConfig
from .mission import build_mission
from .readers import load_points

logger = logging.getLogger("dji-mission")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dji-mission",
        description="Convert GIS sampling points into DJI Pilot 2 waypoint mission KMZ.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose output.")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress informational output.")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build a KMZ mission from a point file.")
    b.add_argument("input", help="Input file (.kml, .kmz, .shp, .geojson, .csv).")
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

    # Inspect subcommand
    i = sub.add_parser("inspect", help="Inspect a generated KMZ and print a summary.")
    i.add_argument("kmz", help="Path to a DJI waypoint mission KMZ file.")

    return p


def _inspect(kmz_path: str) -> int:
    """Read back a KMZ and print mission summary."""
    import xml.etree.ElementTree as ET

    path = Path(kmz_path)
    if not path.exists():
        logger.error("File not found: %s", path)
        return 1

    try:
        with zipfile.ZipFile(path, "r") as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                logger.error("No .kml file found inside %s", path)
                return 1
            kml_text = zf.read(kml_names[0]).decode("utf-8")
    except zipfile.BadZipFile:
        logger.error("Not a valid zip/kmz file: %s", path)
        return 1

    # Parse waypoints from the KML
    root = ET.fromstring(kml_text)

    # Try to find coordinates in Placemarks
    coords_text = root.findall(".//{http://www.opengis.net/kml/2.2}coordinates")
    if not coords_text:
        # Try without namespace
        coords_text = root.findall(".//coordinates")

    lats: list[float] = []
    lons: list[float] = []
    for ct in coords_text:
        text = (ct.text or "").strip()
        for line in text.split():
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    lons.append(float(parts[0]))
                    lats.append(float(parts[1]))
                except ValueError:
                    continue

    print(f"File: {path}")
    print(f"Size: {path.stat().st_size:,} bytes")
    print(f"KML entries: {kml_names}")

    if lats:
        print(f"Waypoints: {len(lats)}")
        print("Bounding box:")
        print(f"  Lat: [{min(lats):.6f}, {max(lats):.6f}]")
        print(f"  Lon: [{min(lons):.6f}, {max(lons):.6f}]")
    else:
        print("Waypoints: (could not parse coordinates)")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Configure logging
    if args.quiet:
        level = logging.WARNING
    elif args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s")

    if args.command == "inspect":
        return _inspect(args.kmz)

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
        logger.error("No points found in %s", args.input)
        return 2

    out = build_mission(points, config, args.out)
    logger.info("Wrote %s  (%s bytes, %d waypoints)", out, f"{Path(out).stat().st_size:,}", len(points))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
