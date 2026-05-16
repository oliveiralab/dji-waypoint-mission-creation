# Contributing

Thanks for your interest in improving `dji-waypoints`! This guide covers the
most common contributions.

## Quick start

```bash
git clone https://github.com/mailson-unl/dji-waypoint-mission-creation
cd dji-waypoint-mission-creation
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -e ".[dev]"
pytest
```

## Adding a new input format

1. Add a `read_<format>(path) -> list[Point]` function in
   [src/dji_waypoints/readers.py](src/dji_waypoints/readers.py).
2. Register it in the `_READERS` dispatch dict at the bottom of that file.
3. Add a unit test in [tests/test_readers.py](tests/test_readers.py).

## Adding support for a new drone

`djikmz` is the underlying KMZ writer. If your drone is not in its enum table,
encode the mission as the closest supported model (e.g. M4E → M3E) and note
the workaround in the README "Supported drones" section. DJI Pilot 2 will
prompt to re-bind the mission on import.

## Code style

- Lint with `ruff check src tests`.
- Format with `ruff format src tests` (optional but appreciated).
- Keep functions small and add a docstring for anything public.

## Pull requests

- Create a branch from `master`.
- Add or update tests for any behaviour change.
- Make sure `pytest` is green locally before pushing — CI will also run it.
- Reference any related issue in the PR description.

## Reporting bugs

Open an issue and include:

- OS, Python version, `djikmz` version
- A minimal input file (or fake equivalent) that reproduces the problem
- The full traceback
