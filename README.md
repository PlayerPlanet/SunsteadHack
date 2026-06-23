# SunsteadHack — ease-health Membrane-Crossing Probe

## Project

Tangled/ease-health membrane-crossing probe scaffold. Monitors clinical claim surfaces
and model/calibration surfaces, suggests regulated crossing pores, and logs human judgments.

## Artifacts

| Path                                     | Purpose                                      |
|------------------------------------------|----------------------------------------------|
| `.tangled/workflows/membrane.yml`        | Tangled spindle workflow (nixery engine)     |
| `scripts/stage_membrane_unit.py`         | Membrane probe: scans cells, emits JSON      |
| `scripts/record_judgment.py`             | Records human judgment to escalation log     |
| `cells/clinical-claims-surface/`         | Patient-facing copy (HIGH risk surface)      |
| `cells/migraine-risk-core/`              | Internal model/calibration surface          |
| `cells/operator-playbooks/`              | Membrane rules and crossing pore definitions|
| `cells/agent-escalation-log/crossings.yaml` | Append-only escalation log              |
| `docs/membrane-trial.md`                 | Run instructions and Tangled mapping         |

## Quick Start

```bash
# Run the membrane probe
python scripts/stage_membrane_unit.py \
  --actor agent-builder-001 \
  --output artifacts/staged-unit.json

# Record human judgment
python scripts/record_judgment.py \
  --input artifacts/staged-unit.json \
  --decision modify \
  --pore regulatory_clinical_safety \
  --judge human-regulatory-001 \
  --rationale "Clinical claim too strong for patient-facing copy." \
  --transform "Rewrite to: estimates personalized migraine-related work-disruption risk."
```

## Three Pores

| Pore                        | Purpose                                    |
|-----------------------------|--------------------------------------------|
| `regulatory_clinical_safety` | Gate patient-facing clinical claims     |
| `generative_model`           | Gate model/calibration/objective changes |
| `human_relational`           | Gate human-facing relational commitments |

## Cells

| Cell                          | Risk   |
|-------------------------------|--------|
| `clinical-claims-surface`     | HIGH   |
| `migraine-risk-core`          | MEDIUM |
| `operator-playbooks`          | LOW    |

## Homeserver Deployment

The `scripts/tangled_webhook_receiver.py` is a minimal, dependency-free webhook
receiver that accepts Tangled push webhooks and writes raw event envelopes to
Stage 0 inbox. See [docs/homeserver-deployment.md](docs/homeserver-deployment.md)
for full deployment topology, systemd setup, Cloudflare tunnel configuration,
and Tangled UI instructions.

## Notes

- All probe runs exit 0; risky flags are recorded in JSON output, not exceptions.
- Escalation log (`crossings.yaml`) is append-only.
- No external packages required — pure Python 3 standard library.
- Webhook receiver uses only Python stdlib (`http.server`).
