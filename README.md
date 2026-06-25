# Sunstead — Bring Your Own Agent Platform

A secure runtime for autonomous agents. You bring the agent; we provide the governed
environment it runs in, the gate that decides when it can act on its own, and the
instrument that tells you — live and measured, not asserted — exactly how much human
oversight it still needs.

> **The goal:** minimize human supervision over deployed agents. Not by trusting them
> blindly, but by earning autonomy incrementally and measuring the boundary as it moves.

Aiven project: `konsta-sunsteadhack` (cloud `google-europe-north1`).

---

## How it works

Customers deploy their agent into the platform runtime. The runtime wraps every action
the agent proposes with three primitives:

**1. A frozen escalation gate (the pore)**
A fixed, rule-based gate that intercepts each action before it executes. If the action
is irreversible, high blast-radius, or outside the workload the agent has earned trust
on — it stops and routes the decision back to the original deployer. Frozen on purpose:
the gate is the measuring stick. A self-tuning gate can't tell "the world got harder"
from "we lowered the bar."

**2. An objective judge**
For every action the agent does execute autonomously, the platform runs a mechanical
check: was it actually correct? No human opinion — a number you can recompute. This is
what makes the whole thing honest. Where no objective judge exists (interpretation, not
extraction), the platform says so and keeps the human in the loop rather than
pretending otherwise.

**3. A live boundary instrument**
Bins the agent's tasks by how far they've drifted from familiar territory. For each
bin: what fraction did the agent escalate, and of the ones it acted on autonomously,
what fraction were confirmed correct? Plot those two readings against drift. The
trustworthy region is where both are healthy. The boundary is where either collapses.
It's entirely external and behavioral — the agent's internals never enter.

The result: a live, empirical answer to "how much does this agent need a human?" that
updates as the agent runs, rather than a one-time vendor assertion.

---

## The training trajectory

Today's gate is a frozen proxy — it catches blast-radius and irreversibility, which
correlates with but is not identical to the true epistemic edge. The boundary instrument
generates a labeled dataset of every escalation: `(task, drift, proposal) → escalate? →
deployer approved/rejected`.

Stage 2 trains on that corpus to predict the deployer's verdict. Every false escalation
the trained membrane learns to auto-clear is a human interruption saved — the
longitudinal curve (human interventions per unit work) bends down. That bend is the
platform's core value delivery: autonomy earned over time, measured, not claimed.

The Stage 1 deep probe (144 labeled rows, Haiku proposing, Sonnet adjudicating) shows
the calibration gap is **~93% learnable** — the residual 7% is genuinely irreducible
judgment that will always route to a human. That irreducible fraction is not a bug; it
is the true epistemic edge, and the platform's job is to find it precisely.

---

## What's proven today

| Claim | Evidence |
|---|---|
| Agent acts autonomously on familiar tasks | p99 58 → 25 ms on live Aiven (DB domain); 107 → 57 ms (JOB benchmark) |
| Gate escalates correctly at the edge | Frozen pore, verified cross-process across 4 sessions on shared Aiven log |
| Boundary is measurable, not asserted | Spatial curve 0% → 100% escalation as drift rises; longitudinal curve flat at fixed drift |
| Escalation routes to deployer | `/adjudicate` in the operator plugin; human judgment written back to log |
| Multi-domain runtime | Kernel / quant / bio domains dispatchable alongside Postgres through same control plane |
| Calibration gap is learnable | 93% LOO accuracy on 15 human judgments; residual = true irreducible edge |

## What is still a bet

The longitudinal curve is **flat by design** with today's frozen gate. Whether training
on the accumulated judgment corpus actually bends it down — whether the platform
genuinely reduces supervision over time across novel task types, not just repeats of
proven ones — is Stage 2. Articulated, never claimed as a result here.

---

## Running it

```bash
pip install -e .

# Verify the runtime fixtures
python -c "from cleanroom.fixtures import CannedBenchmark, NoOpPore, InMemoryLogClient, DummyProposer; print('ok')"

# Run the boundary instrument (offline)
python scripts/run_drift_sweep.py --mock

# Run against live Aiven (needs DSN)
CLEANROOM_PG_DSN='postgres://…?sslmode=require' python scripts/run_phase1_curve.py

# Operator plugin (from a Claude session with the plugin loaded)
/dispatch <task>   ·   /escalations → /adjudicate   ·   /curve <task>   ·   /boundary
```

---

## Marketplace setup

The operator commands ship as a Claude Code plugin (`sunstead-control`) served from a
plugin **marketplace** defined in this repo. A marketplace is just a manifest that lists
one or more installable plugins; Claude Code reads it to discover and install them.

### 1. The marketplace manifest

Create `.claude-plugin/marketplace.json` at the repo root. It registers the `sunstead`
marketplace and points at the bundled plugin in [`plugin/`](plugin/):

