"""Streamlit web UI for dji-waypoints.

Visual design from the Claude Design handoff (sage palette, Geist typography,
3-pane layout: left sidebar = mission config, center = file source + map +
flight metrics, right = pre-flight checks + output + about).

Run locally:
    pip install -e ".[web]"
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import html
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
REPO_URL = "https://github.com/oliveiralab/dji-waypoint-mission-creation"
APP_URL = "https://dji-waypoint-mission.streamlit.app/"
APP_VERSION = "v0.4 · open source"

# US FAA Part 107: drones must stay <= 400 ft (~121.92 m) AGL.
PART_107_CEILING_M = 121.92
SOFT_WARN_AGL_M = 100.0

# Per-waypoint photo capture overhead (s): gimbal settle + shutter.
PHOTO_OVERHEAD_S = 1.5

# Rough single-pack endurance for a DJI M3M (minutes) — used for the
# battery-margin pre-flight badge. Conservative side of vendor spec.
M3M_ENDURANCE_MIN = 35.0


# ---------------------------------------------------------------------------
# Helpers (pure)
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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
        return f"{m}:{s:02d}"
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}"


def elevation_range(points: list[Point]) -> tuple[float, float] | None:
    elevs = [p.elevation_m for p in points if p.elevation_m is not None]
    return (min(elevs), max(elevs)) if elevs else None


def _save_upload(tmp_dir: Path, uploaded) -> Path:
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
# Custom CSS — sage palette, Geist typography, card-style chrome
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --accent:        #5b8a5a;
    --accent-ink:    #2f5a3a;
    --accent-soft:   #e6efe1;
    --accent-soft-ink: #2f5a3a;
    --bg:            #f8f7f3;
    --bg-rail:       #fbfaf6;
    --border:        #e6e3da;
    --ink:           #1c2a22;
    --muted:         #6a7268;
  }

  html, body, [class*="css"] {
    font-family: 'Geist', system-ui, -apple-system, sans-serif !important;
    color: var(--ink);
  }

  /* Tighten default Streamlit padding so the layout feels app-like */
  .main .block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 100%;
  }

  /* ── Top brand bar ─────────────────────────────────────────── */
  .brand-bar {
    display: flex; align-items: center; gap: 14px;
    padding: 6px 0 14px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 18px;
  }
  .brand-mark {
    width: 34px; height: 34px; border-radius: 9px;
    background: var(--accent); color: #fff;
    display: grid; place-items: center;
    font-family: 'Geist Mono', monospace;
    font-weight: 700; font-size: 16px;
  }
  .brand-title {
    font-size: 18px; font-weight: 600; letter-spacing: -0.01em;
  }
  .brand-sub {
    color: var(--muted); font-weight: 400; font-size: 14px; margin-left: 6px;
  }
  .brand-right {
    margin-left: auto; display: flex; align-items: center; gap: 16px;
    font-size: 12.5px; color: var(--muted);
  }
  .brand-right a { color: var(--muted); text-decoration: none; }
  .brand-right a:hover { color: var(--ink); }

  /* ── Section labels (left + right rails) ───────────────────── */
  .section-label {
    font-size: 10.5px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--muted);
    margin: 18px 0 8px 0;
  }

  /* ── Cards ─────────────────────────────────────────────────── */
  .card {
    border: 1px solid var(--border); border-radius: 12px;
    background: #fff; padding: 14px 16px 16px;
    margin-bottom: 14px;
  }
  .card-title {
    display: flex; align-items: center; justify-content: space-between;
    font-size: 13px; font-weight: 600; margin-bottom: 12px; color: var(--ink);
  }
  .card-badge {
    font-size: 10.5px; font-weight: 500; padding: 3px 9px; border-radius: 999px;
    background: var(--accent-soft); color: var(--accent-soft-ink);
  }
  .card-badge.warn { background: #fbf1d8; color: #8a6a1a; }
  .card-badge.bad  { background: #fbe1d8; color: #8a3a1a; }

  .card.dashed {
    background: var(--bg-rail);
    border-style: dashed;
  }

  /* Safety rows inside pre-flight card */
  .safety-row {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 9px 0;
    border-bottom: 1px solid #f1efe7;
  }
  .safety-row:last-child { border-bottom: 0; }
  .safety-icon {
    width: 20px; height: 20px; border-radius: 50%;
    flex-shrink: 0; margin-top: 1px;
    display: grid; place-items: center;
    color: #fff; font-size: 11.5px; font-weight: 700;
  }
  .safety-icon.ok   { background: var(--accent); }
  .safety-icon.warn { background: #d4a23a; }
  .safety-icon.bad  { background: #c25636; }
  .safety-title { font-size: 12.5px; font-weight: 500; color: var(--ink); line-height: 1.3; }
  .safety-sub   { font-size: 11px; color: var(--muted); margin-top: 2px;
                  font-family: 'Geist Mono', monospace; }

  /* Output key-value rows */
  .kv-row {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 5px 0; font-size: 12.5px; color: #3d473e;
  }
  .kv-val {
    font-family: 'Geist Mono', monospace; color: var(--ink); font-weight: 500;
  }

  /* ── File source pill above the map ────────────────────────── */
  .file-bar {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 10px 14px;
    background: var(--bg-rail);
    border: 1px solid var(--border);
    border-radius: 10px 10px 0 0;
    border-bottom: none;
    font-size: 12.5px; color: var(--muted);
  }
  .file-bar .label {
    font-family: 'Geist Mono', monospace; font-size: 11px; color: var(--muted);
  }
  .file-pill {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 3px 12px 3px 4px; border-radius: 999px;
    background: var(--accent-soft); color: var(--accent-soft-ink);
    font-size: 12px; font-weight: 500;
  }
  .file-dot {
    width: 20px; height: 20px; border-radius: 50%;
    background: var(--accent); color: #fff;
    display: inline-grid; place-items: center;
    font-family: 'Geist Mono', monospace; font-size: 10px; font-weight: 700;
  }

  /* ── Map metrics strip below the map ───────────────────────── */
  .metric-strip {
    display: flex; gap: 8px; flex-wrap: wrap;
    padding: 12px 14px;
    background: var(--bg-rail);
    border: 1px solid var(--border);
    border-radius: 0 0 10px 10px;
    border-top: none;
    margin-bottom: 14px;
  }
  .metric-card {
    flex: 1; min-width: 110px;
    background: #fff; border: 1px solid var(--border);
    border-radius: 10px; padding: 9px 13px;
    display: flex; flex-direction: column; gap: 2px;
  }
  .metric-label {
    font-size: 9.5px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--muted);
  }
  .metric-value {
    font-family: 'Geist Mono', monospace;
    font-size: 18px; font-weight: 600; color: var(--ink); line-height: 1.1;
  }
  .metric-unit {
    font-family: 'Geist Mono', monospace;
    font-size: 11px; color: var(--muted); font-weight: 500;
  }

  /* ── Sidebar ───────────────────────────────────────────────── */
  section[data-testid="stSidebar"] {
    background: var(--bg-rail);
    border-right: 1px solid var(--border);
  }
  section[data-testid="stSidebar"] h1,
  section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3 {
    font-size: 15px !important;
    color: var(--ink) !important;
    letter-spacing: -0.01em;
    margin-bottom: 6px;
  }

  /* Inputs */
  div[data-baseweb="input"] > div,
  div[data-baseweb="select"] > div,
  textarea {
    border-radius: 8px !important;
    border-color: var(--border) !important;
    background: #fff !important;
  }
  .stNumberInput input, .stTextInput input {
    font-family: 'Geist Mono', monospace !important;
    font-size: 13px !important;
  }

  /* Primary button = filled accent */
  .stButton > button[kind="primary"],
  .stDownloadButton > button[kind="primary"] {
    background: var(--accent-ink) !important;
    border: none !important;
    color: #fff !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 10px 14px !important;
    box-shadow: 0 1px 0 rgba(255,255,255,0.1) inset, 0 4px 14px rgba(60,110,80,0.18) !important;
  }
  .stButton > button[kind="primary"]:hover,
  .stDownloadButton > button[kind="primary"]:hover {
    background: var(--accent) !important;
  }

  /* Secondary button */
  .stButton > button:not([kind="primary"]) {
    background: #fff !important;
    border: 1px solid var(--border) !important;
    color: var(--accent-soft-ink) !important;
    border-radius: 9px !important;
    font-weight: 500 !important;
  }

  /* File uploader chrome */
  div[data-testid="stFileUploaderDropzone"] {
    background: var(--bg-rail);
    border: 1px dashed var(--border);
    border-radius: 10px;
  }

  /* Alerts (st.warning / st.error) */
  div[data-testid="stAlert"] {
    border-radius: 10px;
    border: 1px solid var(--border);
  }

  /* Headings inside main area */
  h1, h2, h3 { letter-spacing: -0.01em; }
  h2 { font-size: 18px !important; }
  h3 { font-size: 15px !important; color: var(--ink); }

  /* Hide Streamlit's default footer & main-menu chrome for a cleaner app */
  footer { visibility: hidden; }
  #MainMenu { visibility: hidden; }

  /* Custom footer */
  .app-footer {
    margin-top: 24px;
    padding: 12px 0;
    border-top: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
    font-size: 11.5px; color: var(--muted);
  }
  .app-footer .mono { font-family: 'Geist Mono', monospace; }
</style>
"""


