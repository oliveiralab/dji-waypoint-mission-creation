"""Streamlit web UI for dji-waypoints.

Run locally:
    pip install -e ".[web]"
    streamlit run app/streamlit_app.py

Users upload a point file (CSV / KML / GeoJSON / zipped Shapefile), choose
mission parameters from a form, and download a DJI Pilot 2 KMZ.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from dji_waypoints import MissionConfig, build_mission, load_points
from dji_waypoints.config import FT_TO_M

SUPPORTED_EXTS = {".csv", ".kml", ".geojson", ".json", ".zip"}


def _save_upload(tmp_dir: Path, uploaded) -> Path:
    """Persist the uploaded file (and any shapefile sidecars in a .zip) to disk.

    Returns the path that ``load_points`` should be called with.
    """
    name = uploaded.name
    ext = Path(name).suffix.lower()
    target = tmp_dir / name
    target.write_bytes(uploaded.getvalue())

    if ext == ".zip":
        with zipfile.ZipFile(target) as zf:
            zf.extractall(tmp_dir)
        # Find the .shp inside the extracted set.
        shp = next(tmp_dir.rglob("*.shp"), None)
        if shp is None:
            raise ValueError(
                "Uploaded .zip does not contain a .shp file. "
                "Include .shp, .shx, .dbf and .prj together."
            )
        return shp

    return target


def main() -> None:
    st.set_page_config(
        page_title="DJI Waypoint Mission Builder",
        page_icon="🚁",
        layout="centered",
    )

    st.title("🚁 DJI Waypoint Mission Builder")
    st.caption(
        "Upload GIS sampling points, choose your mission settings, and download "
        "a DJI Pilot 2–compatible KMZ. No programming required."
    )

    # ---- Step 1: file upload -------------------------------------------------
    st.subheader("1. Upload your sampling points")
    uploaded = st.file_uploader(
        "Supported formats: CSV, KML, GeoJSON, or a .zip containing a Shapefile "
        "(.shp + .shx + .dbf + .prj)",
        type=["csv", "kml", "geojson", "json", "zip"],
        accept_multiple_files=False,
    )

    if uploaded is None:
        st.info(
            "Tip: a CSV with columns `id, lat, lon, elevation` is the simplest input. "
            "Coordinates must be WGS-84 (EPSG:4326)."
        )
        st.stop()

    ext = Path(uploaded.name).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        st.error(f"Unsupported file type: {ext}")
        st.stop()

    # ---- Step 2: mission configuration --------------------------------------
    st.subheader("2. Configure the mission")

    with st.form("mission_form"):
        c1, c2 = st.columns(2)
        with c1:
            drone_model = st.selectbox(
                "Drone model",
                ["M3M", "M3E", "M4E (encoded as M3E)"],
                help="M4E is not natively supported by djikmz; it is written as M3E. "
                     "DJI Pilot 2 will prompt to re-bind on import — accept.",
            )
            mission_name = st.text_input("Mission name", value="Waypoint Survey")
            pilot_name = st.text_input("Pilot name", value="pilot")
            speed_mps = st.number_input(
                "Cruise speed (m/s)", min_value=0.5, max_value=20.0, value=5.0, step=0.5
            )
            hover_sec = st.number_input(
                "Hover before photo (s)", min_value=0.0, max_value=30.0, value=2.0, step=0.5
            )

        with c2:
            agl_unit = st.radio("Height unit", ["feet", "metres"], horizontal=True)
            if agl_unit == "feet":
                agl_ft = st.number_input(
                    "Height above ground (ft)", min_value=1.0, max_value=400.0,
                    value=85.0, step=1.0,
                )
                agl_m = agl_ft * FT_TO_M
            else:
                agl_m = st.number_input(
                    "Height above ground (m)", min_value=0.5, max_value=120.0,
                    value=25.908, step=0.5,
                )

            gimbal_pitch = st.slider(
                "Gimbal pitch (°)", min_value=-90, max_value=0, value=-90,
                help="-90 = straight down (nadir), 0 = horizon.",
            )
            heading_deg = st.slider(
                "Heading (°)", min_value=0, max_value=359, value=0,
                help="Fixed compass heading for repeatable image orientation.",
            )

            terrain_follow = st.checkbox(
                "Terrain following",
                value=False,
                help="Keep AGL constant above local ground (requires per-point elevation "
                     "in the input, or a takeoff elevation below).",
            )
            takeoff_elev = st.number_input(
                "Takeoff elevation, AMSL (m, optional)",
                min_value=-500.0, max_value=9000.0, value=0.0, step=0.1,
                help="Only needed when terrain following. Look up your spot at "
                     "https://apps.nationalmap.gov/elevation/",
            )

        submitted = st.form_submit_button("Build mission KMZ", type="primary")

    if not submitted:
        st.stop()

    # ---- Step 3: build and offer download -----------------------------------
    drone_str = "M3E" if drone_model.startswith("M4E") else drone_model

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        try:
            src_path = _save_upload(tmp_dir, uploaded)
            points = load_points(src_path)
        except Exception as exc:  # noqa: BLE001 — show any reader error to the user
            st.error(f"Could not read the uploaded file: {exc}")
            st.stop()

        if not points:
            st.error("The file was parsed but contained zero points.")
            st.stop()

        config = MissionConfig(
            drone_model=drone_str,
            pilot_name=pilot_name,
            mission_name=mission_name,
            agl_m=agl_m,
            speed_mps=speed_mps,
            hover_sec=hover_sec,
            gimbal_pitch=float(gimbal_pitch),
            heading_deg=float(heading_deg),
            terrain_follow=terrain_follow,
            takeoff_elevation_m=takeoff_elev if terrain_follow and takeoff_elev != 0.0 else None,
        )

        out_path = tmp_dir / f"{mission_name.replace(' ', '_')}.kmz"
        try:
            build_mission(points, config, out_path)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Mission build failed: {exc}")
            st.stop()

        kmz_bytes = out_path.read_bytes()

    st.success(f"Built mission with {len(points)} waypoints.")

    with st.expander("Preview waypoints"):
        st.dataframe(
            [{"id": p.id, "lat": p.lat, "lon": p.lon, "elevation_m": p.elevation_m}
             for p in points[:200]],
            use_container_width=True,
        )
        # Map preview
        st.map(
            data=[{"lat": p.lat, "lon": p.lon} for p in points],
            zoom=14,
        )

    st.download_button(
        "⬇️ Download KMZ",
        data=kmz_bytes,
        file_name=out_path.name,
        mime="application/vnd.google-earth.kmz",
        type="primary",
    )

    st.caption(
        "Next: copy the KMZ to your tablet/controller and open it in "
        "**DJI Pilot 2 → Waypoint Mission → Import KMZ/KML**."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
