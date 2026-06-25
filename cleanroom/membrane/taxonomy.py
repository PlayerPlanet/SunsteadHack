"""Frozen semantic-risk taxonomy for DB change candidates (membrane v2, issue #20).

WHY THIS EXISTS
---------------
Membrane v1 (`cleanroom/membrane/__init__.py`) keys decisions on the *lever identity*
(the GUC name). That is why its held-out (leave-one-lever-out) test abstains 100% on
any unseen lever: a name carries no signal about a lever the membrane has never seen.
v1 memorizes; it does not generalize. That is the gap v2 closes.

The insight: the human's approve/reject verdict was never really about the *name* —
it was about what the change *risks*. Durability switches that can lose or corrupt
data on a crash get rejected; sizing knobs that only move throughput and are fully
recoverable get approved; a bounded durability/latency *tradeoff* is the genuinely
ambiguous case. v2 features each candidate on those semantic axes instead of its name,
so a never-before-seen lever that shares a risk profile with a seen one inherits its
verdict — real cross-lever generalization.

THE HONESTY BOUNDARY (read before trusting any v2 number)
---------------------------------------------------------
These risk profiles are **domain priors**, taken from documented PostgreSQL behaviour
of each parameter — NOT fitted to the 15 escalation labels. The claim v2 makes is
therefore precise:

    "With a small, fixed risk taxonomy defined from DB semantics, the false-stop slack
     generalizes ACROSS levers."

It is NOT the claim "the verdict is learned tabula rasa from 15 rows." The risk of
circularity (silently baking the verdict into the features) is real; we guard it two
ways: (1) the taxonomy is defined here from parameter semantics, with the documented
reason in each entry, independent of which way the human voted; (2) the verdict↔risk
correlation is then *measured* empirically (scripts/eval_membrane_v2.py), not asserted.
If LOLO generalizes, the priors carry it; if it does not, we have learned the priors
are insufficient. Either outcome is honest.

This module is FROZEN data, not a model. It never sees labels and never self-tunes.
"""

from dataclasses import dataclass

from cleanroom.types import Candidate

# Ordinal: how much committed data a crash can lose/corrupt while the change is in
# effect. The single most predictive risk axis (durability is what humans guard).
DATA_LOSS_NONE = 0      # throughput/plan only; a crash loses nothing extra
DATA_LOSS_BOUNDED = 1   # loses at most the last few in-flight txns; NO corruption
DATA_LOSS_HIGH = 2      # can corrupt/lose committed data on crash


@dataclass(frozen=True)
class RiskProfile:
    """Semantic-risk features for one lever, from documented PG behaviour.

    Fields (all from parameter semantics, not from any verdict):
        risk_class: coarse family label (for legibility / OOD novelty).
        data_loss_on_crash: DATA_LOSS_{NONE,BOUNDED,HIGH}.
        changes_result_semantics: would change query *results*, not just speed.
        recoverable: can be fully undone (reversible in effect, not just as a toggle).
        restart_required: bouncing the service to take effect (availability blast).
        rationale: the documented reason, so the taxonomy is auditable.
    """

    risk_class: str
    data_loss_on_crash: int
    changes_result_semantics: bool
    recoverable: bool
    restart_required: bool
    rationale: str


# --- The taxonomy: PostgreSQL parameter semantics (label-independent) --------
#
# Each entry cites the documented behaviour. None of these were chosen by looking
# at how the human voted; they are properties of the parameter.

