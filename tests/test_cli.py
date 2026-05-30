"""Tests for the CLI entry point."""
from __future__ import annotations

from pathlib import Path

from dji_waypoints.cli import main

REPO = Path(__file__).resolve().parents[1]
SAMPLE_CSV = REPO / "examples" / "sample_points.csv"


def test_cli_build(tmp_path):
    out = tmp_path / "out.kmz"
    rc = main(["build", str(SAMPLE_CSV), "--out", str(out)])
    assert rc == 0
    assert out.exists()


def test_cli_build_with_agl_ft(tmp_path):
    out = tmp_path / "out.kmz"
    rc = main(["build", str(SAMPLE_CSV), "--out", str(out), "--agl-ft", "85"])
    assert rc == 0
    assert out.exists()


def test_cli_build_with_terrain_follow(tmp_path):
    out = tmp_path / "out.kmz"
    rc = main([
        "build", str(SAMPLE_CSV), "--out", str(out),
        "--terrain-follow", "--takeoff-elevation-m", "327.0",
    ])
    assert rc == 0
    assert out.exists()


def test_cli_build_no_points(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("id,lat,lon\n")
    out = tmp_path / "out.kmz"
    rc = main(["build", str(empty), "--out", str(out)])
    assert rc == 2


def test_cli_inspect(tmp_path):
    # First build a KMZ, then inspect it.
    out = tmp_path / "mission.kmz"
    main(["build", str(SAMPLE_CSV), "--out", str(out)])
    rc = main(["inspect", str(out)])
    assert rc == 0


def test_cli_inspect_missing_file(tmp_path):
    rc = main(["inspect", str(tmp_path / "nope.kmz")])
    assert rc == 1


def test_cli_verbose(tmp_path):
    out = tmp_path / "out.kmz"
    rc = main(["-v", "build", str(SAMPLE_CSV), "--out", str(out)])
    assert rc == 0


def test_cli_quiet(tmp_path):
    out = tmp_path / "out.kmz"
    rc = main(["-q", "build", str(SAMPLE_CSV), "--out", str(out)])
    assert rc == 0
