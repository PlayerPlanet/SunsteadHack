# Manifesto Proof — claim → evidence → status

> What proves [`manifesto.md`](manifesto.md), where the evidence lives, and — kept
> honest — what is still a *bet* rather than a result. One-link demo artifact:
> the self-contained page in [`manifesto-proof.html`](manifesto-proof.html)
> (published private copy: claude.ai/code/artifact/a39de9dc-9c7e-40e6-84f3-6ffaeba64a6d).

## The claims and their evidence

| Manifesto claim | Evidence | Status |
|---|---|---|
| **Autonomous interior** — modify → run → measure → keep-or-discard on a live DB, scored by an objective judge | Story A loop on live Aiven: p99 **58.4 → 25.3 ms** kept, useless index rolled back (`scripts/run_phase1_curve.py`); judge = Story B frozen benchmark + `is_within_noise` | ✅ Proven (live) |
| **It stops and asks** — at the edge of what it can stand behind, escalate to a human | Frozen pore escalates irreversible/high-blast candidates → crossing → human `adjudicate` writes `judgment` with `judge_kind='human'`. Verified live **across 4 separate processes** sharing only the Aiven log (Story D) | ✅ Proven (live) |
| **Schema'd escalation log on Aiven** | `experiment`/`crossing`/`judgment`/`run` tables; `PgLogClient` + `PgRunStore`; persistence verified cross-process | ✅ Proven (live) |
| **Boundary measured, not asserted — spatial** (escalation rate ↑ workload drift) | `scripts/run_drift_sweep.py` → `boundary.escalation_rate_by_drift`. Rises **0 → 1** across drift; escalations are real frozen-pore decisions, emergent from a drift-aware *proposer* (the soft part), not hand-set | ✅ Proven (in-mem / representative); ⏳ Aiven-live persistence = next |
| **Boundary — longitudinal** (escalations-per-unit-work, flat by design) | `run_drift_sweep.run_stationary` → `boundary.escalations_per_unit_work`. Flat ≈ 0.4 at fixed drift as volume accumulates | ✅ Proven |
| **Operable from a Claude session** — the substrate humans use is Claude | Claude Code plugin: MCP server (11 tools incl. `read_boundary`) + `/dispatch /runs /escalations /adjudicate /curve /boundary` | ✅ Proven (contract + in-mem); ⏳ live plugin session = next |

## Kept honest — what is NOT claimed

- **The bet (articulated, not claimed):** a calibrated, OOD-aware membrane that bends the
  longitudinal line *down* — the frontier receding. With today's frozen pore that line is **flat by
  design**, and the flatness is the point. Claiming the bend as a result would be the exact
  hyper-competence-on-a-drifted-metric failure the manifesto warns against.
- **Proxy, labelled everywhere:** the pore gates blast-radius + reversibility — a *lower bound on*,
  not identical to, the true epistemic edge.
- **The spatial drift-response is modelled** in the proposer (legitimate — the proposer is the soft,
  non-judge part). The pore that classifies each candidate is frozen and dumb. The rising curve says
  "the world drifted," never "the gate moved."

## The bright line

The moment the agent can edit the frozen judge/loss mid-run to make the curve look better, the
thesis collapses. Freeze + sign + log makes that structurally impossible, not merely discouraged.

## Regenerate the evidence

```bash
# Both boundary readings (infra-free; add --out boundary.json for the artifact data)
python scripts/run_drift_sweep.py

# The descending p99 curve on live Aiven (isolated schema, reversible)
CLEANROOM_PG_DSN='postgres://…?sslmode=require' python scripts/run_phase1_curve.py

# From a Claude session with the plugin loaded:
/dispatch <task>   ·   /escalations → /adjudicate   ·   /curve <task>   ·   /boundary
```

## Open / next (the ~remaining percent)

1. Persist the drift sweep to **Aiven live** (isolated schema, ~5 min, needs DDL approval).
2. Drive the instrument through the **plugin in a live operator session** (`/boundary`).
3. Story D Phase 2: real `ClaudeCodeProposer` + live harness; define-actions through the frozen pore.
