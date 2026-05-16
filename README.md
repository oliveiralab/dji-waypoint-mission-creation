# DJI Waypoint Mission Creator

Convert GIS sampling-point data (KML or Shapefile) into **DJI Pilot 2–compatible waypoint mission KMZ files** for autonomous drone surveys.

Designed for stand-count ground-truth comparison with multispectral sensors (e.g. Sentera FieldAgent). Each waypoint triggers a nadir photo after a brief hover, ensuring sharp, consistently oriented images at a constant GSD.

---

## Scripts

### `convert_to_dji.py` — M3M from KML with terrain following
Parses a QGIS-exported KML with per-point AMSL elevation and builds a mission where every waypoint flies at a **constant height above its own ground** (terrain following).

| Parameter | Default |
|-----------|---------|
| Drone | Mavic 3 Multispectral (M3M) |
| AGL | 85 ft (25.908 m) |
| Speed | 5 m/s |
| Hover | 2 s per point |
| Gimbal | −90° (nadir) |
| Heading | 0° (north) |

```
py convert_to_dji.py
```

---

### `convert_to_dji_m4e_50ft.py` — M4E from KML at 50 ft
Reuses the parsing and settings from `convert_to_dji.py` but targets the **Matrice 4E** at 50 ft AGL and a faster cruise speed.

> **Note:** `djikmz` does not yet include M4E in its drone table; the mission is encoded as M3E (closest match). DJI Pilot 2 will prompt you to re-bind — accept.

| Parameter | Value |
|-----------|-------|
| Drone | M4E (encoded as M3E) |
| AGL | 50 ft (15.24 m) |
| Speed | 12 m/s |

```
py convert_to_dji_m4e_50ft.py
```

---

### `convert_to_dji_m3m_30ft_brucetest22.py` — M3M from Shapefile, flat field
Reads a **WGS-84 point Shapefile** (QGIS / Volitant export) and builds a flat-field mission at a constant height above the takeoff point. No terrain following needed for level agricultural fields.

| Parameter | Value |
|-----------|-------|
| Drone | Mavic 3 Multispectral (M3M) |
| AGL | 30 ft (9.144 m) |
| Speed | 5 m/s |
| Input | `.shp` (WGS-84 / EPSG:4326) |

```
py convert_to_dji_m3m_30ft_brucetest22.py
```

---

## Requirements

```
pip install djikmz pyshp
```

Python 3.10+ recommended.

---

## Workflow

1. Export sampling points from QGIS as a KML (with elevation) **or** as a WGS-84 Shapefile.
2. Edit the mission parameters at the top of the relevant script (AGL, pilot name, speed, etc.).
3. Run the script — a `.kmz` file is written next to the input file.
4. Transfer the KMZ to your device and open in **DJI Pilot 2 → Waypoint Mission → Import KMZ/KML**.

---

## Mission design rationale

| Feature | Why |
|---------|-----|
| Constant AGL | Same GSD at every point → comparable image quality |
| Nadir gimbal (−90°) | Identical look angle → consistent stand-count measurement |
| Hover before photo | Eliminates motion blur at the moment of capture |
| Fixed heading | Repeatable image orientation for multi-date comparisons |

---

## License

MIT
