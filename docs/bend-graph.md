# The bend graph — the learned membrane, in shadow, against a frozen ruler

> **Issue #20.** Deploy the learned membrane as a SHADOW gate — it logs what it *would* decide but never touches the wheel — and show the longitudinal escalation curve bend down *without moving the frozen ruler.*

## The figure

```
escalations (0..15)  · frozen   # membrane-shadow
                                                       ·
                                                        
                                             ·········· 
                                       ······          #
                                  ·····      ########## 
                             ·····        ###           
                         ····#############              
                        #####                           
                                                        
                  ######                                
                                                        
##################                                      
0                                            work (144 steps)
```
Frozen pore raises **15** escalations over 144 steps. The membrane-shadow would wave through **4** of them (clean-precedent false stops), leaving **11** — a **26.7% reduction** in human escalations, with **zero false-clears**. Abstentions and escalates still count as escalations, so the bend is bounded by exactly the slack the membrane can stand behind.

## What the membrane decided (full-fit deployment gate)

| lever | membrane | P(approve) | human verdicts |
|---|---|---|---|
| `synchronous_commit` | **abstain** | 0.714 | reject×1, approve×4 |
| `shared_buffers` | **auto_clear** | 0.75 | approve×2 |
| `max_wal_size` | **auto_clear** | 0.75 | approve×2 |
| `fsync` | **escalate** | 0.2 | reject×3 |
| `full_page_writes` | **escalate** | 0.2 | reject×3 |

- **False-clear rate: 0%** (0/15) — the dangerous error (auto-clearing a human-reject) never happens: a lever with *any* reject in its record is never auto-cleared.
- **Reclaimed false-stops: 4** — clean-precedent stops the membrane would wave through (the bend).
- **Abstention concentrates on `synchronous_commit`** — the one lever that drew opposite human verdicts. The membrane refuses to call the irreducible judgment and asks a human, exactly as a calibrated agent should.

## The honesty guardrail — held-out (leave-one-lever-out)

On a lever it has **never seen**, the membrane abstains **100%** of the time and auto-clears **nothing** (false-clear rate **0%**). It does not hallucinate generalization: confronted with a novel lever it asks a human rather than guessing. This is the abstain head working, and it is why the bend only appears for levers with precedent.

## Calibration / robustness (leave-one-out on n=15)

- Expected calibration error (ECE): **0.3333** (n=15 — crude but honest).
- The single LOO error is **1 false-clear** — the lone `synchronous_commit` reject, which when held out leaves that lever looking pure-approve. This is the published 93.3% residual, and it is *precisely why* the deployment gate (which sees the reject) abstains on `synchronous_commit`: erring toward asking turns the one irreducible case into an abstention instead of a dangerous clear.

| P(approve) bin | n | mean P(approve) | observed approve rate |
|---|---|---|---|
| 0.2-0.4 | 6 | 0.25 | 0.0 |
| 0.6-0.8 | 8 | 0.667 | 1.0 |
| 0.8-1.0 | 1 | 0.833 | 0.0 |

## Honesty caveat

> This is a **shadow** measurement of learnability under held-out drift — not a deployed self-aware agent, and not cross-domain. The membrane never acted; the frozen pore (`cleanroom/pore`) made every real decision and is byte-for-byte unchanged. Latency is modeled (live p99 proven separately). The held-out split is leave-one-lever-out, not held-out-regime: the frozen pore concentrates 100% of escalations in the `regime_break` tier, so a held-out-regime split has zero training labels — leave-one-lever-out is the honest, stricter analogue.

_Regenerate: `python scripts/eval_membrane.py && python scripts/render_bend_graph.py`._