def render_brand_bar() -> None:
    st.markdown(
        f"""
        <div class="brand-bar">
          <div class="brand-mark">W</div>
          <div>
            <span class="brand-title">Waypoint</span>
            <span class="brand-sub">· DJI Mission Builder</span>
          </div>
          <div class="brand-right">
            <span>{APP_VERSION}</span>
            <a href="{REPO_URL}" target="_blank">GitHub ↗</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sidebar — mission configuration
# ---------------------------------------------------------------------------

def render_sidebar(points: list[Point] | None) -> MissionConfig:
    st.sidebar.markdown(
        "<div class='section-label' style='margin-top:0'>Mission identity</div>",
        unsafe_allow_html=True,
    )
    mission_name = st.sidebar.text_input(
        "Mission name", value="Waypoint Survey", key="mission_name"
    )
    pilot_name = st.sidebar.text_input("Pilot", value="pilot", key="pilot_name")
    drone_model = st.sidebar.selectbox(
        "Drone model",
        ["M3M", "M3E", "M4E (encoded as M3E)"],
        key="drone_model",
        help=(
            "M4E is not yet natively supported by djikmz; it is encoded as M3E. "
            "DJI Pilot 2 will prompt to re-bind on import — accept."
        ),
    )

    st.sidebar.markdown(
        "<div class='section-label'>Flight</div>", unsafe_allow_html=True
    )
    c1, c2 = st.sidebar.columns(2)
    with c1:
        speed_mps = st.number_input(
            "Cruise (m/s)",
            min_value=0.5, max_value=20.0, value=5.0, step=0.5,
            key="speed_mps",
        )
    with c2:
        hover_sec = st.number_input(
            "Hover (s)",
            min_value=0.0, max_value=30.0, value=2.0, step=0.5,
            key="hover_sec",
            help="Seconds to hover before each photo.",
        )

    st.sidebar.markdown(
        "<div class='section-label'>Altitude</div>", unsafe_allow_html=True
    )
    agl_unit = st.sidebar.radio(
        "Unit", ["feet", "metres"], horizontal=True, key="agl_unit"
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

    st.sidebar.markdown(
        "<div class='section-label'>Camera</div>", unsafe_allow_html=True
    )
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

    st.sidebar.markdown(
        "<div class='section-label'>Terrain</div>", unsafe_allow_html=True
    )
    terrain_follow = st.sidebar.checkbox(
        "Terrain following",
        value=False,
        help=(
            "Keeps AGL constant above local ground. Needs per-point elevations "
            "in the input AND a takeoff elevation."
        ),
        key="terrain_follow",
    )

    default_takeoff = 0.0
    erange = elevation_range(points) if points else None
    if erange is not None:
        default_takeoff = round(erange[0], 2)
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
# Main panel — upload, map, metrics, pre-flight, output
# ---------------------------------------------------------------------------

def render_upload() -> Path | None:
    st.markdown("### 1 — Upload your sampling points")
    st.caption(
        "CSV, KML, GeoJSON, or a .zip containing a Shapefile "
        "(.shp + .shx + .dbf + .prj)."
    )

    col_up, col_sample = st.columns([3, 1])
    with col_up:
        uploaded = st.file_uploader(
            "Drop a file",
            type=["csv", "kml", "geojson", "json", "zip"],
            accept_multiple_files=False,
            key="uploader",
            label_visibility="collapsed",
        )
    with col_sample:
        if st.button(
            "Try sample data",
            width="stretch",
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
        return SAMPLE_PATH

    st.info(
        "Drop a points file above, or click **Try sample data** to explore. "
        "CSVs should have columns `id`, `lat`, `lon`, `elevation` (WGS-84)."
    )
    return None


def render_file_bar(src_path: Path, points: list[Point]) -> None:
    name = html.escape(src_path.name)
    n = len(points)
    has_elev = any(p.elevation_m is not None for p in points)
    elev_tag = "· elevation present" if has_elev else "· no elevation"
    st.markdown(
        f"""
        <div class="file-bar">
          <span class="label">Source</span>
          <span class="file-pill">
            <span class="file-dot">✓</span>
            {name} — {n} waypoints
          </span>
          <span>· WGS-84 {elev_tag}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_map(points: list[Point]) -> None:
    try:
        st.map(
            data=[{"lat": p.lat, "lon": p.lon} for p in points],
            zoom=14,
            color="#5b8a5a",
            size=12,
            width="stretch",
        )
    except Exception as exc:  # noqa: BLE001 - map is non-critical preview
        st.caption(f"Map preview unavailable ({exc.__class__.__name__}).")


def render_metric_strip(points: list[Point], config: MissionConfig,
                        agl_unit: str) -> None:
    distance_m = path_length_m(points)
    eta = estimate_flight_seconds(points, config.speed_mps, config.hover_sec)
    erange = elevation_range(points)
    delta_elev = (erange[1] - erange[0]) if erange else None

    if agl_unit == "feet":
        agl_disp = f"{config.agl_m / FT_TO_M:.0f}"
        agl_unit_lbl = " ft"
    else:
        agl_disp = f"{config.agl_m:.1f}"
        agl_unit_lbl = " m"

    delta_html = (
        f'<span class="metric-value">{delta_elev:.1f}'
        f'<span class="metric-unit"> m</span></span>'
        if delta_elev is not None
        else '<span class="metric-value">—</span>'
    )

    st.markdown(
        f"""
        <div class="metric-strip">
          <div class="metric-card">
            <span class="metric-label">Waypoints</span>
            <span class="metric-value">{len(points)}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Path length</span>
            <span class="metric-value">{distance_m:,.0f}<span class="metric-unit"> m</span></span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Flight time</span>
            <span class="metric-value">{format_duration(eta)}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Δ Elev.</span>
            {delta_html}
          </div>
          <div class="metric-card">
            <span class="metric-label">AGL</span>
            <span class="metric-value">{agl_disp}<span class="metric-unit">{agl_unit_lbl}</span></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _safety_checks(points: list[Point], config: MissionConfig) -> list[dict]:
    erange = elevation_range(points)
    delta_elev = (erange[1] - erange[0]) if erange else 0.0
    eta_min = estimate_flight_seconds(
        points, config.speed_mps, config.hover_sec
    ) / 60.0
    battery_pct = (eta_min / M3M_ENDURANCE_MIN) * 100 if M3M_ENDURANCE_MIN else 0

    checks: list[dict] = []

    # FAA Part 107 ceiling
    margin_pct = max(0.0, (1 - config.agl_m / PART_107_CEILING_M) * 100)
    if config.agl_m > PART_107_CEILING_M:
        checks.append(dict(
            tone="bad",
            title="FAA Part 107 ceiling exceeded",
            sub=f"{config.agl_m:.0f} m AGL · waiver required",
        ))
    elif config.agl_m > SOFT_WARN_AGL_M:
        checks.append(dict(
            tone="warn",
            title="FAA Part 107 ceiling — close to limit",
            sub=f"{config.agl_m:.0f} m AGL · {margin_pct:.0f}% margin to 120 m",
        ))
    else:
        checks.append(dict(
            tone="ok",
            title="FAA Part 107 ceiling",
            sub=f"{config.agl_m:.1f} m AGL · {margin_pct:.0f}% margin to 120 m",
        ))

    # Terrain clearance
    if erange is None:
        checks.append(dict(
            tone="warn",
            title="Terrain clearance",
            sub="No per-point elevations in input",
        ))
    else:
        min_agl = config.agl_m - delta_elev
        if min_agl < 5:
            tone = "bad"
        elif min_agl < 15:
            tone = "warn"
        else:
            tone = "ok"
        checks.append(dict(
            tone=tone,
            title="Terrain clearance",
            sub=f"Min AGL {min_agl:.1f} m over Δ{delta_elev:.1f} m",
        ))

    # Battery
    if battery_pct > 80:
        tone = "bad"
    elif battery_pct > 50:
        tone = "warn"
    else:
        tone = "ok"
    checks.append(dict(
        tone=tone,
        title="Mission within battery",
        sub=f"~{battery_pct:.0f}% of a single M3M pack ({eta_min:.1f} min)",
    ))

    # Takeoff elevation source
    if config.terrain_follow:
        checks.append(dict(
            tone="warn",
            title="Takeoff elevation source",
            sub="Auto · verify on nationalmap.gov",
        ))
    else:
        checks.append(dict(
            tone="ok",
            title="Terrain following",
            sub="Disabled · constant AGL above takeoff",
        ))

    return checks


def render_preflight_card(points: list[Point], config: MissionConfig) -> None:
    checks = _safety_checks(points, config)
    ok_count = sum(1 for c in checks if c["tone"] == "ok")
    total = len(checks)
    bad = any(c["tone"] == "bad" for c in checks)
    badge_cls = "bad" if bad else ("warn" if ok_count < total else "")
    badge_text = f"{ok_count} / {total} OK"

    rows_html = "".join(
        f"""
        <div class="safety-row">
          <div class="safety-icon {c['tone']}">{'✓' if c['tone']=='ok' else ('!' if c['tone']=='warn' else '×')}</div>
          <div style="flex:1">
            <div class="safety-title">{html.escape(c['title'])}</div>
            <div class="safety-sub">{html.escape(c['sub'])}</div>
          </div>
        </div>
        """
        for c in checks
    )

    st.markdown(
        f"""
        <div class="card">
          <div class="card-title">
            Pre-flight check
            <span class="card-badge {badge_cls}">{badge_text}</span>
          </div>
          {rows_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_output_card(points: list[Point], config: MissionConfig) -> None:
    file_name = (config.mission_name or "mission").replace(" ", "_") + ".kmz"
    # Rough KMZ size estimate: ~0.6 KB header + ~0.4 KB per waypoint, compressed.
    est_kb = 0.6 + 0.4 * len(points)

    st.markdown(
        f"""
        <div class="card">
          <div class="card-title">Output</div>
          <div class="kv-row"><span>Format</span><span class="kv-val">DJI Pilot 2 KMZ</span></div>
          <div class="kv-row"><span>File name</span><span class="kv-val">{html.escape(file_name)}</span></div>
          <div class="kv-row"><span>Encoded as</span><span class="kv-val">{config.drone_model}</span></div>
          <div class="kv-row"><span>Est. size</span><span class="kv-val">~ {est_kb:.1f} KB</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "Build mission KMZ",
        type="primary",
        width="stretch",
        key="build_btn",
    ):
        with st.spinner("Building KMZ…"):
            try:
                with tempfile.TemporaryDirectory() as td:
                    out_path = Path(td) / file_name
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
    if result:
        st.success(
            f"Built `{result['file_name']}` with "
            f"{result['n_points']} waypoint(s)."
        )
        st.download_button(
            "⬇️ Download KMZ",
            data=result["kmz_bytes"],
            file_name=result["file_name"],
            mime="application/vnd.google-earth.kmz",
            type="primary",
            width="stretch",
            key="dl_btn",
        )
        st.caption(
            "Copy to your tablet → DJI Pilot 2 → Waypoint Mission → Import KMZ."
        )
    else:
        st.caption(
            "Open in DJI Pilot 2 → Waypoint Mission → Import KMZ after building."
        )


def render_about_card() -> None:
    st.markdown(
        f"""
        <div class="card dashed">
          <div style="font-family: 'Geist Mono', monospace; font-size: 11px;
                      color: var(--muted); margin-bottom: 6px;">About</div>
          <div style="font-size: 12.5px; color: var(--ink); line-height: 1.5;">
            Built by <strong>Mailson Freire de Oliveira</strong>,
            Water &amp; Cropping Systems Extension Educator,
            <span style="white-space:nowrap;">UNL IANR</span>.
            MIT licensed — please cite in scientific work.
            <br/><br/>
            <a href="{REPO_URL}" target="_blank"
               style="color: var(--accent-soft-ink);">GitHub repo ↗</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_waypoint_table(points: list[Point]) -> None:
    with st.expander(f"Show {len(points)} waypoint(s) as a table"):
        st.dataframe(
            [
                {"id": p.id, "lat": p.lat, "lon": p.lon,
                 "elevation_m": p.elevation_m}
                for p in points[:500]
            ],
            width="stretch",
        )
        if len(points) > 500:
            st.caption(f"Showing first 500 of {len(points)} rows.")


def render_footer() -> None:
    st.markdown(
        """
        <div class="app-footer">
          <span>UNL IANR · Mailson Freire de Oliveira · MIT licensed</span>
          <span class="mono">dji-waypoints · streamlit edition</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Waypoint — DJI Mission Builder",
        page_icon="🚁",
        layout="wide",
    )

    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    render_brand_bar()

    # Upload first so the sidebar can use loaded points (for default takeoff).
    src_path = render_upload()

    points: list[Point] = []
    load_error: str | None = None
    if src_path is not None:
        try:
            points = load_points(src_path)
        except Exception as exc:  # noqa: BLE001
            load_error = f"Could not read `{src_path.name}`: {exc}"

    config = render_sidebar(points if points else None)
    agl_unit = st.session_state.get("agl_unit", "feet")

    if load_error:
        st.error(load_error)
        render_footer()
        st.stop()
    if src_path is None:
        render_footer()
        st.stop()
    if not points:
        st.warning("The file was parsed but contained zero points.")
        render_footer()
        st.stop()

    # 2-column layout: map + metrics on the left, right rail on the right.
    col_center, col_right = st.columns([2, 1], gap="large")

    with col_center:
        st.markdown("### 2 — Preview")
        render_file_bar(src_path, points)
        render_map(points)
        render_metric_strip(points, config, agl_unit)
        render_waypoint_table(points)

    with col_right:
        st.markdown("### 3 — Build & download")
        render_preflight_card(points, config)
        render_output_card(points, config)
        render_about_card()

    render_footer()


if __name__ == "__main__":  # pragma: no cover
    main()
