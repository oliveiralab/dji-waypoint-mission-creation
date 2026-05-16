"""Streamlit web UI for dji-waypoints — redesigned 2026-05.

Run locally:
    pip install -e ".[web]"
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import math
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from dji_waypoints import MissionConfig, build_mission, load_points
from dji_waypoints.config import FT_TO_M
from dji_waypoints.readers import Point

# ── Constants ─────────────────────────────────────────────────────────────────
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "examples" / "sample_points.csv"
REPO_URL = "https://github.com/oliveiralab/dji-waypoint-mission-creation"
APP_URL  = "https://dji-waypoint-mission.streamlit.app/"
VERSION  = "0.4"

PART_107_CEILING_M = 121.92   # 400 ft AGL
SOFT_WARN_AGL_M    = 100.0
PHOTO_OVERHEAD_S   = 1.5      # gimbal settle + shutter per waypoint
M3M_ENDURANCE_S    = 23 * 60  # ≈23 min hover endurance

# ── Pure helpers ──────────────────────────────────────────────────────────────

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
    cruise    = path_length_m(points) / speed_mps
    per_point = (hover_sec + PHOTO_OVERHEAD_S) * len(points)
    return cruise + per_point


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}:{s:02d}"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}:{s:02d}"


def elevation_range(points: list[Point]) -> tuple[float, float] | None:
    elevs = [p.elevation_m for p in points if p.elevation_m is not None]
    return (min(elevs), max(elevs)) if elevs else None


def _save_upload(tmp_dir: Path, uploaded) -> Path:
    name   = uploaded.name
    ext    = Path(name).suffix.lower()
    target = tmp_dir / name
    target.write_bytes(uploaded.getvalue())
    if ext == ".zip":
        with zipfile.ZipFile(target) as zf:
            zf.extractall(tmp_dir)
        shp = next(tmp_dir.rglob("*.shp"), None)
        if shp is None:
            raise ValueError(
                "Uploaded .zip has no .shp file. "
                "Include .shp, .shx, .dbf and .prj together."
            )
        return shp
    return target


def battery_pct_estimate(
    points: list[Point], speed_mps: float, hover_sec: float
) -> float:
    """Rough battery % for a single M3M pack (~23 min hover endurance)."""
    secs = estimate_flight_seconds(points, speed_mps, hover_sec)
    return round(secs / M3M_ENDURANCE_S * 100, 1)


# ── CSS injection ─────────────────────────────────────────────────────────────

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600;700&display=swap');

/* ── Reset Streamlit chrome ── */
#MainMenu,
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDeployButton"],
footer { display: none !important; }

.block-container   { padding: 0 !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] > div { padding: 0 !important; }
.stApp { background: #f7f9f4; font-family: 'Geist', system-ui, sans-serif; color: #1c2a22; }

/* ── Sidebar (left config rail) ── */
[data-testid="stSidebar"] {
  background: #fafbf7 !important;
  border-right: 1px solid #e6ebe0 !important;
  min-width: 290px !important;
  max-width: 290px !important;
}
[data-testid="stSidebar"] > div:first-child { background: #fafbf7 !important; }
[data-testid="stSidebarContent"] { padding: 20px 18px 32px !important; }
[data-testid="stSidebarUserContent"] { padding: 0 !important; }
button[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarNavSeparator"] { display: none !important; }
[data-testid="stSidebarNav"] { display: none !important; }

/* ── Section labels ── */
.wpt-sec {
  font-size: 10.5px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.1em; color: #7a8f80;
  margin: 0 0 10px; padding-top: 18px;
  display: flex; justify-content: space-between; align-items: center;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-sec:first-of-type { padding-top: 0; }
.wpt-sec-action {
  font-size: 10.5px; color: #3d9957; cursor: pointer;
  text-transform: none; letter-spacing: 0; font-weight: 500;
  font-family: 'Geist Mono', monospace;
}
.wpt-divider {
  border: none; border-top: 1px solid #e6ebe0;
  margin: 4px 0 16px;
}
/* Unit toggle */
.wpt-unit-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
.wpt-unit-label { font-size: 12px; color: #556a5c; font-weight: 500; }
.wpt-unit-toggle {
  display: inline-flex; border: 1px solid #e0e8d8;
  border-radius: 7px; padding: 2px; background: white;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-unit-pill {
  padding: 3px 10px; border-radius: 5px; font-size: 11.5px;
  cursor: pointer; border: none;
}
.wpt-unit-pill.active {
  background: #e3f2e9; color: #2a6b3d; font-weight: 600;
}
.wpt-unit-pill:not(.active) { background: transparent; color: #7a8f80; font-weight: 500; }

/* ── Top bar ── */
.wpt-topbar {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 24px; border-bottom: 1px solid #e6ebe0;
  background: #fafbf7; position: sticky; top: 0; z-index: 100;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-brand {
  display: flex; align-items: center; gap: 10px;
  font-weight: 600; font-size: 15px; letter-spacing: -0.01em; color: #1c2a22;
}
.wpt-brandmark {
  width: 28px; height: 28px; border-radius: 8px; background: #3d9957;
  display: grid; place-items: center; color: white;
  font-size: 14px; font-weight: 700; font-family: 'Geist Mono', monospace;
  flex-shrink: 0;
}
.wpt-brandsub   { color: #7a8f80; font-size: 13px; font-weight: 400; }
.wpt-crumbs     { margin-left: 18px; display: flex; align-items: center; gap: 8px; font-size: 12px; color: #7a8f80; }
.wpt-crumb-chip {
  padding: 3px 8px; border-radius: 5px; background: #edf2e8;
  font-family: 'Geist Mono', monospace; color: #1c2a22; font-size: 11.5px;
}
.wpt-topbar-right { margin-left: auto; display: flex; align-items: center; gap: 14px; font-size: 12px; color: #7a8f80; }
.wpt-ghostlink   { color: #7a8f80; text-decoration: none; padding: 4px 6px; border-radius: 6px; }
.wpt-ghostlink:hover { color: #1c2a22; background: #edf2e8; }
.wpt-version     { font-family: 'Geist Mono', monospace; font-size: 11px; }

/* ── File bar (center column) ── */
.wpt-file-bar {
  padding: 8px 18px; border-bottom: 1px solid #e6ebe0;
  background: #fafbf7; display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: #7a8f80; flex-wrap: wrap;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-file-pill {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 3px 12px 3px 4px; border-radius: 999px;
  background: #e3f2e9; color: #2a6b3d; font-size: 12px; font-weight: 500;
}
.wpt-file-dot {
  width: 18px; height: 18px; border-radius: 50%; background: #3d9957;
  display: grid; place-items: center; color: white;
  font-size: 10px; font-weight: 700; font-family: 'Geist Mono', monospace; flex-shrink: 0;
}

/* ── Metrics strip ── */
.wpt-metrics {
  display: flex; gap: 8px; padding: 12px 16px;
  background: #f7f9f4; border-top: 1px solid #e6ebe0; flex-wrap: wrap;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-metric {
  background: white; border-radius: 10px; padding: 9px 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); min-width: 88px;
  display: flex; flex-direction: column; gap: 2px;
  border: 1px solid #e6ebe0;
}
.wpt-metric-label  { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.1em; color: #7a8f80; font-weight: 600; }
.wpt-metric-val    { font-size: 18px; font-weight: 600; color: #1c2a22; font-family: 'Geist Mono', monospace; line-height: 1.1; }
.wpt-metric-unit   { font-size: 11px; color: #7a8f80; font-family: 'Geist Mono', monospace; font-weight: 500; }

/* ── Cards (right column) ── */
.wpt-card {
  border: 1px solid #e6ebe0; border-radius: 12px; padding: 16px;
  background: white; margin-bottom: 14px;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-card-title {
  font-size: 12.5px; font-weight: 600; color: #1c2a22; margin-bottom: 12px;
  display: flex; align-items: center; justify-content: space-between;
}
.wpt-badge-ok   { font-size: 10.5px; font-weight: 500; padding: 2px 8px; border-radius: 999px; background: #e3f2e9; color: #2a6b3d; }
.wpt-badge-warn { font-size: 10.5px; font-weight: 500; padding: 2px 8px; border-radius: 999px; background: #fef3c7; color: #92400e; }
.wpt-badge-err  { font-size: 10.5px; font-weight: 500; padding: 2px 8px; border-radius: 999px; background: #fee2e2; color: #991b1b; }

/* ── Safety rows ── */
.wpt-safety-row {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 9px 0; border-bottom: 1px solid #f0f4ec;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-safety-row:last-child { border-bottom: none; }
.wpt-safety-icon {
  width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0;
  display: grid; place-items: center; color: white;
  font-size: 11px; font-weight: 700; margin-top: 1px;
}
.wpt-si-ok   { background: #3d9957; }
.wpt-si-warn { background: #f59e0b; }
.wpt-si-err  { background: #ef4444; }
.wpt-safety-title { font-size: 12.5px; font-weight: 500; color: #1c2a22; line-height: 1.3; }
.wpt-safety-sub   { font-size: 11px; color: #7a8f80; margin-top: 2px; font-family: 'Geist Mono', monospace; }

/* ── kv rows (output card) ── */
.wpt-kv {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 5px 0; font-size: 12px; color: #556a5c;
  font-family: 'Geist', system-ui, sans-serif;
  border-bottom: 1px solid #f0f4ec;
}
.wpt-kv:last-child { border-bottom: none; }
.wpt-kv span:last-child { font-family: 'Geist Mono', monospace; color: #1c2a22; font-weight: 500; }

/* ── About card ── */
.wpt-about {
  border: 1px dashed #c8d8be; border-radius: 12px; padding: 14px 16px;
  background: #fafbf7; margin-bottom: 14px;
  font-family: 'Geist', system-ui, sans-serif;
}
.wpt-about-label { font-size: 11px; color: #7a8f80; font-family: 'Geist Mono', monospace; margin-bottom: 6px; }
.wpt-about-body  { font-size: 12px; color: #1c2a22; line-height: 1.5; }

/* ── Build hint ── */
.wpt-build-hint {
  text-align: center; font-size: 11px; color: #7a8f80; margin-top: 8px;
  line-height: 1.4; font-family: 'Geist Mono', monospace;
}

/* ── Footer ── */
.wpt-footer {
  padding: 10px 24px; border-top: 1px solid #e6ebe0;
  font-size: 11px; color: #7a8f80;
  display: flex; justify-content: space-between; align-items: center;
  background: #fafbf7; font-family: 'Geist', system-ui, sans-serif;
}
.wpt-footer span:last-child { font-family: 'Geist Mono', monospace; }

/* ── Streamlit widget overrides ── */
.stTextInput input,
.stNumberInput input {
  font-family: 'Geist Mono', monospace !important;
  border-radius: 7px !important;
  border: 1px solid #e0e8d8 !important;
  background: white !important;
  font-size: 13px !important;
  color: #1c2a22 !important;
}
.stTextInput input {
  font-family: 'Geist', system-ui, sans-serif !important;
}
.stTextInput input:focus,
.stNumberInput input:focus {
  border-color: rgba(61,153,87,0.5) !important;
  box-shadow: 0 0 0 2px rgba(61,153,87,0.12) !important;
  outline: none !important;
}
.stTextInput label, .stNumberInput label,
.stSelectbox label, .stSlider label, .stCheckbox label,
.stRadio label, .stFileUploader label {
  font-size: 12px !important;
  color: #556a5c !important;
  font-weight: 500 !important;
  font-family: 'Geist', system-ui, sans-serif !important;
}
/* Slider accent */
[data-testid="stSlider"] > div > div > div > div {
  background: #3d9957 !important;
}
/* Radio (unit) */
.stRadio [data-baseweb="radio"] div { border-color: #3d9957 !important; }
.stRadio [data-baseweb="radio"][aria-checked="true"] div { background: #3d9957 !important; }
/* Checkbox */
[data-baseweb="checkbox"] span {
  background-color: #3d9957 !important;
  border-color: #3d9957 !important;
}
/* Primary button */
.stButton > button[kind="primary"] {
  background: #1e4d2b !important;
  border: none !important;
  border-radius: 10px !important;
  font-family: 'Geist', system-ui, sans-serif !important;
  font-weight: 600 !important;
  font-size: 14px !important;
  padding: 11px 16px !important;
  color: white !important;
  box-shadow: 0 4px 14px rgba(30,77,43,0.18) !important;
  transition: background 150ms !important;
}
.stButton > button[kind="primary"]:hover { background: #2a6b3d !important; }
/* Secondary button */
.stButton > button[kind="secondary"] {
  background: white !important;
  border: 1px solid #e0e8d8 !important;
  border-radius: 9px !important;
  font-family: 'Geist', system-ui, sans-serif !important;
  font-weight: 500 !important;
  font-size: 13px !important;
  color: #3d9957 !important;
}
/* Download button */
.stDownloadButton > button {
  background: #3d9957 !important;
  border: none !important;
  border-radius: 10px !important;
  font-family: 'Geist', system-ui, sans-serif !important;
  font-weight: 600 !important;
  font-size: 14px !important;
  padding: 11px 16px !important;
  color: white !important;
  width: 100% !important;
  box-shadow: 0 4px 14px rgba(61,153,87,0.22) !important;
}
/* Expander */
[data-testid="stExpander"] summary {
  font-size: 12px !important; font-weight: 500 !important;
  color: #556a5c !important;
  font-family: 'Geist', system-ui, sans-serif !important;
}
/* Uploader dropzone */
[data-testid="stFileUploaderDropzone"] {
  border-radius: 9px !important;
  border: 1.5px dashed #c8d8be !important;
  background: #f7f9f4 !important;
  padding: 10px !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] {
  font-size: 12px !important;
  color: #7a8f80 !important;
  font-family: 'Geist', system-ui, sans-serif !important;
}
/* Info / success / warning boxes */
[data-testid="stAlert"] {
  border-radius: 9px !important;
  font-size: 12px !important;
  font-family: 'Geist', system-ui, sans-serif !important;
}
/* Dataframe */
[data-testid="stDataFrame"] { border-radius: 8px !important; overflow: hidden !important; }
/* Metric widget */
[data-testid="metric-container"] label { color: #7a8f80 !important; font-size: 11px !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: 'Geist Mono', monospace !important;
  font-size: 22px !important;
}
/* Selectbox */
[data-baseweb="select"] > div {
  border-radius: 7px !important;
  border-color: #e0e8d8 !important;
  font-family: 'Geist', system-ui, sans-serif !important;
  font-size: 13px !important;
}
</style>
"""


