"""Load the green-bond CSVs and compute the deterministic drift score.

The drift score is "distance from vanilla" — the axis the trustworthy region
recedes along. Pure structural features, no LLM, computed per ISIN from the
issuances row.
"""

import csv
import os
from pathlib import Path

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "2026-06-23_100-bond-sample-takehome"


def data_dir() -> Path:
    return Path(os.environ.get("BONDS_DATA_DIR", _DEFAULT_DIR))


def _rows(name: str) -> list[dict]:
    with open(data_dir() / name, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(v) -> float | None:
    """Parse a float, tolerating blanks / junk."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_tables() -> dict[str, list[dict]]:
    return {
        "issuances": _rows("issuances.csv"),
        "cat_allocations": _rows("cat_allocations.csv"),
        "geo_allocations": _rows("geo_allocations.csv"),
        "impacts": _rows("impacts.csv"),
    }


# --------------------------------------------------------------------------- #
# Drift score — deterministic distance-from-vanilla in [0, 1].                 #
# --------------------------------------------------------------------------- #

def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def drift_features(iss_row: dict) -> dict:
    """The structural features that make a bond 'weird'. All observable, no PDF."""
    post_n = num(iss_row.get("post_icma_categories_number")) or 0.0
    pre_n = num(iss_row.get("pre_icma_categories_number")) or 0.0
    cov = num(iss_row.get("allocation_coverage_pct"))
    trail = iss_row.get("document_source_trail") or ""
    post_docs = iss_row.get("post_source_documents") or ""
    return {
        "n_post_categories": _clamp(post_n / 8.0),
        "low_coverage": _clamp(1.0 - (cov / 100.0)) if cov is not None else 0.5,
        "trail_length": _clamp(len(trail) / 2000.0),
        "n_source_docs": _clamp((post_docs.count(";") + (1 if post_docs.strip() else 0)) / 5.0),
        "pre_post_gap": _clamp(max(0.0, pre_n - post_n) / 8.0),
    }


def drift_score(iss_row: dict) -> float:
    f = drift_features(iss_row)
    return round(sum(f.values()) / len(f), 4)


def drift_by_isin() -> dict[str, float]:
    """ISIN -> drift score. For duplicate ISINs, keep the first issuance row."""
    out: dict[str, float] = {}
    for r in _rows("issuances.csv"):
        isin = r["isin"]
        if isin not in out:
            out[isin] = drift_score(r)
    return out


DRIFT_BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]


def drift_bin(d: float) -> str:
    for lo, hi in DRIFT_BINS:
        if lo <= d < hi:
            return f"{lo:.1f}-{hi if hi <= 1 else 1.0:.1f}"
    return "0.8-1.0"
