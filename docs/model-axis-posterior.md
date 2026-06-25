# Model axis — posterior over the escalation region

> Beta-Binomial posterior (Jeffreys prior) over each proposer's escalation behaviour. Overlapping credible intervals ⇒ the apparent difference may be noise; separated ⇒ real.

## Escalation rate (all drift)

| model | k/n | posterior mean | 95% CrI | P(highest) |
|---|---|---|---|---|
| haiku-4.5 | 7/60 | 12.3% | [5.4%, 21.5%] | 1% |
| sonnet-4.6 | 17/60 | 28.7% | [18.1%, 40.6%] | 92% |
| opus-4.5 | 7/60 | 12.3% | [5.4%, 21.5%] | 1% |
| opus-4.8 | 9/60 | 15.6% | [7.7%, 25.6%] | 3% |
| minimax-m2.5 | 3/40 | 8.5% | [2.2%, 18.7%] | 0% |
| minimax-m3 | 5/40 | 13.4% | [4.9%, 25.2%] | 2% |

## High-drift escalation rate (drift ≥ 0.8)

| model | k/n | posterior mean | 95% CrI | P(highest) |
|---|---|---|---|---|
| haiku-4.5 | 7/11 | 62.5% | [34.8%, 86.3%] | 5% |
| sonnet-4.6 | 10/11 | 87.5% | [64.7%, 99.0%] | 88% |
| opus-4.5 | 6/11 | 54.2% | [27.0%, 80.0%] | 2% |
| opus-4.8 | 6/11 | 54.2% | [27.0%, 80.0%] | 1% |
| minimax-m2.5 | 3/7 | 43.8% | [13.9%, 76.5%] | 1% |
| minimax-m3 | 4/7 | 56.2% | [23.4%, 86.1%] | 4% |

## False-stop rate (reclaimable slack)

| model | k/n | posterior mean | 95% CrI | P(highest) |
|---|---|---|---|---|
| haiku-4.5 | 3/7 | 43.8% | [13.9%, 76.5%] | 3% |
| sonnet-4.6 | 12/17 | 69.4% | [47.0%, 87.8%] | 30% |
| opus-4.5 | 2/7 | 31.2% | [6.5%, 64.8%] | 0% |
| opus-4.8 | 7/9 | 75.0% | [45.6%, 95.1%] | 59% |
| minimax-m2.5 | 1/3 | 37.5% | [3.9%, 82.3%] | 4% |
| minimax-m3 | 2/5 | 41.7% | [9.4%, 79.1%] | 4% |

## Selected pairwise dominance (escalation rate)

- P(sonnet-4.6 escalates more than minimax-m2.5) = **100%**
- P(sonnet-4.6 escalates more than haiku-4.5) = **99%**
- P(sonnet-4.6 escalates more than opus-4.5) = **99%**
- P(sonnet-4.6 escalates more than minimax-m3) = **97%**
- P(sonnet-4.6 escalates more than opus-4.8) = **96%**
- P(opus-4.8 escalates more than minimax-m2.5) = **87%**

> Jeffreys prior Beta(0.5,0.5); 200k MC draws. Wide intervals are the honest consequence of modest n + real-LLM sampling — the reason to show a posterior, not a bare percentage.
