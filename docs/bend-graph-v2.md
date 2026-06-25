# Membrane v2 — semantic risk buys real cross-lever generalization

> v1 keyed on the lever *name*, so on a never-seen lever it abstained 100% — it memorized, it didn't generalize. v2 keys on the lever's *risk profile* (data-loss-on-crash, result-semantics, recoverability), so a never-seen lever inherits the verdict of its profile-peers. Same shadow discipline, same frozen ruler.

## The headline — held-out (leave-one-lever-out)

| | committed cold calls | correct | false-clears | reclaimed cold | abstention |
|---|---|---|---|---|---|
| **v2 (risk profile)** | 10 | 10/10 | 0 | 4 | 33% |
| v1 (lever identity) | 0 | — | 0 | 0 | 100% |

**Marquee:** hold out `fsync` *entirely* → v2 predicts **escalate** cold (human verdict: reject); v1 → **abstain**. v2 learned `data_loss_on_crash=HIGH → reject` from `full_page_writes` and applied it to a lever it had never seen. v1 had no precedent for the *name*.

v2 makes **10 correct cold calls with 0 false-clears** on levers it never trained on; v1 makes **zero** committed calls there. That is the qualitative step — from memorization to generalization — and it is the result v1 structurally cannot produce.

## The Pareto frontier — reclaimed slack vs false-clear risk

v1 gave a single bend point. v2's decision is cost-theoretic — clear iff predicted `P(reject) < rho`, where `rho = C_human / C_false_clear` — so sweeping `rho` traces the whole tradeoff the operator can dial:

```
false-clears (0..1)
                                           #
                                            
                                            
                                            
                                            
                                            
                                            
                                            
                                            
#                    #                      
0                          reclaimed (0..8)
```
| rho | reclaimed | false-clears | remaining escalations |
|---|---|---|---|
| 0.05 | 0 | 0 | 15 |
| 0.1 | 4 | 0 | 11 |
| 0.15 | 4 | 0 | 11 |
| 0.2 | 4 | 0 | 11 |
| 0.25 | 4 | 0 | 11 |
| 0.3 | 8 | 1 | 6 |
| 0.35 | 8 | 1 | 6 |
| 0.4 | 8 | 1 | 6 |
| 0.5 | 8 | 1 | 6 |
| 0.7 | 8 | 1 | 6 |
| 0.9 | 8 | 1 | 6 |

The **zero-false-clear knee sits at `rho ≤ 0.25`: reclaim 4, no false-clears** — exactly where v1's single point lives. Past `rho = 0.3` the operator can reclaim 8 by accepting the one `synchronous_commit` reject as a false-clear. "Minimize false-clears" stops being a magic threshold and becomes a risk dial.

## Deployment (full-fit, rho=0.25)

False-clears **0**, reclaimed **4**, abstains on **synchronous_commit** (the bounded-tradeoff lever). Same honest headline as v1 — but now reached through risk semantics that generalize.

## The OOD abstain head

v2 abstains when it has no basis to stand behind a call — the manifesto's literal ask, now computable because the features are no longer degenerate:

| candidate | decision | why |
|---|---|---|
| result_semantics_rewrite | **abstain** | changes-result-semantics |
| unknown_systemic_lever | **abstain** | ood-unrecognised-lever |
| irreversible_table_rewrite | **abstain** | irreversible-never-cleared |

## The frozen risk taxonomy (domain priors, label-independent)

| lever | risk class | data-loss-on-crash | rationale |
|---|---|---|---|
| `fsync` | durability_switch | high | fsync=off stops flushing WAL/data to disk; a crash can leave an unrecoverable, corrupt cluster. Documented as unsafe unless the whole cluster is disposable. |
| `full_page_writes` | durability_switch | high | full_page_writes=off risks torn pages after a crash mid-write -> silent corruption. A correctness guarantee, not a tuning knob. |
| `synchronous_commit` | durability_tradeoff | bounded | synchronous_commit=off returns success before WAL is durably flushed; a crash loses only the last few committed txns, with NO corruption. A bounded, common latency/durability tradeoff — the genuinely ambiguous case. |
| `wal_level` | replication_capability | bounded | Lowering wal_level can break replicas / PITR; raising is safe. Restart-required, and the effect is on recoverability infrastructure, not the primary's data. |
| `shared_buffers` | memory_sizing | none | Pure memory-sizing for the buffer cache; affects throughput only and is fully recoverable. Restart-required (availability blast), no data risk. |
| `max_connections` | capacity_sizing | none | Connection-slot sizing; restart-required and high blast (bounces sessions) but no durability or result-semantics risk. |
| `max_wal_size` | wal_sizing | none | Soft cap on WAL between checkpoints; trades disk for checkpoint frequency. Online, fully recoverable, no data risk. |
| `work_mem` | memory_sizing | none | Per-node sort/hash memory; planner/throughput only, online, recoverable. |
| `random_page_cost` | planner_cost | none | Planner cost constant; changes plan choice, never results. Online, recoverable. |
| `effective_cache_size` | planner_cost | none | Planner hint about OS cache size; influences plans only. Online, recoverable. |

## Honesty caveat

> n is still 15. Trust the generalization *shape*, not the magnitudes. The risk taxonomy is domain priors from PostgreSQL docs, defined independent of the labels (see cleanroom/membrane/taxonomy.py) — the claim is *with a small fixed risk taxonomy the slack generalizes across levers*, not that the verdict is learned tabula rasa. Still shadow-only; the frozen pore made every real decision and is byte-for-byte unchanged. Giving the membrane the wheel and cross-domain transfer remain out of scope.

_Regenerate: `python scripts/eval_membrane_v2.py && python scripts/render_bend_graph_v2.py`._