# ── Leaflet map component ─────────────────────────────────────────────────────

def _leaflet_map_html(points: list[Point], height: int = 400) -> str:
    """Return a self-contained Leaflet HTML string for the given points."""
    pts_json = json.dumps([
        {"id": p.id, "lat": p.lat, "lon": p.lon, "elev": p.elevation_m}
        for p in points
    ])
    return f"""
    <!doctype html><html><head>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <style>
      html, body {{ margin:0; padding:0; height:100%; background:#222; }}
      #map {{ position:absolute; inset:0; }}
      .wm {{ background:white; border:2.2px solid #3d9957; border-radius:50%;
             width:26px; height:26px; display:flex; align-items:center;
             justify-content:center; font:700 13px/1 'Geist Mono',monospace;
             color:#0e1a14; box-shadow:0 0 0 3px rgba(0,0,0,0.35); }}
      .bm-bar {{ position:absolute; top:12px; left:12px; z-index:1000;
                 display:flex; gap:3px; padding:3px;
                 background:rgba(255,255,255,0.96); border-radius:8px;
                 box-shadow:0 4px 14px rgba(0,0,0,0.15); }}
      .bm {{ padding:5px 10px; border-radius:5px; border:none; cursor:pointer;
              font-size:11.5px; font-weight:500; background:transparent;
              color:#555; font-family:system-ui,sans-serif; }}
      .bm.on {{ background:#e3f2e9; color:#2a6b3d; font-weight:600; }}
    </style></head><body>
    <div id="map"></div>
    <div class="bm-bar">
      <button class="bm on" onclick="setBM('sat',this)">satellite</button>
      <button class="bm"    onclick="setBM('topo',this)">terrain</button>
      <button class="bm"    onclick="setBM('osm',this)">streets</button>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      var PTS = {pts_json};
      var map = L.map('map', {{zoomControl:true}});
      var layers = {{
        sat:  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{attribution:'Esri'}}),
        topo: L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png', {{attribution:'OpenTopoMap', subdomains:'abc', maxZoom:17}}),
        osm:  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{attribution:'&copy; OpenStreetMap', subdomains:'abc'}})
      }};
      var cur = layers.sat;
      cur.addTo(map);
      function setBM(k, btn) {{
        map.removeLayer(cur); cur = layers[k]; cur.addTo(map); cur.bringToBack();
        document.querySelectorAll('.bm').forEach(b => b.classList.remove('on'));
        btn.classList.add('on');
      }}
      if (PTS.length > 0) {{
        var lls = PTS.map(p => [p.lat, p.lon]);
        // Path shadow + dashed line
        L.polyline(lls, {{color:'rgba(0,0,0,0.4)', weight:7, lineJoin:'round'}}).addTo(map);
        L.polyline(lls, {{color:'#3d9957', weight:2.8, dashArray:'9 6', opacity:0.95}}).addTo(map);
        // Takeoff approach
        var p0 = PTS[0];
        var to = [p0.lat - 0.00018, p0.lon - 0.00018];
        L.polyline([to, lls[0]], {{color:'rgba(255,255,255,0.8)', weight:1.5, dashArray:'3 5'}}).addTo(map);
        // Takeoff marker
        var toIcon = L.divIcon({{
          html: '<div style="width:22px;height:22px;border-radius:50%;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"><svg width=10 height=10><polygon points=\'5,1 9,9 1,9\' fill=white/></svg></div>',
          className:'', iconAnchor:[11,11]
        }});
        L.marker(to, {{icon:toIcon}}).bindTooltip('TAKEOFF', {{direction:'bottom'}}).addTo(map);
        // Numbered waypoint markers
        PTS.forEach(function(p) {{
          var ic = L.divIcon({{html:'<div class="wm">'+p.id+'</div>', className:'', iconAnchor:[13,13]}});
          var tip = 'WP ' + p.id + (p.elev != null ? ' &middot; '+p.elev.toFixed(1)+' m AMSL' : '');
          L.marker([p.lat,p.lon], {{icon:ic}}).bindTooltip(tip, {{direction:'top'}}).addTo(map);
        }});
        map.fitBounds(L.latLngBounds(lls), {{padding:[48, 48]}});
      }} else {{
        map.setView([40.617,-96.179], 15);
      }}
    </script></body></html>
    """


