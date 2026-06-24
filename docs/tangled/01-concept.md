# 01 — Concept

## What this track is

A **governance + explainability layer** for an agentic data organization, built on Tangled
(decentralized git on the AT Protocol). Two reused/extended pieces:

1. **Membrane governance** (extends the existing membrane-crossing probe — see
   `../membrane-trial.md`). An AI Data-Agent never mutates infrastructure silently. Every
   proposed change *stages* as a unit, *crosses a pore* (a gated checkpoint), and is *logged*.
   - **Cells** = surfaces with a risk level.
   - **Pores** = controlled crossings with checks + (for HIGH risk) required human judgment.
   - New data-infra pores: `data_schema_safety`, `data_cost_envelope`, `data_blast_radius`.
2. **ATProto explainability.** The crossings and judgments are promoted from a flat
   `crossings.yaml` into **signed AT Protocol records** in users'/agents' PDSes. Because those
   records are public, addressable, lexicon-typed, and **DID-signed**, the decision trail is
   verifiable and queryable by design — and *anyone* can build an alternative appview over it.

## The thesis

> **Explainability and accountability as a property of the substrate, not a bolted-on feature.**

A `com.sunstead.judgment` record isn't a log line you have to trust — it's a cryptographically
attributed assertion: *this DID (this agent, or this human judge) decided this, at this time,
about this change, for this reason.* Plural appviews (regulator view, cost view, lineage view)
all reconcile to one signed source of truth. No single app owns the explanation.

## Relationship to the Aiven track

The two tracks are one idea at different points on a spectrum:

| | Aiven track (front-runner) | Tangled track (this) |
|---|---|---|
| Acceptance signal | **objective metric** (p99/cost/throughput) | **human judgement**, governed |
| Needs a human in the loop? | No — the metric is the judge | Yes for HIGH-risk; amortized over time |
| Closing the autonomous loop | safe immediately (hard-to-game metric) | safe only with governance + (v2) calibrated abstention |
| Risk | low (objective) | Goodhart / drift if judgement is amortized naively |

**One-line bridge:** *autoresearch needs a metric; we use the objective one where it exists
(Aiven), and we manufacture-and-govern human judgement where it doesn't (Tangled).* The Tangled
track is what makes a *manufactured* acceptance signal trustworthy enough to eventually close a
loop on — via signed, auditable, drift-monitored judgement records.

## Why explore it first

This track's ATProto integration carries the most unknowns (custom-lexicon writes, agent DIDs,
firehose pickup, spindle runtime). Spiking those early tells us whether the explainability story
is real before anyone writes production code. See
[04-open-questions-and-spikes.md](04-open-questions-and-spikes.md).
