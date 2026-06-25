# Domain Onboarding — Classify the Problem, Co-Author the Loss (frozen)

> Design proposal for team reaction **before any code**. Thesis-touching — read the
> bright line first. Relates to [`manifesto.md`](manifesto.md),
> [`solution-directions.md`](solution-directions.md) (the *v2 amortized judge* it must
> NOT be confused with), and Epic #8 domain benchmarks (#9 kernel / #10 quant / #11 bio).

## The bright line (state it once)

The judge must be **objective, hard-to-game, and frozen** — the same property that lets
the frozen pore distinguish "the world drifted" from "we loosened the gate." **The moment
an agent can edit the frozen loss mid-run to make the curve look better, the whole thesis
collapses into the unearned scaling claim the manifesto avoids.** Everything below is built
to make that move *structurally impossible* (freeze + sign + logged crossing), not merely
discouraged.

## Why we need a front door

`autoresearch`/our Data-Agent only closes the loop honestly where a cheap, objective,
hard-to-game metric exists (DB p99). Most enterprise problems lack one and must stay
human-gated. To generalize beyond the DB task **without** smuggling illegitimate work into
the autonomous loop, we need two things in front of the loop: a **classifier** that routes a
problem to a legitimate judge (or refuses), and a **human-led, CC-assisted loss elicitation**
that produces a frozen judge when one is constructible.

## Move 1 — Classify the problem (low-risk, CC-native, do freely)

A `/classify` (domain-onboard) skill takes a problem statement; CC returns exactly one of:

- **Known class** → DB / kernel #9 / quant #10 / bio #11 → reuse the existing adapter triplet.
- **Novel but judge-constructible** → go to Move 2.
- **No cheap, hard-to-game judge exists** → **stays human-gated** (emit the human workflow,
  do not enter the loop).

The third bucket is what makes the classifier honest. *A classifier that always finds a class
is the exact failure the manifesto warns about.* For most enterprise problems the most valuable
output is: **"the loop can't run here legitimately — here's the human-gated workflow instead."**
Architecturally cheap: we already shell out to Claude Code in `cleanroom/loop/proposers.py`
(`ClaudeProposer`/`ClaudeCodeProposer`), so a CC-driven front-door router is consistent
plumbing, not new infrastructure. Routing is reversible and human-checkable → low risk.

## Move 2 — Co-author the loss with the human (frozen, one specific shape)

- ❌ **Agent authors/owns its own loss → forbidden.** Agent grading its own homework; pure
  Goodhart; collapses legitimacy.
- ✅ **Human-led, CC-assisted elicitation → frozen, signed loss before iteration 0.** Not just
  legitimate — it's the *correct* place for the human. **Defining the objective is the
  irreducible human judgment** the manifesto says humans should concentrate into. CC is not
  deciding what "better" means; it helps the human articulate and codify it, then steps back.
  That puts the human at the frontier, not out of the loop.

### Four disciplines that keep Move 2 inside the thesis

1. **Freeze-and-sign before iteration 0.** Elicitation emits a loss spec; content-hash it and
   write a **loss-definition crossing** via `logclient.write_crossing` (action carries the
   spec + hash). The loop runs against an immutable target. No mid-run loss edits without a
   *new* signed crossing. (The loss-analogue of the frozen pore.)
2. **Output reduces to the existing frozen contract.** The dialogue's deliverable is a domain
   **adapter triplet**, same shape as Epic #8: a measurement fn (→ lower-is-better scalar,
   the `Result.p99_ms` overload), a constraint/correctness fn (→ `check_correctness`), and an
   actions adapter (the action-injection seam already landed). CC helps a human write three
   functions — which is what CC is for. `Result`/`PoreResult` stay frozen.
3. **Adversarial gameability review is a mandatory gate.** Before freezing, the dialogue must
   ask: *"here is the candidate loss — give me three ways an optimizer wins it without doing
   the real work."* This is already implicit in the class choices (walk-forward OOS Sharpe for
   #10 resists overfitting; held-out F1 for #11 resists leakage). Make it an explicit step —
   ideally a `dev-team-reviewer` pass that can **block** the freeze.
4. **Soft to construct, hard frozen to run.** The classifier and loss-builder are
   LLM-mediated → soft and gameable → they can **never** be the judge. They are scaffolding
   that *produces* a frozen judge. Keep the soft part out of the loop, and distinct from the
   pore, which stays frozen and dumb regardless.

### Bonus: a second honesty curve

Once loss redefinitions are logged crossings, the boundary instrument gets
**loss-redefinitions per unit work**. A loss that keeps drifting toward "easier" shows up as
a line that doesn't flatten — you can literally *see* a team Goodharting itself. On-brand
artifact alongside escalation-rate-by-drift.

### Not the v2 amortized judge

Keep this distinct in the pitch. The *v2 amortized judge* (solution-directions.md) **learns**
human judgment on stationary surfaces — soft, deferred, dangerous. This is the safe inverse:
a **human-authored** loss, elicited once, **frozen up front**. Don't conflate them.

## Concretely — three things on top of what exists

1. A **`/classify`** skill with a decision rubric, including the "no legitimate judge" exit.
2. An interactive **loss-elicitation workflow** (AskUserQuestion-driven) → emits
   `cleanroom/domains/<name>/{proposer,judge,actions}.py` + a signed **loss spec**.
3. A **`write_crossing` freeze record** (spec + content hash) before the run.

## Frozen-loss-spec — straw man (for reaction)

```json
{
  "domain": "<name>", "version": 1,
  "objective": "<one-line human statement of better>",
  "measurement": "module:fn -> float (lower is better)",
  "constraints": "module:fn -> bool (hard correctness/guardrail)",
  "action_space": ["<reversible action kinds>"],
  "gameability_review": ["<≥3 ways to win without real work, + why blocked>"],
  "signed_by": "<human>", "content_hash": "<sha256 over the above>"
}
```

## Open questions for the team

- Where does the signed spec live — only as a `crossing` row, or also a version-controlled
  file under `cleanroom/domains/<name>/`? (Crossing = audit; file = reproducibility. Probably
  both, with the crossing as source of truth for "what the loop ran against.")
- Should `dev-team-reviewer`'s gameability verdict be a **hard block** on freeze, or advisory
  with human override (itself logged)?
- Minimum bar for "judge-constructible" vs "stays human-gated" — what makes the rubric
  resistant to wishful classification?
- Does the loop need to *verify* the running loss's hash matches the signed crossing at each
  iteration (cheap tamper check), and refuse to proceed on mismatch?

## Recommendation

Build order once this doc is agreed: (1) `/classify` rubric + the honest exit, (2) the
loss-elicitation workflow emitting the triplet + signed spec, (3) the freeze crossing + the
per-iteration hash check. Ship behind the existing contract so nothing in the frozen judge or
the pore changes.