```json
{
  "name": "sunstead",
  "owner": { "name": "SunsteadHack Team" },
  "metadata": {
    "description": "SunsteadHack plugins — operate the self-optimizing Data-Agent control plane from Claude.",
    "version": "1.0.0"
  },
  "plugins": [
    {
      "name": "sunstead-control",
      "source": "./plugin",
      "description": "Operate the SunsteadHack autoresearch control plane — dispatch runs, watch p99/cost curves, read the boundary instrument, and adjudicate escalations. Slash commands: /dispatch /runs /escalations /adjudicate /curve /boundary.",
      "version": "1.0.0",
      "author": { "name": "SunsteadHack Team" }
    }
  ]
}
```

The `source` is repo-relative, so the plugin definition in
[`plugin/.claude-plugin/plugin.json`](plugin/.claude-plugin/plugin.json) is resolved
from the marketplace root.

### 2. Register the marketplace in Claude Code

From a Claude Code session, add the marketplace by path (local checkout) or by repo:

```
/plugin marketplace add .                       # local checkout (repo root)
/plugin marketplace add <owner>/sunsteadhack    # or by GitHub repo
```

Verify it resolved:

```
/plugin marketplace list
```

### 3. Install and enable the plugin

```
/plugin install sunstead-control@sunstead
```

This makes the operator slash commands available:
`/dispatch /runs /escalations /adjudicate /curve /boundary`.

### 4. Connect the control-plane MCP server

The slash commands talk to an MCP server. **The recommended path is the hosted control
plane** — an AgentCore Runtime reached over HTTP with OAuth (authorization-code + PKCE).
Add it with the public Cognito client; no secret, no `claude mcp login`:

```bash
claude mcp add --transport http --callback-port 8080 sunstead-control \
  "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A528081867249%3Aruntime%2Fsunsteadcontrol_sunstead_control-u9zi87DjdX/invocations?qualifier=DEFAULT"
```

On first use Claude opens a browser sign-in; tokens are stored in your keychain and
auto-refreshed. You land as a **read-only viewer** until an operator adds your Cognito
user to a group. This is the config the plugin ships in
[`plugin/.mcp.json`](plugin/.mcp.json) (the file Claude Code auto-loads), with the public
client `1phgpdfcrftedtj69hhni18bue` defaulted in — so `--client-id` is optional and a
marketplace install just works. To point at your own runtime + Cognito pool, set
`SUNSTEAD_CONTROL_URL` and `SUNSTEAD_CONTROL_CLIENT_ID`.

**Local stdio alternative (development only).** The hosted transport is the only one that
works from a marketplace install — that copy has no `cleanroom` source on `PYTHONPATH`, so
the stdio servers fail with `-32000`. For local dev from a repo checkout,
[`plugin/.mcp.local.json`](plugin/.mcp.local.json) runs `cleanroom.control.server.mcp`
(and the `sunstead-bench` benchmark) as subprocesses; copy it over `.mcp.json` in your
checkout. It needs the repo on `PYTHONPATH` and, for shared state across sessions, an
Aiven Postgres DSN — without one it falls back to in-memory storage (lost on MCP restart):

```bash
export CLEANROOM_PG_DSN="postgresql://user:pass@host:5432/db?sslmode=require"
```

See [`plugin/README.md`](plugin/README.md) for the full command reference, the
in-memory vs. persistent backend selection, and the governance/legitimacy boundary
(what the plugin is and isn't allowed to do).

---

## Repository map

| Path | Purpose |
|---|---|
| [`cleanroom/loop/`](cleanroom/loop/) | Agent run loop — propose → judge → keep or discard |
| [`cleanroom/pore/`](cleanroom/pore/) | Frozen escalation gate (the measuring stick) |
| [`cleanroom/boundary/`](cleanroom/boundary/) | Boundary instrument — escalation rate + correctness vs. drift |
| [`cleanroom/control/`](cleanroom/control/) | Operator control plane — MCP server, dispatcher, slash commands |
| [`cleanroom/domains/`](cleanroom/domains/) | Domain adapters — kernel, quant, bio (plug-in judges + action spaces) |
| [`cleanroom/probe/`](cleanroom/probe/) | Deep boundary probe — labels the calibration gap |
| [`cleanroom/db/`](cleanroom/db/) | Append-only escalation log on Aiven Postgres |
| [`plugin/`](plugin/) | Claude Code plugin — `/dispatch /runs /escalations /adjudicate /curve /boundary` |
| [`scripts/`](scripts/) | Curve generation, drift sweep, deep probe, membrane fit |
| [`docs/manifesto.md`](docs/manifesto.md) | The thesis: autonomy is only honest where you can judge it |
| [`docs/manifesto-proof.md`](docs/manifesto-proof.md) | Every claim mapped to its evidence |
| [`docs/deep-probe-report.md`](docs/deep-probe-report.md) | Calibration gap analysis — the learnable fraction |
| [`docs/domain-onboarding.md`](docs/domain-onboarding.md) | How to onboard a new domain (classify + frozen loss) |
