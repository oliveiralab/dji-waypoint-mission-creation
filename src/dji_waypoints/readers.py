"""Input readers for KML, Shapefile, GeoJSON, and CSV point files.

All readers return a list of :class:`Point` objects with optional elevation.
Coordinates must be in WGS-84 geographic (EPSG:4326).
"""
from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path

# DJI Pilot 2 maximum waypoint count.
MAX_WAYPOINTS = 65535


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


# --- KMZ (zipped KML) --------------------------------------------------------

def read_kmz(path: Path) -> list[Point]:
    """Extract the first .kml inside a .kmz archive and parse it."""
    with zipfile.ZipFile(path, "r") as zf:
        kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            raise ValueError(f"No .kml file found inside {path}")
        kml_text = zf.read(kml_names[0]).decode("utf-8")
    # Parse the in-memory KML text directly.
    points: list[Point] = []
    for body in _PLACEMARK_RE.findall(kml_text):
        coord_m = _COORD_RE.search(body)
        if not coord_m:
            continue
        id_m = _ID_RE.search(body)
        elev_m = _ELEV_RE.search(body)
        pid = int(float(id_m.group(1))) if id_m else len(points) + 1
        lon = float(coord_m.group(1))
        lat = float(coord_m.group(2))
        if elev_m:
            elev: float | None = float(elev_m.group(1))
        elif coord_m.group(3):
            elev = float(coord_m.group(3))
        else:
            elev = None
        points.append(Point(pid, lat, lon, elev))
    return points


# --- Validation --------------------------------------------------------------

def validate_points(points: list[Point]) -> list[Point]:
    """Validate a list of points: bounds, duplicates, and max count.

    Raises
    ------
    ValueError
        If any coordinate is out of WGS-84 bounds or point count exceeds
        the DJI Pilot 2 limit.

    Warns (UserWarning)
        If duplicate coordinates are detected.
    """
    if len(points) > MAX_WAYPOINTS:
        raise ValueError(
            f"Too many waypoints ({len(points):,}). "
            f"DJI Pilot 2 supports at most {MAX_WAYPOINTS:,}."
        )

    for p in points:
        if not (-90.0 <= p.lat <= 90.0):
            raise ValueError(
                f"Point {p.id}: latitude {p.lat} is out of range [-90, 90]."
            )
        if not (-180.0 <= p.lon <= 180.0):
            raise ValueError(
                f"Point {p.id}: longitude {p.lon} is out of range [-180, 180]."
            )

    seen: set[tuple[float, float]] = set()
    duplicates: list[int] = []
    for p in points:
        coord = (p.lat, p.lon)
        if coord in seen:
            duplicates.append(p.id)
        else:
            seen.add(coord)

    if duplicates:
        warnings.warn(
            f"Duplicate coordinates detected at point(s): {duplicates}. "
            "This may indicate a data error.",
            stacklevel=2,
        )

    return points


# --- Dispatcher --------------------------------------------------------------

_READERS = {
    ".kml": read_kml,
    ".kmz": read_kmz,
    ".shp": read_shapefile,
    ".geojson": read_geojson,
    ".json": read_geojson,
    ".csv": read_csv,
}


def _chunked(items: list[Point], size: int) -> list[list[Point]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_elevations(points: list[Point], source: str = "srtm90m") -> list[Point]:
    """Populate missing point elevations using OpenTopoData.

    This is useful for terrain-following missions when the input points
    do not already carry elevation values.
    """
    sources = {"srtm90m", "aster30m", "worlddem"}
    if source not in sources:
        raise ValueError(
            f"Unsupported elevation source '{source}'. Supported: {sorted(sources)}"
        )

    missing = [p for p in points if p.elevation_m is None]
    if not missing:
        return points

    base_url = f"https://api.opentopodata.org/v1/{source}"
    for batch in _chunked(missing, 50):
        locations = "|".join(f"{p.lat},{p.lon}" for p in batch)
        url = f"{base_url}?locations={urllib.parse.quote(locations)}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "dji-waypoints/1.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)

        status = data.get("status")
        if status != "OK":
            raise ValueError(
                f"Elevation lookup failed: {status} - {data.get('error', 'unknown')}"
            )

        results = data.get("results", [])
        if len(results) != len(batch):
            raise ValueError(
                "Elevation lookup returned a different number of results than requested."
            )

        for p, result in zip(batch, results):
            # Individual results from OpenTopoData carry no "status" field;
            # only the top-level response does.  Just check the value.
            elev = result.get("elevation")
            if elev is not None:
                p.elevation_m = float(elev)

    return points


def load_points(path: str | Path) -> list[Point]:
    """Load points from any supported file type, dispatched by extension.

    Validates coordinates, checks for duplicates, and enforces the DJI
    waypoint count limit.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in _READERS:
        raise ValueError(
            f"Unsupported input format '{ext}'. "
            f"Supported: {sorted(_READERS.keys())}"
        )
    points = _READERS[ext](p)
    return validate_points(points)
