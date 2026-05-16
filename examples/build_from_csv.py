"""Minimal example: build a mission from the bundled sample CSV.

Run from the repo root:
    pip install -e .
    py examples/build_from_csv.py
"""
from pathlib import Path

from dji_waypoints import MissionConfig, build_mission, load_points

HERE = Path(__file__).parent
SRC = HERE / "sample_points.csv"
OUT = HERE / "sample_mission.kmz"


def main() -> None:
    points = load_points(SRC)
    config = MissionConfig.from_ft(
        agl_ft=85.0,
        drone_model="M3M",
        pilot_name="demo",
        mission_name="Sample CSV Mission",
        terrain_follow=True,
        takeoff_elevation_m=327.83,
    )
    out = build_mission(points, config, OUT)
    print(f"Wrote {out} with {len(points)} waypoints.")


if __name__ == "__main__":
    main()
