"""Green-bond data-quality agent.

Public surface:
  * `review(record) -> Decision`  — the clean per-record contract a benchmark or
    the main pipeline wraps (ok | error | escalate). See `review.py`.
  * `assess_record(table, row, ctx, reasoner) -> [Finding]` — all findings for one
    record; the pure seam the CLI and tests use.
  * CLI: `python -m agent [--llm]`.
"""

from .data import Context, build_context, load_tables
from .finding import Finding
from .review import Decision, assess_record, decide, review

__all__ = [
    "review", "Decision", "assess_record", "decide",
    "Finding", "Context", "build_context", "load_tables",
]
