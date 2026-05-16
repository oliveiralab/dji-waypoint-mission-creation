"""Input readers for KML, Shapefile, GeoJSON, and CSV point files.

All readers return a list of :class:`Point` objects with optional elevation.
Coordinates must be in WGS-84 geographic (EPSG:4326).
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Point:
    id: int
    lat: float
    lon: float
    elevation_m: float | None = None  # AMSL ground elevation if available


# --- KML ---------------------------------------------------------------------

_PLACEMARK_RE = re.compile(r"<Placemark[^>]*>(.*?)</Placemark>", re.DOTALL)
_ID_RE = re.compile(r'<SimpleData name="id">([\d.]+)</SimpleData>')
_ELEV_RE = re.compile(r'<SimpleData name="elevation">([\d.\-]+)</SimpleData>')
_COORD_RE = re.compile(r"<coordinates>\s*([\-\d.]+),([\-\d.]+)(?:,([\-\d.]+))?")


def read_kml(path: Path) -> list[Point]:
    text = Path(path).read_text(encoding="utf-8")
    points: list[Point] = []
    for body in _PLACEMARK_RE.findall(text):
        coord_m = _COORD_RE.search(body)
        if not coord_m:
            continue
        id_m = _ID_RE.search(body)
        elev_m = _ELEV_RE.search(body)
        pid = int(float(id_m.group(1))) if id_m else len(points) + 1
        lon = float(coord_m.group(1))
        lat = float(coord_m.group(2))
        # Prefer explicit SimpleData elevation; fall back to KML coord altitude.
        if elev_m:
            elev: float | None = float(elev_m.group(1))
        elif coord_m.group(3):
            elev = float(coord_m.group(3))
        else:
            elev = None
        points.append(Point(pid, lat, lon, elev))
    return points


# --- Shapefile ---------------------------------------------------------------

def read_shapefile(path: Path) -> list[Point]:
    import shapefile  # pyshp

    sf = shapefile.Reader(str(path))
    field_names = [f[0] for f in sf.fields[1:]]
    id_idx = field_names.index("id") if "id" in field_names else None
    elev_idx = None
    for candidate in ("elevation", "elev", "z"):
        if candidate in field_names:
            elev_idx = field_names.index(candidate)
            break

    points: list[Point] = []
    for i, sr in enumerate(sf.iterShapeRecords()):
        lon, lat = sr.shape.points[0]
        pid = int(sr.record[id_idx]) if id_idx is not None else i + 1
        elev = float(sr.record[elev_idx]) if elev_idx is not None else None
        points.append(Point(pid, lat, lon, elev))
    return points


# --- GeoJSON -----------------------------------------------------------------

def read_geojson(path: Path) -> list[Point]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    points: list[Point] = []
    features = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
    for i, feat in enumerate(features):
        geom = feat.get("geometry", {})
        if geom.get("type") != "Point":
            continue
        coords = geom["coordinates"]
        lon, lat = float(coords[0]), float(coords[1])
        elev = float(coords[2]) if len(coords) > 2 else None
        props = feat.get("properties") or {}
        pid = int(props.get("id", i + 1))
        if elev is None and "elevation" in props:
            elev = float(props["elevation"])
        points.append(Point(pid, lat, lon, elev))
    return points


# --- CSV ---------------------------------------------------------------------

def read_csv(path: Path) -> list[Point]:
    """Read a CSV with columns: id (optional), lat, lon, elevation (optional).

    Column names are case-insensitive. Common aliases accepted:
    lat/latitude, lon/lng/longitude, elev/elevation/z.
    """
    aliases = {
        "id": {"id", "fid", "point_id"},
        "lat": {"lat", "latitude", "y"},
        "lon": {"lon", "lng", "long", "longitude", "x"},
        "elev": {"elev", "elevation", "z", "alt", "altitude"},
    }

    def resolve(header: list[str], key: str) -> str | None:
        lower = {h.lower(): h for h in header}
        for cand in aliases[key]:
            if cand in lower:
                return lower[cand]
        return None

    points: list[Point] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        id_col = resolve(header, "id")
        lat_col = resolve(header, "lat")
        lon_col = resolve(header, "lon")
        elev_col = resolve(header, "elev")
        if not lat_col or not lon_col:
            raise ValueError(
                f"CSV {path} must have lat/lon columns. Got headers: {header}"
            )
        for i, row in enumerate(reader):
            pid = int(float(row[id_col])) if id_col and row.get(id_col) else i + 1
            lat = float(row[lat_col])
            lon = float(row[lon_col])
            elev = (
                float(row[elev_col])
                if elev_col and row.get(elev_col) not in (None, "")
                else None
            )
            points.append(Point(pid, lat, lon, elev))
    return points


# --- Dispatcher --------------------------------------------------------------

_READERS = {
    ".kml": read_kml,
    ".shp": read_shapefile,
    ".geojson": read_geojson,
    ".json": read_geojson,
    ".csv": read_csv,
}


def load_points(path: str | Path) -> list[Point]:
    """Load points from any supported file type, dispatched by extension."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in _READERS:
        raise ValueError(
            f"Unsupported input format '{ext}'. "
            f"Supported: {sorted(_READERS.keys())}"
        )
    return _READERS[ext](p)