# ── Topbar ────────────────────────────────────────────────────────────────────

def _render_topbar(filename: str | None) -> None:
    crumb_html = (
        f'<span class="wpt-crumb-chip">{filename}</span>'
        if filename
        else '<span style="font-size:12px;color:#aab8b2;">no file loaded</span>'
    )
    st.markdown(f"""
    <div class="wpt-topbar">
      <div class="wpt-brand">
        <div class="wpt-brandmark">W</div>
        <span>Waypoint <span class="wpt-brandsub">· DJI Mission Builder</span></span>
      </div>
      <div class="wpt-crumbs">
        {crumb_html}
      </div>
      <div class="wpt-topbar-right">
        <span class="wpt-version">v{VERSION} &middot; open source</span>
        <a href="{APP_URL}" class="wpt-ghostlink" target="_blank">Docs</a>
        <a href="{REPO_URL}" class="wpt-ghostlink" target="_blank">GitHub &nearr;</a>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────

def _render_footer() -> None:
    today = date.today().isoformat()
    st.markdown(f"""
    <div class="wpt-footer">
      <span>UNL IANR &middot; Mailson Freire de Oliveira &middot; MIT licensed</span>
      <span>session {today} &middot; open source</span>
    </div>
    """, unsafe_allow_html=True)


# ── Sidebar config ────────────────────────────────────────────────────────────

def _sec(label: str, action: str | None = None) -> None:
    """Render a styled section label."""
    action_html = (
        f'<span class="wpt-sec-action">{action}</span>' if action else ""
    )
    st.markdown(
        f'<div class="wpt-sec">{label}{action_html}</div>',
        unsafe_allow_html=True,
    )


def render_config(points: list[Point] | None) -> MissionConfig:
    """Render config form in the sidebar; return a MissionConfig."""

    _sec("Mission identity")
    mission_name = st.text_input(
        "Mission name", value="Waypoint Survey", key="mission_name",
        label_visibility="visible",
    )
    pilot_name = st.text_input(
        "Pilot", value="pilot", key="pilot_name",
        label_visibility="visible",
    )
    drone_model = st.selectbox(
        "Drone model",
        ["M3M — Mavic 3 Multispectral", "M3E — Mavic 3 Enterprise", "M4E — encoded as M3E"],
        key="drone_model",
    )

    st.markdown('<hr class="wpt-divider"/>', unsafe_allow_html=True)
    _sec("Flight", action="defaults")
    col_a, col_b = st.columns(2, gap="small")
    with col_a:
        speed_mps = st.number_input(
            "Cruise speed (m/s)",
            min_value=0.5, max_value=20.0, value=5.0, step=0.5, key="speed_mps",
        )
    with col_b:
        hover_sec = st.number_input(
            "Hover (s)",
            min_value=0.0, max_value=30.0, value=2.0, step=0.5, key="hover_sec",
        )

    st.markdown('<hr class="wpt-divider"/>', unsafe_allow_html=True)
    _sec("Altitude")

    # Unit toggle via HTML buttons + session state
    if "agl_unit" not in st.session_state:
        st.session_state["agl_unit"] = "feet"

    agl_unit = st.session_state["agl_unit"]
    ft_active = 'class="wpt-unit-pill active"' if agl_unit == "feet"   else 'class="wpt-unit-pill"'
    m_active  = 'class="wpt-unit-pill active"' if agl_unit == "metres" else 'class="wpt-unit-pill"'
    st.markdown(f"""
    <div class="wpt-unit-row">
      <span class="wpt-unit-label">Unit</span>
      <div class="wpt-unit-toggle">
        <button {ft_active}
          onclick="window.parent.document.dispatchEvent(
            new CustomEvent('setAglUnit', {{detail:'feet'}}))">
          feet</button>
        <button {m_active}
          onclick="window.parent.document.dispatchEvent(
            new CustomEvent('setAglUnit', {{detail:'metres'}}))">
          metres</button>
      </div>
    </div>
    """, unsafe_allow_html=True)
    unit_radio = st.radio(
        "Height unit", ["feet", "metres"], horizontal=True, key="agl_unit",
        label_visibility="collapsed",
    )
    agl_unit = unit_radio

    if agl_unit == "feet":
        agl_ft = st.number_input(
            "Height above ground (ft)",
            min_value=1.0, max_value=400.0, value=85.0, step=1.0, key="agl_ft",
        )
        agl_m = agl_ft * FT_TO_M
        st.caption(f"= {agl_m:.2f} m")
    else:
        agl_m = st.number_input(
            "Height above ground (m)",
            min_value=0.5, max_value=200.0, value=25.91, step=0.5, key="agl_m_input",
        )
        st.caption(f"= {agl_m / FT_TO_M:.1f} ft")

    if agl_m > PART_107_CEILING_M:
        st.error(f"⚠️ {agl_m:.0f} m exceeds FAA Part 107 ceiling (120 m / 400 ft). Waiver required.")
    elif agl_m > SOFT_WARN_AGL_M:
        st.warning(f"{agl_m:.0f} m is close to the 120 m Part 107 ceiling.")

    st.markdown('<hr class="wpt-divider"/>', unsafe_allow_html=True)
    _sec("Camera")
    gimbal_pitch = st.slider(
        "Gimbal pitch — −90° nadir · 0° horizon",
        min_value=-90, max_value=0, value=-90, key="gimbal_pitch",
    )
    heading_deg = st.slider(
        "Heading — fixed compass bearing",
        min_value=0, max_value=359, value=0, key="heading_deg",
    )

    st.markdown('<hr class="wpt-divider"/>', unsafe_allow_html=True)
    _sec("Terrain")
    terrain_follow = st.checkbox(
        "Terrain following — keep AGL constant above local ground",
        value=False, key="terrain_follow",
    )

    default_takeoff = 0.0
    erange = elevation_range(points) if points else None
    if erange is not None:
        default_takeoff = round(erange[0], 2)
    takeoff_key = f"takeoff_elev::{default_takeoff:.2f}"
    takeoff_elev = st.number_input(
        "Takeoff elevation · AMSL (m)",
        min_value=-500.0, max_value=9000.0,
        value=default_takeoff, step=0.1,
        key=takeoff_key,
        help="Auto-filled from the minimum point elevation. Verify at nationalmap.gov.",
    )
    if terrain_follow and erange is None:
        st.warning("Terrain following needs per-point elevations in your file.")

    drone_str = "M3E" if drone_model.startswith("M4E") else drone_model.split(" ")[0]
    return MissionConfig(
        drone_model=drone_str,
        pilot_name=pilot_name,
        mission_name=mission_name,
        agl_m=agl_m,
        speed_mps=float(speed_mps),
        hover_sec=float(hover_sec),
        gimbal_pitch=float(gimbal_pitch),
        heading_deg=float(heading_deg),
        terrain_follow=terrain_follow,
        takeoff_elevation_m=(
            takeoff_elev if terrain_follow and takeoff_elev != 0.0 else None
        ),
    )


# ── Pre-flight check helpers ──────────────────────────────────────────────────

def _safety_row(tone: str, title: str, sub: str) -> str:
    glyph = {"ok": "&#10003;", "warn": "!", "err": "&times;"}[tone]
    return (
        f'<div class="wpt-safety-row">'
        f'  <div class="wpt-safety-icon wpt-si-{tone}">{glyph}</div>'
        f'  <div>'
        f'    <div class="wpt-safety-title">{title}</div>'
        f'    <div class="wpt-safety-sub">{sub}</div>'
        f'  </div>'
        f'</div>'
    )


def _preflight_html(
    points: list[Point],
    config: MissionConfig,
    erange: tuple[float, float] | None,
) -> str:
    rows: list[str] = []
    ok_count = 0

    # 1) FAA Part 107 ceiling
    margin_pct = round((1 - config.agl_m / PART_107_CEILING_M) * 100)
    agl_ft = round(config.agl_m / FT_TO_M, 1)
    if config.agl_m > PART_107_CEILING_M:
        tone = "err"
        sub  = f"{agl_ft} ft AGL &mdash; exceeds 400 ft ceiling"
    else:
        tone = "ok"; ok_count += 1
        sub  = f"{agl_ft} ft AGL &middot; {margin_pct}% margin to 400 ft"
    rows.append(_safety_row(tone, "FAA Part 107 ceiling", sub))

    # 2) Terrain clearance
    if erange is not None and config.terrain_follow:
        delta = erange[1] - erange[0]
        min_agl = config.agl_m - delta
        tone = "ok" if min_agl > 10 else "warn"; ok_count += (1 if tone == "ok" else 0)
        sub  = f"Min AGL {min_agl / FT_TO_M:.1f} ft over &Delta;{delta:.1f} m terrain"
    elif erange is not None:
        delta = erange[1] - erange[0]
        tone  = "ok"; ok_count += 1
        sub   = f"Flat AGL &middot; &Delta;{delta:.1f} m elevation spread"
    else:
        tone = "warn"
        sub  = "No per-point elevations &mdash; terrain unknown"
    rows.append(_safety_row(tone, "Terrain clearance", sub))

    # 3) Battery estimate
    batt = battery_pct_estimate(points, config.speed_mps, config.hover_sec)
    if batt > 90:
        tone = "warn"; sub = f"~{batt}% of a single M3M pack &mdash; consider splitting"
    elif batt > 100:
        tone = "err";  sub = f"~{batt}% &mdash; multi-battery mission required"
    else:
        tone = "ok"; ok_count += 1; sub = f"~{batt}% of a single M3M pack"
    rows.append(_safety_row(tone, "Mission within battery", sub))

    # 4) Takeoff elevation source
    if config.takeoff_elevation_m is not None:
        tone = "ok"; ok_count += 1
        sub  = f"Manual &middot; {config.takeoff_elevation_m:.1f} m AMSL"
    elif erange is not None:
        tone = "warn"
        sub  = f"Auto &middot; min point elevation {erange[0]:.1f} m &mdash; verify on nationalmap.gov"
    else:
        tone = "warn"
        sub  = "Auto &middot; verify takeoff elevation at nationalmap.gov"
    rows.append(_safety_row(tone, "Takeoff elevation source", sub))

    total = len(rows)
    badge_cls = "wpt-badge-ok" if ok_count == total else "wpt-badge-warn"
    badge_txt = f"{ok_count} / {total} OK"
    header = (
        f'<div class="wpt-card-title">Pre-flight check '
        f'<span class="{badge_cls}">{badge_txt}</span></div>'
    )
    return f'<div class="wpt-card">{header}{" ".join(rows)}</div>'


# ── Output summary card ───────────────────────────────────────────────────────

def _output_card_html(
    points: list[Point] | None,
    config: MissionConfig | None,
    built: bool,
) -> str:
    if points is None or config is None:
        return (
            '<div class="wpt-card">'
            '<div class="wpt-card-title">Output</div>'
            '<p style="font-size:12px;color:#7a8f80;margin:0;">Load a file to preview output details.</p>'
            '</div>'
        )
    safe_name = (config.mission_name or "mission").replace(" ", "_")
    fname = f"{safe_name}.kmz"
    est_kb = round(len(points) * 0.7 + 1.5, 1)
    drone_enc = config.drone_model
    rows = (
        f'<div class="wpt-kv"><span>Format</span><span>DJI Pilot 2 KMZ</span></div>'
        f'<div class="wpt-kv"><span>File name</span><span>{fname}</span></div>'
        f'<div class="wpt-kv"><span>Encoded as</span><span>{drone_enc}</span></div>'
        f'<div class="wpt-kv"><span>Waypoints</span><span>{len(points)}</span></div>'
        f'<div class="wpt-kv"><span>Est. size</span><span>~{est_kb} KB</span></div>'
    )
    return f'<div class="wpt-card"><div class="wpt-card-title">Output</div>{rows}</div>'


# ── Metrics strip ─────────────────────────────────────────────────────────────

def _metrics_html(
    points: list[Point],
    config: MissionConfig,
    erange: tuple[float, float] | None,
) -> str:
    n_pts     = len(points)
    dist_m    = path_length_m(points)
    eta       = estimate_flight_seconds(points, config.speed_mps, config.hover_sec)
    eta_str   = format_duration(eta)
    delta_elev = f"{erange[1] - erange[0]:.1f}" if erange else "n/a"
    agl_ft     = round(config.agl_m / FT_TO_M)
    agl_str    = f"{agl_ft} ft" if st.session_state.get("agl_unit", "feet") == "feet" else f"{config.agl_m:.1f} m"

    def card(label, val, unit=""):
        unit_html = f'<span class="wpt-metric-unit">{unit}</span>' if unit else ""
        return (
            f'<div class="wpt-metric">'
            f'<span class="wpt-metric-label">{label}</span>'
            f'<span class="wpt-metric-val">{val}{unit_html}</span>'
            f'</div>'
        )

    cards = (
        card("Waypoints", n_pts) +
        card("Path length", f"{dist_m:,.0f}", "m") +
        card("Flight time", eta_str) +
        card("&Delta; Elev.", delta_elev, "m" if erange else "") +
        card("AGL", agl_str)
    )
    return f'<div class="wpt-metrics">{cards}</div>'


# ── Main app entry point ──────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Waypoint — DJI Mission Builder",
        page_icon="🚁",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inject CSS
    st.markdown(CSS, unsafe_allow_html=True)

    # ── Resolve file ────────────────────────────────────────────────────────
    # File state persists across reruns via session_state.
    if "src_path" not in st.session_state:
        st.session_state["src_path"]  = None
        st.session_state["src_name"]  = None
        st.session_state["use_sample"] = False

    points:     list[Point] = []
    load_error: str | None  = None

    # Load points from whatever is currently selected
    src_path: Path | None = st.session_state.get("src_path")
    if src_path and src_path.exists():
        try:
            points = load_points(src_path)
        except Exception as exc:
            load_error = str(exc)

    # ── Sidebar config ──────────────────────────────────────────────────────
    with st.sidebar:
        config = render_config(points if points else None)

        st.markdown('<hr class="wpt-divider"/>', unsafe_allow_html=True)
        with st.expander("About"):
            st.markdown(
                f"Built by **Mailson Freire de Oliveira**, "
                f"Water & Cropping Systems Extension Educator, "
                f"University of Nebraska–Lincoln, IANR.\n\n"
                f"[GitHub repo]({REPO_URL}) · MIT licensed\n\n"
                f"Please cite in scientific work."
            )

    # ── Top bar ─────────────────────────────────────────────────────────────
    _render_topbar(st.session_state.get("src_name"))

    # ── Main body: center (map) + right (pre-flight / build) ────────────────
    col_center, col_right = st.columns([3, 1], gap="small")

    # ── CENTER COLUMN ───────────────────────────────────────────────────────
    with col_center:
        # File upload bar
        st.markdown('<div class="wpt-file-bar">', unsafe_allow_html=True)
        up_col, btn_col = st.columns([4, 1], gap="small")
        with up_col:
            uploaded = st.file_uploader(
                "Upload points",
                type=["csv", "kml", "geojson", "json", "zip"],
                key="uploader",
                label_visibility="collapsed",
            )
        with btn_col:
            if st.button("Sample data", use_container_width=True,
                         help="Load the 6-point demo CSV."):
                st.session_state["use_sample"] = True
                st.session_state["src_path"]   = SAMPLE_PATH if SAMPLE_PATH.exists() else None
                st.session_state["src_name"]   = SAMPLE_PATH.name if SAMPLE_PATH.exists() else None
                st.session_state.pop("result", None)
                st.rerun()

        if uploaded is not None:
            tmp = Path(tempfile.gettempdir()) / "_dji_upload"
            tmp.mkdir(exist_ok=True)
            try:
                saved = _save_upload(tmp, uploaded)
                st.session_state["src_path"]   = saved
                st.session_state["src_name"]   = uploaded.name
                st.session_state["use_sample"] = False
                st.session_state.pop("result", None)
                src_path = saved
                try:
                    points = load_points(src_path)
                    load_error = None
                except Exception as exc:
                    load_error = str(exc)
            except Exception as exc:
                st.error(f"Could not stage upload: {exc}")
        st.markdown('</div>', unsafe_allow_html=True)

        # File pill (shown after a file is loaded)
        src_name = st.session_state.get("src_name")
        if src_name and points:
            pill = (
                f'<div class="wpt-file-bar">'
                f'<span>Source</span>'
                f'<span class="wpt-file-pill">'
                f'<span class="wpt-file-dot">&#10003;</span>'
                f'{src_name} &mdash; {len(points)} waypoint{"s" if len(points) != 1 else ""}'
                f'</span>'
                f'<span>· WGS-84'
                + (" · elevation present" if elevation_range(points) else " · no elevation")
                + '</span></div>'
            )
            st.markdown(pill, unsafe_allow_html=True)

        # Load error
        if load_error:
            st.error(f"Could not read `{src_name}`: {load_error}")

        # ── Map ─────────────────────────────────────────────────────────────
        if points:
            map_html = _leaflet_map_html(points, height=420)
            components.html(map_html, height=420, scrolling=False)

            # Metrics strip
            erange = elevation_range(points)
            st.markdown(
                _metrics_html(points, config, erange),
                unsafe_allow_html=True,
            )

            # Waypoints table (collapsible)
            with st.expander(f"Show {len(points)} waypoint(s) as table"):
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
        else:
            st.markdown(
                '<div style="padding:32px 20px;text-align:center;color:#7a8f80;'
                'font-size:13px;font-family:\'Geist\',system-ui,sans-serif;">'
                'Upload a file or click <strong>Sample data</strong> to preview a mission.'
                '<br><br>'
                '<span style="font-size:11px;font-family:\'Geist Mono\',monospace;">'
                'CSV &middot; KML &middot; GeoJSON &middot; Shapefile (.zip)'
                '</span></div>',
                unsafe_allow_html=True,
            )

    # ── RIGHT COLUMN ────────────────────────────────────────────────────────
    with col_right:
        if points:
            erange = elevation_range(points)

            # Pre-flight check card
            st.markdown(
                _preflight_html(points, config, erange),
                unsafe_allow_html=True,
            )

            # Output summary card (not yet built)
            result = st.session_state.get("result")
            if not result:
                st.markdown(
                    _output_card_html(points, config, built=False),
                    unsafe_allow_html=True,
                )

            # Build / Download
            if not result:
                if st.button(
                    "Build mission KMZ",
                    type="primary",
                    use_container_width=True,
                    key="build_btn",
                ):
                    with st.spinner("Building KMZ\u2026"):
                        try:
                            with tempfile.TemporaryDirectory() as td:
                                out_path = Path(td) / (
                                    f"{(config.mission_name or 'mission').replace(' ', '_')}.kmz"
                                )
                                build_mission(points, config, out_path)
                                st.session_state["result"] = {
                                    "kmz_bytes": out_path.read_bytes(),
                                    "file_name": out_path.name,
                                    "n_points":  len(points),
                                }
                        except Exception as exc:
                            st.session_state.pop("result", None)
                            st.error(f"Mission build failed: {exc}")
                st.markdown(
                    '<div class="wpt-build-hint">Open in DJI Pilot 2 &rarr; Waypoint Mission &rarr; Import KMZ</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.success(
                    f"Built `{result['file_name']}` with {result['n_points']} waypoint(s)."
                )
                st.download_button(
                    "\u2b07\ufe0f  Download KMZ",
                    data=result["kmz_bytes"],
                    file_name=result["file_name"],
                    mime="application/vnd.google-earth.kmz",
                    use_container_width=True,
                    key="dl_btn",
                )
                if st.button("Rebuild", use_container_width=True, key="rebuild_btn"):
                    st.session_state.pop("result", None)
                    st.rerun()
                st.markdown(
                    '<div class="wpt-build-hint">Copy to tablet &rarr; DJI Pilot 2 &rarr; Import KMZ</div>',
                    unsafe_allow_html=True,
                )

        else:
            # No file loaded — show placeholder cards
            st.markdown(
                _output_card_html(None, None, built=False),
                unsafe_allow_html=True,
            )

        # About card
        st.markdown(
            f'<div class="wpt-about">'
            f'<div class="wpt-about-label">About</div>'
            f'<div class="wpt-about-body">'
            f'Built by <strong>Mailson Freire de Oliveira</strong>, '
            f'Water &amp; Cropping Systems Extension, UNL IANR. '
            f'MIT licensed &mdash; please cite in scientific work.</div></div>',
            unsafe_allow_html=True,
        )

    # ── Footer ───────────────────────────────────────────────────────────────
    _render_footer()


if __name__ == "__main__":  # pragma: no cover
    main()
