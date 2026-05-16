"""Streamlit web UI for dji-waypoints.

Run locally:
    pip install -e ".[web]"
    streamlit run app/streamlit_app.py

Non-programmers can upload a point file (CSV / KML / GeoJSON / zipped
Shapefile), preview it on a map, tweak mission parameters in the sidebar,
and download a DJI Pilot 2 KMZ.
"""
from __future__ import annotations

import math
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from dji_waypoints import MissionConfig, build_mission, load_points
from dji_waypoints.config import FT_TO_M
from dji_waypoints.readers import Point

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTS = {".csv", ".kml", ".geojson", ".json", ".zip"}
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "sample_points.csv"
REPO_URL = "https://github.com/mailson-unl/dji-waypoint-mission-creation"
APP_URL = "https://dji-waypoint-mission.streamlit.app/"

# US FAA Part 107: drones must stay <= 400 ft (~121.92 m) AGL.
PART_107_CEILING_M = 121.92
SOFT_WARN_AGL_M = 100.0

# Per-waypoint photo capture overhead (s): gimbal settle + shutter.
PHOTO_OVERHEAD_S = 1.5


# ---------------------------------------------------------------------------
# Helpers (pure)
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 coordinates."""
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def path_length_m(points: list[Point]) -> float:
    return sum(
        haversine_m(a.lat, a.lon, b.lat, b.lon)
        for a, b in zip(points, points[1:])
    )


def estimate_flight_seconds(
    points: list[Point], speed_mps: float, hover_sec: float
) -> float:
    if not points or speed_mps <= 0:
        return 0.0
    cruise = path_length_m(points) / speed_mps
    per_point = (hover_sec + PHOTO_OVERHEAD_S) * len(points)
    return cruise + per_point


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def elevation_range(points: list[Point]) -> tuple[float, float] | None:
    elevs = [p.elevation_m for p in points if p.elevation_m is not None]
    return (min(elevs), max(elevs)) if elevs else None


def _save_upload(tmp_dir: Path, uploaded) -> Path:
    """Persist an uploaded file (and any shapefile sidecars in a .zip)."""
    name = uploaded.name
    ext = Path(name).suffix.lower()
    target = tmp_dir / name
    target.write_bytes(uploaded.getvalue())

    if ext == ".zip":
        with zipfile.ZipFile(target) as zf:
            zf.extractall(tmp_dir)
        shp = next(tmp_dir.rglob("*.shp"), None)
        if shp is None:
            raise ValueError(
                "Uploaded .zip does not contain a .shp file. "
                "Include .shp, .shx, .dbf and .prj together."
            )
        return shp

    return target


# ---------------------------------------------------------------------------
# Sidebar — mission configuration
# ---------------------------------------------------------------------------

def render_sidebar(points: list[Point] | None) -> MissionConfig:
    """Render the sidebar config and return the resulting MissionConfig."""
    st.sidebar.header("Mission configuration")

    st.sidebar.subheader("Identity")
    drone_model = st.sidebar.selectbox(
        "Drone model",
        ["M3M", "M3E", "M4E (encoded as M3E)"],
        key="drone_model",
        help=(
            "M4E is not yet natively supported by djikmz; it is encoded as M3E. "
            "DJI Pilot 2 will prompt to re-bind on import — accept."
        ),
    )
    mission_name = st.sidebar.text_input(
        "Mission name", value="Waypoint Survey", key="mission_name"
    )
    pilot_name = st.sidebar.text_input("Pilot name", value="pilot", key="pilot_name")

    st.sidebar.subheader("Flight")
    speed_mps = st.sidebar.number_input(
        "Cruise speed (m/s)",
        min_value=0.5, max_value=20.0, value=5.0, step=0.5,
        key="speed_mps",
    )
    hover_sec = st.sidebar.number_input(
        "Hover before photo (s)",
        min_value=0.0, max_value=30.0, value=2.0, step=0.5,
        key="hover_sec",
    )

    st.sidebar.subheader("Altitude")
    agl_unit = st.sidebar.radio(
        "Height unit", ["feet", "metres"], horizontal=True, key="agl_unit"
    )
    if agl_unit == "feet":
        agl_ft = st.sidebar.number_input(
            "Height above ground (ft)",
            min_value=1.0, max_value=400.0, value=85.0, step=1.0,
            key="agl_ft",
        )
        agl_m = agl_ft * FT_TO_M
        st.sidebar.caption(f"= {agl_m:.2f} m")
    else:
        agl_m = st.sidebar.number_input(
            "Height above ground (m)",
            min_value=0.5, max_value=200.0, value=25.908, step=0.5,
            key="agl_m_input",
        )
        st.sidebar.caption(f"= {agl_m / FT_TO_M:.1f} ft")

    if agl_m > PART_107_CEILING_M:
        st.sidebar.error(
            f"⚠️ {agl_m:.0f} m exceeds the FAA Part 107 ceiling of 120 m "
            "(400 ft). You need a waiver."
        )
    elif agl_m > SOFT_WARN_AGL_M:
        st.sidebar.warning(
            f"Heads-up: {agl_m:.0f} m is close to the 120 m Part 107 ceiling."
        )

    st.sidebar.subheader("Camera")
    gimbal_pitch = st.sidebar.slider(
        "Gimbal pitch (°)", min_value=-90, max_value=0, value=-90,
        help="-90 = straight down (nadir), 0 = horizon.",
        key="gimbal_pitch",
    )
    heading_deg = st.sidebar.slider(
        "Heading (°)", min_value=0, max_value=359, value=0,
        help="Fixed compass heading for repeatable image orientation.",
        key="heading_deg",
    )

    st.sidebar.subheader("Terrain")
    terrain_follow = st.sidebar.checkbox(
        "Terrain following",
        value=False,
        help=(
            "Keeps AGL constant above local ground. Needs per-point elevations "
            "in the input AND a takeoff elevation."
        ),
        key="terrain_follow",
    )

    # Smart default: pre-fill takeoff elevation from data when available.
    default_takeoff = 0.0
    erange = elevation_range(points) if points else None
    if erange is not None:
        default_takeoff = round(erange[0], 2)
    # Use a dynamic key so the widget picks up the new default when data changes.
    takeoff_key = f"takeoff_elev::{default_takeoff:.2f}"
    takeoff_elev = st.sidebar.number_input(
        "Takeoff elevation, AMSL (m)",
        min_value=-500.0, max_value=9000.0,
        value=default_takeoff, step=0.1,
        help=(
            "Only used when terrain following is on. Auto-filled from the "
            "minimum elevation in your points. Look up your spot at "
            "https://apps.nationalmap.gov/elevation/"
        ),
        key=takeoff_key,
    )
    if terrain_follow and erange is None:
        st.sidebar.warning(
            "Terrain following needs per-point elevations in your input. "
            "Current file has none."
        )

    st.sidebar.divider()
    with st.sidebar.expander("About"):
        st.markdown(
            f"**dji-waypoints** — open source\n\n"
            f"[Live app]({APP_URL}) · [GitHub repo]({REPO_URL})\n\n"
            "Created by **Mailson Freire de Oliveira**, "
            "Water and Cropping Systems Extension Educator, "
            "University of Nebraska–Lincoln, "
            "Institute of Agriculture and Natural Resources.\n\n"
            "If you use this tool in scientific work, please cite the author."
        )

    drone_str = "M3E" if drone_model.startswith("M4E") else drone_model

    return MissionConfig(
        drone_model=drone_str,
        pilot_name=pilot_name,
        mission_name=mission_name,
        agl_m=agl_m,
        speed_mps=speed_mps,
        hover_sec=hover_sec,
        gimbal_pitch=float(gimbal_pitch),
        heading_deg=float(heading_deg),
        terrain_follow=terrain_follow,
        takeoff_elevation_m=(
            takeoff_elev if terrain_follow and takeoff_elev != 0.0 else None
        ),
    )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

def render_upload() -> Path | None:
    """Render upload UI. Returns a path to a points file or None."""
    st.subheader("1 — Upload your sampling points")

    col_up, col_sample = st.columns([3, 1])
    with col_up:
        uploaded = st.file_uploader(
            "CSV, KML, GeoJSON, or a .zip containing a Shapefile "
            "(.shp + .shx + .dbf + .prj)",
            type=["csv", "kml", "geojson", "json", "zip"],
            accept_multiple_files=False,
            key="uploader",
        )
    with col_sample:
        st.write("")
        st.write("")
        if st.button(
            "Try sample data",
            use_container_width=True,
            help="Load the 6-point demo CSV bundled in the repo.",
        ):
            st.session_state["use_sample"] = True
            st.session_state.pop("result", None)
            st.rerun()

    if uploaded is not None:
        st.session_state["use_sample"] = False
        tmp = Path(tempfile.gettempdir()) / "_dji_upload"
        tmp.mkdir(exist_ok=True)
        try:
            return _save_upload(tmp, uploaded)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not stage upload: {exc}")
            return None

    if st.session_state.get("use_sample") and SAMPLE_PATH.exists():
        st.caption(f"Using sample data: `{SAMPLE_PATH.name}` (6 points)")
        return SAMPLE_PATH

    st.info(
        "Drop a points file above, or click **Try sample data** to explore. "
        "CSVs should have columns `id, lat, lon, elevation` (WGS-84)."
    )
    return None


def render_preview(points: list[Point], config: MissionConfig) -> None:
    st.subheader("2 — Preview")

    distance_m = path_length_m(points)
    eta = estimate_flight_seconds(points, config.speed_mps, config.hover_sec)
    erange = elevation_range(points)

    cols = st.columns(4)
    cols[0].metric("Waypoints", len(points))
    cols[1].metric("Path length", f"{distance_m:,.0f} m")
    cols[2].metric("Est. flight time", format_duration(eta))
    if erange is not None:
        cols[3].metric(
            "Elev. range",
            f"{erange[1] - erange[0]:.1f} m",
            delta=f"{erange[0]:.1f} → {erange[1]:.1f} m",
            delta_color="off",
        )
    else:
        cols[3].metric("Elev. range", "n/a")

    st.map(
        data=[{"lat": p.lat, "lon": p.lon} for p in points],
        zoom=14,
    )

    with st.expander(f"Show {len(points)} waypoint(s) as a table"):
        st.dataframe(
            [
                {"id": p.id, "lat": p.lat, "lon": p.lon,
                 "elevation_m": p.elevation_m}
                for p in points[:500]
            ],
            use_container_width=True,
        )
        if len(points) > 500:
            st.caption(f"Showing first 500 of {len(points)} rows.")


def render_build_and_download(
    points: list[Point], config: MissionConfig
) -> None:
    """Build button + cached result + download. Survives reruns."""
    st.subheader("3 — Build & download")

    if st.button(
        "Build mission KMZ",
        type="primary",
        use_container_width=True,
        key="build_btn",
    ):
        with st.spinner("Building KMZ…"):
            try:
                with tempfile.TemporaryDirectory() as td:
                    out_path = Path(td) / (
                        f"{(config.mission_name or 'mission').replace(' ', '_')}.kmz"
                    )
                    build_mission(points, config, out_path)
                    st.session_state["result"] = {
                        "kmz_bytes": out_path.read_bytes(),
                        "file_name": out_path.name,
                        "n_points": len(points),
                    }
            except Exception as exc:  # noqa: BLE001
                st.session_state.pop("result", None)
                st.error(f"Mission build failed: {exc}")

    result = st.session_state.get("result")
    if not result:
        return

    st.success(
        f"Built `{result['file_name']}` with {result['n_points']} waypoint(s)."
    )
    st.download_button(
        "⬇️ Download KMZ",
        data=result["kmz_bytes"],
        file_name=result["file_name"],
        mime="application/vnd.google-earth.kmz",
        type="primary",
        use_container_width=True,
        key="dl_btn",
    )
    st.caption(
        "Next: copy the KMZ to your tablet/controller and open it in "
        "**DJI Pilot 2 → Waypoint Mission → Import KMZ/KML**."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="DJI Waypoint Mission Builder",
        page_icon="🚁",
        layout="wide",
    )

    st.title("🚁 DJI Waypoint Mission Builder")
    st.caption(
        "Upload GIS sampling points, tweak mission settings in the sidebar, "
        "and download a DJI Pilot 2–compatible KMZ. No programming required."
    )

    src_path = render_upload()

    points: list[Point] = []
    load_error: str | None = None
    if src_path is not None:
        try:
            points = load_points(src_path)
        except Exception as exc:  # noqa: BLE001
            load_error = f"Could not read `{src_path.name}`: {exc}"

    config = render_sidebar(points if points else None)

    if load_error:
        st.error(load_error)
        st.stop()
    if src_path is None:
        st.stop()
    if not points:
        st.warning("The file was parsed but contained zero points.")
        st.stop()

    render_preview(points, config)
    render_build_and_download(points, config)


if __name__ == "__main__":  # pragma: no cover
    main()
