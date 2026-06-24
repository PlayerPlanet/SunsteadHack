# Manifesto

We are building an autonomous research workflow with one defining move: **it knows when to stop.**

It runs on its own until it reaches the edge of what it can stand behind — and there, instead of
guessing, it asks a human. That single act is the thesis.

The old model scaled people with output: more research, more analysts, headcount as the product.
We are cutting that link. When the machine handles everything it can be trusted to handle, human
attention stops tracking volume and tracks only the frontier — the judgments no agent can own.
The bottleneck was never the human. It was an org shape that kept people in the path of work they
no longer needed to touch.

Remove it, and headcount scales not with how much research we do, but with how fast our world
still produces problems we can't yet trust a machine with. We are betting that rate shrinks faster
than our ambition reopens it. We might be wrong — so we built the instrument that measures it: the
line where autonomy ends and judgment begins, drawn live, watched as it moves.

We are not minimizing people. We are pointing them at the only part that still needs them.

---

## From thesis to instrument

The thesis is only honest if the boundary is *measured*, not asserted. Two readings, both drawn
live off the escalation log (Aiven Postgres):

- **Spatial — where the edge is now.** Escalation rate vs workload drift. As the world drifts from
  what the system has earned trust on, escalations rise; this traces the current shape of the
  autonomous region.
  *Proxy caveat:* the shippable pore gates **blast-radius + reversibility** — "would this be safe
  to be wrong about" — which **lower-bounds, but is not,** the true epistemic edge ("what the agent
  can stand behind"). We label it as a proxy everywhere.
- **Longitudinal — whether the frontier recedes.** Escalations-per-unit-work vs cumulative volume.
  This is the bet itself: does human attention decouple from output as trust accumulates? With
  today's **frozen** pore the line is **flat by design** — and that flat line is the point. It is
  the frontier that does not *yet* recede. The amortized membrane (deferred, data-gated) is the bet
  to bend it down. The instrument is already pointed at it.

## What ships vs. what's the bet

- **Ships (48h):** the autonomous interior, the dumb-frozen pore that stops and asks, the schema'd
  escalation log, and the instrument that draws both readings.
- **The bet (articulated, not claimed):** the calibrated, OOD-aware membrane that lets the
  longitudinal line actually bend — the frontier receding faster than ambition reopens it. Claiming
  this as a *result* would be the very failure the thesis warns against: hyper-competence on a
  metric that quietly drifted. We measure it; we do not fake it.

---

*Architecture: see [`aiven_agentic_org.md`](aiven_agentic_org.md) and the diagram
[`aiven-architecture.png`](aiven-architecture.png). Build decomposition: GitHub issues #2 (loop),
#3 (substrate), #4 (boundary instrument).*
