# Context

Quick orientation for anyone (human or agent) landing in this repo cold.

## The thesis

We're building an autonomous research workflow whose defining property is **it knows
when to stop.** It runs unattended until it hits the edge of what it can stand behind
— and there, instead of guessing, it asks a human. That's the whole thesis, not "we
replaced people."

The old model scaled people with output — more research, more analysts, headcount as
the product. We're cutting that link: when the system can be trusted to handle
something, human attention stops tracking volume and starts tracking only the
frontier — the judgments no agent can yet own. The bottleneck was never "people," it
was an org shape that kept people in the path of work they no longer needed to touch.

We don't get to just assert that the boundary shrinks — that would be the exact
failure the thesis warns against (hyper-competence on a metric that quietly drifted).
So instead of claiming it, we built the instrument that measures it, live. Full
version: `docs/manifesto.md`.

## What we're building

A **cleanroom autoresearch loop** — Karpathy's `autoresearch` pattern (modify → run →
measure → keep-or-discard → repeat), run against a live Postgres database on Aiven
instead of a training script. The objective metric (p99 latency / cost / correctness)
plays the role of `val_bpb` — an objective, hard-to-game judge, which is what makes a
human-free loop honest at all. Database performance is one of the few domains that
already has that kind of judge.

- Aiven Postgres (`sunstead-pg-bench`) is both the target being tuned (indexes, GUCs,
  pool sizing, query rewrites) and the home of the escalation log / experiment memory.
- The escalation gate ("pore") is dumb, frozen, rule-based: irreversible /
  high-blast-radius / correctness-uncertain → ask a human. Frozen on purpose — if it
  self-tuned, you couldn't tell "the world drifted" from "we loosened the gate."

## What the demo actually proves — and, just as importantly, what it doesn't

Two readings, both drawn live off the escalation log, not asserted:

1. **Spatial — where the edge is now.** Escalation rate vs. workload drift. This *is*
   proven by the demo: the autonomy boundary exists, is measurable, and moves
   correctly — escalations rise when the live workload drifts from what's earned
   trust. This also licenses a narrower, real scaling claim: for one task already
   verified stationary, you can run it many more times without a human per
   repetition. Genuine, demonstrated.

2. **Longitudinal — whether the frontier recedes.** Escalations-per-unit-work vs.
   cumulative volume. This is the actual bet: does human attention decouple from
   output as trust accumulates, across *new* kinds of work, not just repeats of one
   proven task? With today's frozen pore, this line is **flat by design** — and that
   flat line is the point, not a gap. From the manifesto directly:

   > "With today's frozen pore the line is flat by design — and that flat line is the
   > point. It is the frontier that does not yet recede... Claiming this as a result
   > would be the very failure the thesis warns against: hyper-competence on a metric
   > that quietly drifted."

   So: **no measured organizational scaling benefit yet, and we say so on stage.** The
   calibrated, OOD-aware membrane that would bend this line down is the deferred
   research bet — articulated, never claimed as a result.

## The Arctal relationship — keep this distinction sharp

This manifesto sits in the same conceptual territory as Sequoia/Arctal's framing
("the next trillion-dollar company is a software company masquerading as a services
firm," agents do the mechanical work, humans concentrate into judgment and
accountability). Fine to invoke as the vision.

But there's a real difference, and it matters: **Arctal asserts the scaling outcome as
an already-achieved business result** (real revenue, real headcount history over real
operating time). **We do not claim that outcome** — we claim only the instrument that
would let anyone check whether it's happening, and we're honest that today the line is
flat. That's a *stronger* intellectual position than Arctal's, not a weaker one — but
only if we keep it precise. The moment the pitch says "we scale better, this uses
fewer humans" as an achieved result, we've quietly resolved the exact bet the
manifesto says is still open, and the position collapses back into an unearned
version of Arctal's claim.

## What to actually say on stage

> "The system knows when to stop, and we can prove it — here's the curve. Whether that
> lets an org need fewer people over time is the bet we're honest about not having
> shown yet."

That's a complete, compelling claim on its own. It doesn't need the Arctal-style
scaling line bolted on, and bolting it on is the one move that would undercut
everything else here being true.

## Where to look

- `docs/manifesto.md` — the thesis in full.
- `docs/solution-directions.md` — architecture, gates, roadmap, status.
- `docs/gate-1-findings.md` — what's actually verified live against Aiven.
- `cleanroom/` — the code (loop, actions, benchmark, pore, boundary, dashboard).