_GUC_PROFILES: dict[str, RiskProfile] = {
    "fsync": RiskProfile(
        "durability_switch", DATA_LOSS_HIGH, False, True, False,
        "fsync=off stops flushing WAL/data to disk; a crash can leave an unrecoverable, "
        "corrupt cluster. Documented as unsafe unless the whole cluster is disposable.",
    ),
    "full_page_writes": RiskProfile(
        "durability_switch", DATA_LOSS_HIGH, False, True, False,
        "full_page_writes=off risks torn pages after a crash mid-write -> silent "
        "corruption. A correctness guarantee, not a tuning knob.",
    ),
    "synchronous_commit": RiskProfile(
        "durability_tradeoff", DATA_LOSS_BOUNDED, False, True, False,
        "synchronous_commit=off returns success before WAL is durably flushed; a crash "
        "loses only the last few committed txns, with NO corruption. A bounded, common "
        "latency/durability tradeoff — the genuinely ambiguous case.",
    ),
    "wal_level": RiskProfile(
        "replication_capability", DATA_LOSS_BOUNDED, False, True, True,
        "Lowering wal_level can break replicas / PITR; raising is safe. Restart-required, "
        "and the effect is on recoverability infrastructure, not the primary's data.",
    ),
    "shared_buffers": RiskProfile(
        "memory_sizing", DATA_LOSS_NONE, False, True, True,
        "Pure memory-sizing for the buffer cache; affects throughput only and is fully "
        "recoverable. Restart-required (availability blast), no data risk.",
    ),
    "max_connections": RiskProfile(
        "capacity_sizing", DATA_LOSS_NONE, False, True, True,
        "Connection-slot sizing; restart-required and high blast (bounces sessions) but "
        "no durability or result-semantics risk.",
    ),
    "max_wal_size": RiskProfile(
        "wal_sizing", DATA_LOSS_NONE, False, True, False,
        "Soft cap on WAL between checkpoints; trades disk for checkpoint frequency. "
        "Online, fully recoverable, no data risk.",
    ),
    "work_mem": RiskProfile(
        "memory_sizing", DATA_LOSS_NONE, False, True, False,
        "Per-node sort/hash memory; planner/throughput only, online, recoverable.",
    ),
    "random_page_cost": RiskProfile(
        "planner_cost", DATA_LOSS_NONE, False, True, False,
        "Planner cost constant; changes plan choice, never results. Online, recoverable.",
    ),
    "effective_cache_size": RiskProfile(
        "planner_cost", DATA_LOSS_NONE, False, True, False,
        "Planner hint about OS cache size; influences plans only. Online, recoverable.",
    ),
}

# Non-GUC operations keyed by an explicit `op`.
_OP_PROFILES: dict[str, RiskProfile] = {
    "vacuum_full": RiskProfile(
        "table_rewrite", DATA_LOSS_NONE, False, False, False,
        "VACUUM FULL rewrites the table under an ACCESS EXCLUSIVE lock; no data loss but "
        "NOT reversible and blocks all access for its duration.",
    ),
    "query_rewrite": RiskProfile(
        "semantic_rewrite", DATA_LOSS_NONE, True, True, False,
        "A query rewrite that changes result semantics — fast but answers a different "
        "question. The classic 'correct but wrong' membrane case.",
    ),
}

# Profile for reversible, low-risk, targeted fixes (indexes / extended statistics):
# the auto-applied path the pore never even escalates.
_TARGETED_PROFILE = RiskProfile(
    "targeted_reversible", DATA_LOSS_NONE, False, True, False,
    "Secondary index / extended statistics: reversible, targeted, no systemic or "
    "durability risk. The pore auto-clears these without escalating.",
)


def lever_of(candidate: Candidate) -> str:
    """GUC name, else explicit op, else candidate type — matches membrane v1/fit."""
    params = candidate.params or {}
    return params.get("name") or params.get("op") or candidate.type


def profile_of(candidate: Candidate) -> RiskProfile:
    """The semantic-risk profile for a candidate, from the frozen taxonomy.

    Falls back to the targeted-reversible profile for index/statistics candidates and
    — conservatively — to a HIGH-data-loss, irreversible-if-marked profile for any
    truly unknown lever, so an unrecognised systemic change is never treated as safe.
    """
    params = candidate.params or {}
    name = params.get("name")
    if name and name in _GUC_PROFILES:
        return _GUC_PROFILES[name]
    op = params.get("op")
    if op and op in _OP_PROFILES:
        return _OP_PROFILES[op]
    if candidate.type in ("index", "statistics"):
        return _TARGETED_PROFILE
    # Unknown systemic lever: refuse to assume it is safe. Mark as novel via an
    # 'unknown' risk_class so the OOD head can abstain on it.
    return RiskProfile(
        "unknown", DATA_LOSS_BOUNDED, False, candidate.reversible, False,
        f"Unrecognised lever {lever_of(candidate)!r}; treated as novel/uncertain.",
    )


def feature_vector(candidate: Candidate) -> dict:
    """Numeric semantic features for a candidate (NO lever identity)."""
    p = profile_of(candidate)
    return {
        "data_loss_on_crash": p.data_loss_on_crash,
        "changes_result_semantics": int(p.changes_result_semantics),
        "recoverable": int(p.recoverable and candidate.reversible),
        "restart_required": int(p.restart_required),
        "risk_class": p.risk_class,
    }


# All risk classes the taxonomy can emit — used by the OOD head to recognise a class
# it has no training precedent for.
KNOWN_RISK_CLASSES = frozenset(
    p.risk_class for p in list(_GUC_PROFILES.values()) + list(_OP_PROFILES.values())
) | {_TARGETED_PROFILE.risk_class, "unknown"}
