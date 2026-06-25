"""Data loading + the shared `Context` the checks reason against.

`Context` holds everything a per-record check needs that is *not* on the record
itself: cross-table indexes (the same ISIN across files), the per-currency FX
consensus, and per-metric impact-intensity peer statistics. It is built once from
the loaded tables and is pure data thereafter — so the checks stay pure functions
of `(record, context)` and remain trivially testable.

Stdlib only (`csv`, `statistics`). No pandas: the deterministic tier must run on
30k+ rows with zero install friction, and a streaming `csv.DictReader` is plenty.
"""

from __future__ import annotations

import csv
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "2026-06-23_100-bond-sample-takehome"

TABLES = ("issuances", "cat_allocations", "geo_allocations", "impacts")


def data_dir() -> Path:
    """Sample data location; override with BONDS_DATA_DIR for the real corpus."""
    return Path(os.environ.get("BONDS_DATA_DIR", _DEFAULT_DIR))


def num(v) -> float | None:
    """Parse a float, tolerating blanks, thousands separators and junk -> None."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_tables(d: Path | None = None) -> dict[str, list[dict]]:
    d = d or data_dir()
    out: dict[str, list[dict]] = {}
    for name in TABLES:
        with open(d / f"{name}.csv", encoding="utf-8") as fh:
            out[name] = list(csv.DictReader(fh))
    return out


@dataclass
class PeerStat:
    """Robust location/scale for one peer group (median + MAD), used for outliers."""
    median: float
    mad: float          # median absolute deviation (robust spread)
    n: int

    def robust_z(self, x: float) -> float:
        """How many robust sigmas is x from the group median (0 if no spread)."""
        if self.mad <= 0:
            return 0.0
        return abs(x - self.median) / (1.4826 * self.mad)


@dataclass
class Context:
    """Everything cross-record the checks need. Built once; pure data after."""
    iss_by_isin: dict[str, dict] = field(default_factory=dict)
    impacts_by_isin: dict[str, list[dict]] = field(default_factory=dict)
    cat_by_isin: dict[str, list[dict]] = field(default_factory=dict)
    geo_by_isin: dict[str, list[dict]] = field(default_factory=dict)

    # currency -> consensus USD-per-unit rate (median of implied rates in corpus)
    fx_consensus: dict[str, float] = field(default_factory=dict)
    # impact_metric -> PeerStat over impact_per_million_USD (intensity outliers)
    pmu_peers: dict[str, PeerStat] = field(default_factory=dict)
    # isin -> count of issuance rows (duplicate-ISIN detection at scale)
    isin_row_counts: dict[str, int] = field(default_factory=dict)


def build_context(tables: dict[str, list[dict]]) -> Context:
    ctx = Context()

    iss = tables["issuances"]
    for r in iss:
        isin = r["isin"]
        ctx.isin_row_counts[isin] = ctx.isin_row_counts.get(isin, 0) + 1
        ctx.iss_by_isin.setdefault(isin, r)  # first row wins; divergence handled by check
    for r in tables["impacts"]:
        ctx.impacts_by_isin.setdefault(r["isin"], []).append(r)
    for r in tables["cat_allocations"]:
        ctx.cat_by_isin.setdefault(r["isin"], []).append(r)
    for r in tables["geo_allocations"]:
        ctx.geo_by_isin.setdefault(r["isin"], []).append(r)

    # FX consensus: median implied USD/unit rate per currency, from the data itself.
    by_ccy: dict[str, list[float]] = {}
    for r in iss:
        amt, usd = num(r.get("bond_amount")), num(r.get("bond_USD_amount"))
        ccy = (r.get("bond_currency") or "").strip()
        if amt and usd and ccy:
            by_ccy.setdefault(ccy, []).append(usd / amt)
    ctx.fx_consensus = {c: statistics.median(v) for c, v in by_ccy.items() if v}

    # Intensity peers: median + MAD of impact_per_million_USD per impact_metric.
    by_metric: dict[str, list[float]] = {}
    for r in tables["impacts"]:
        pmu = num(r.get("impact_per_million_USD"))
        metric = (r.get("impact_metric") or "").strip()
        if pmu is not None and pmu > 0 and metric:
            by_metric.setdefault(metric, []).append(pmu)
    for metric, vals in by_metric.items():
        if len(vals) < 4:
            continue  # too few peers to call an outlier
        med = statistics.median(vals)
        mad = statistics.median([abs(x - med) for x in vals])
        ctx.pmu_peers[metric] = PeerStat(median=med, mad=mad, n=len(vals))

    return ctx
