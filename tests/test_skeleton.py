"""Phase 0 smoke tests: the environment and config skeleton are sound."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_KEYS = {"value", "unit", "source_or_assumption", "note"}


def _leaves(node, path=()):
    """Yield (path, dict) for every parameter entry (a dict holding a 'value' key)."""
    if isinstance(node, dict) and "value" in node:
        yield path, node
    elif isinstance(node, dict):
        for key, child in node.items():
            yield from _leaves(child, path + (key,))


def test_required_libraries_import():
    import numpy, scipy, pandas, rasterio, shapely, ortools, networkx, matplotlib, PIL, requests  # noqa: F401


def test_params_every_entry_has_four_fields():
    params = yaml.safe_load((ROOT / "config" / "params.yaml").read_text(encoding="utf-8"))
    leaves = list(_leaves(params))
    assert leaves, "params.yaml has no parameters"
    for path, entry in leaves:
        assert set(entry) == REQUIRED_KEYS, f"{'.'.join(path)} has keys {sorted(entry)}"
        assert str(entry["source_or_assumption"]).strip(), f"{'.'.join(path)} has no source"


def test_raw_data_is_git_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/*" in gitignore
