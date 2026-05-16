# DJI Waypoint Mission Creator

[![CI](https://github.com/mailson-unl/dji-waypoint-mission-creation/actions/workflows/ci.yml/badge.svg)](https://github.com/mailson-unl/dji-waypoint-mission-creation/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Convert GIS sampling points (**KML, Shapefile, GeoJSON, or CSV**) into **DJI Pilot 2 waypoint mission KMZ** files for autonomous drone surveys.

Designed for precision-agriculture and research workflows — stand counting, ground-truth comparison with multispectral platforms (Sentera FieldAgent, Pix4Dfields), repeatable multi-date surveys — but useful for any "fly to point, hover, take photo" mission.

---

## Features

- **No-code web app** — upload points, fill a form, download a KMZ ([screenshot below](#web-app-no-code))
- **Multiple input formats**: KML, Shapefile (`.shp`), GeoJSON, CSV
- **Terrain following**: constant AGL above local ground (constant GSD)
- **Flat-field mode**: constant height above takeoff (no elevation data needed)
- **Configurable photography**: any gimbal pitch, hover duration, heading, speed
- **CLI and Python API** — use as a script or import as a library
- **Tested** against Python 3.10 / 3.11 / 3.12

---

## Install

```bash
pip install git+https://github.com/mailson-unl/dji-waypoint-mission-creation
```

Or for local development:

```bash
git clone https://github.com/mailson-unl/dji-waypoint-mission-creation
cd dji-waypoint-mission-creation
pip install -e ".[dev]"
```

---

## Web app (no-code)

A Streamlit UI for non-programmers: upload a point file, tweak settings in the sidebar, see the mission on a map with stats (path length, ETA, AGL safety check), and download the KMZ.

### Use it online

The app is deployment-ready for **[Streamlit Community Cloud](https://share.streamlit.io)** (free). Once deployed, the public URL is added here so collaborators can just click and go — no install needed.

> **Maintainer note:** to publish, go to <https://share.streamlit.io>, sign in with GitHub, click **New app**, select this repo (`mailson-unl/dji-waypoint-mission-creation`), branch `master`, main file `app/streamlit_app.py`, and deploy. The repo already contains `requirements.txt` and `.streamlit/config.toml` so the cloud builder works out of the box.

### Run locally

```bash
pip install -e ".[web]"
streamlit run app/streamlit_app.py
```

Then open the URL Streamlit prints (default `http://localhost:8501`). Upload one of:

- **CSV** (simplest — columns `id, lat, lon, elevation`)
- **KML** or **GeoJSON**
- **Zipped Shapefile** — put `.shp + .shx + .dbf + .prj` in a single `.zip`

Or click **Try sample data** to load a built-in example. Pick your drone, height (ft or m), gimbal pitch, hover duration, etc., click **Build mission KMZ**, and download the result.

---

## Quick start — CLI

```bash
# Flat field, constant 30 ft AGL above takeoff
dji-mission build points.shp --out mission.kmz --drone M3M --agl-ft 30

# Hilly terrain: KML with per-point elevation, follow the terrain at 85 ft
dji-mission build points.kml --out mission.kmz --drone M3M --agl-ft 85 \
    --terrain-follow --takeoff-elevation-m 327.83

# CSV input, slower cruise, 3-second hover
dji-mission build points.csv --out mission.kmz --speed 4 --hover 3
```

Run `dji-mission build --help` for the full option list.

---

## Quick start — Python API

```python
from dji_waypoints import MissionConfig, build_mission, load_points

points = load_points("examples/sample_points.csv")

config = MissionConfig.from_ft(
    agl_ft=85.0,
    drone_model="M3M",
    pilot_name="myname",
    mission_name="Field A Survey",
    terrain_follow=True,
    takeoff_elevation_m=327.83,
)

build_mission(points, config, "mission.kmz")
```

A runnable example is in [examples/build_from_csv.py](examples/build_from_csv.py).

---

## Input formats

| Format | Extension | Notes |
|--------|-----------|-------|
| CSV | `.csv` | Columns: `id` (optional), `lat`, `lon`, `elevation` (optional). Aliases accepted (`latitude`, `lng`, `z`, etc.). |
| KML | `.kml` | QGIS exports with `<SimpleData name="elevation">` work out of the box. |
| Shapefile | `.shp` | Must be WGS-84 (EPSG:4326). Reads `id` and `elevation`/`elev`/`z` fields if present. |
| GeoJSON | `.geojson`, `.json` | Point features, WGS-84. Elevation from `coordinates[2]` or `properties.elevation`. |

---

## Mission configuration reference

All knobs available on `MissionConfig` (and the CLI):

| Field | Default | Description |
|-------|---------|-------------|
| `drone_model` | `"M3M"` | DJI drone enum string (see `djikmz` docs). |
| `pilot_name` | `"pilot"` | Pilot label written into KMZ. |
| `mission_name` | `"Waypoint Survey"` | Mission label shown in DJI Pilot 2. |
| `agl_m` | `25.908` | Height above ground in metres (85 ft). |
| `speed_mps` | `5.0` | Cruise speed between waypoints. |
| `hover_sec` | `2.0` | Hover at each point before photo (reduces motion blur). |
| `gimbal_pitch` | `-90.0` | −90° = nadir, 0° = horizon. |
| `heading_deg` | `0.0` | Fixed compass heading for repeatable image orientation. |
| `terrain_follow` | `False` | If True, adjust each waypoint so AGL is constant above the local ground. |
| `takeoff_elevation_m` | `None` | AMSL elevation (m) of the takeoff spot. Required for `terrain_follow=True` if points lack elevation. |

---

## Supported drones

| Drone | Status | Notes |
|-------|--------|-------|
| Mavic 3 Multispectral (M3M) | ✅ Tested | Default. |
| Mavic 3 Enterprise (M3E) | ✅ Tested | |
| Matrice 4E (M4E) | ⚠️ Workaround | `djikmz` lacks an M4E enum; missions are encoded as M3E. DJI Pilot 2 prompts to re-bind on import — accept. |
| Other Mavic / Matrice | 🔬 Untested | Likely works if `djikmz` recognises the model string. |

---

## Mission design rationale

| Feature | Why |
|---------|-----|
| Constant AGL | Same ground sample distance (GSD) at every point → comparable image quality. |
| Nadir gimbal (−90°) | Identical look angle → consistent stand-count and reflectance measurements. |
| Hover before photo | Eliminates motion blur at the moment of capture. |
| Fixed heading | Repeatable image orientation for multi-date comparisons. |

---

## Workflow

1. Export sampling points from QGIS (or any GIS) as one of the supported formats. Ensure coordinates are WGS-84 (EPSG:4326).
2. Run the CLI or a Python script to produce a `.kmz`.
3. Transfer the KMZ to your tablet/controller and open in **DJI Pilot 2 → Waypoint Mission → Import KMZ/KML**.
4. Verify the route on the in-app preview, then fly.

---

## Legacy scripts

The original task-specific scripts (`convert_to_dji.py`, `convert_to_dji_m4e_50ft.py`, `convert_to_dji_m3m_30ft_brucetest22.py`) still live at the repo root for reference. New users should prefer the package and CLI.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports, new input-format readers, and additional drone enums are all welcome.

---

## Citation

If you use this tool in scientific work, please credit the author:

> Freire de Oliveira, M. (2026). *DJI Waypoint Mission Creator* [software]. University of Nebraska–Lincoln, Institute of Agriculture and Natural Resources. https://github.com/mailson-unl/dji-waypoint-mission-creation

**BibTeX:**

```bibtex
@software{freiredeoliveira_dji_waypoint_2026,
  author  = {Freire de Oliveira, Mailson},
  title   = {DJI Waypoint Mission Creator},
  year    = {2026},
  url     = {https://github.com/mailson-unl/dji-waypoint-mission-creation},
  note    = {Water and Cropping Systems Extension Educator,
             University of Nebraska--Lincoln,
             Institute of Agriculture and Natural Resources}
}
```

---

## Author

**Mailson Freire de Oliveira** — Water and Cropping Systems Extension Educator
University of Nebraska–Lincoln, Institute of Agriculture and Natural Resources

---

## License

[MIT](LICENSE)
