# Membrane Trial — Tangled Workflow Run Instructions

## Overview

This document describes how to run the Tangled/ease-health membrane-crossing probe using
the `membrane.yml` workflow.

---

## Architecture

### Cells (Surfaces)

| Cell Path                           | Surface Type            | Risk   |
|-------------------------------------|-------------------------|--------|
| `cells/clinical-claims-surface/`    | Patient-facing copy     | HIGH   |
| `cells/migraine-risk-core/`         | Internal model surface  | MEDIUM |
| `cells/operator-playbooks/`         | Internal runbooks       | LOW    |
| `cells/agent-escalation-log/`       | Escalation log (append) | —      |

### Pores

| Pore                    | Purpose                                      | Human Review |
|-------------------------|----------------------------------------------|--------------|
| `regulatory_clinical_safety` | Gate patient-facing clinical claims     | REQUIRED    |
| `generative_model`      | Share model/calibration info with devs      | REQUIRED    |
| `human_relational`      | Human-facing relational/experiential content | REQUIRED    |

> **Note:** `human_relational` serves as the fallback pore for benign units (no clinical claim or model surface detected). While it is a human-review pore, it does **not** require human judgment to be required for crossing — it simply indicates the unit is human-facing relational content. The `requires_human_judgment` flag remains `false` for benign units because no risky surfaces were breached.

---

## Tangled Workflow Mapping

The `.tangled/workflows/membrane.yml` workflow maps to the following concepts:

| Tangled Concept       | ease-health Implementation                   |
|-----------------------|----------------------------------------------|
| `engine: "nixery"`    | Execution engine (declarative workflow runner)|
| `dependencies: nixpkgs: [python3]` | Required runtime dependency         |
| `when: event: ["push", "manual"], branch: ["main", "master"]` | Auto-runs on push to main/master; on-demand via Tangled CLI |
| `steps:`             | Named steps with `command:` field            |

### Workflow Steps

```yaml
# .tangled/workflows/membrane.yml
name: membrane
description: Tangled spindle workflow for membrane-crossing probe / ease-health clinical claim gate
engine: "nixery"
when:
  - event: ["push", "manual"]
    branch: ["main", "master"]
dependencies:
  nixpkgs: [python3]
steps:
  - name: "Stage membrane unit"
    command: |
      python3 scripts/stage_membrane_unit.py --actor "${AGENT_ACTOR:-agent-builder-001}" --output artifacts/staged-unit.json
      cat artifacts/staged-unit.json
```

---

## Manual Run Instructions

### Step 1 — Run the Membrane Probe

```bash
python scripts/stage_membrane_unit.py \
  --actor agent-builder-001 \
  --output artifacts/staged-unit.json
```

**Expected output**: JSON probe result with:
- `claim_surface_touched`: `true` if risky clinical claims found
- `model_surface_touched`: `true` if model/calibration terms found
- `suggested_pore`: recommended pore for crossing
- `requires_human_judgment`: `true` if clinical claim surface OR model surface was touched

### Step 2 — Record Human Judgment

```bash
python scripts/record_judgment.py \
  --input artifacts/staged-unit.json \
  --decision modify \
  --pore regulatory_clinical_safety \
  --judge human-regulatory-001 \
  --rationale "Clinical claim too strong for patient-facing copy." \
  --transform "Rewrite to: estimates personalized migraine-related work-disruption risk."
```

This appends an entry to `cells/agent-escalation-log/crossings.yaml`.

### Step 3 — Review the Escalation Log

```bash
cat cells/agent-escalation-log/crossings.yaml
```

---

## Probe Output Fields

| Field                      | Type    | Description                                      |
|----------------------------|---------|--------------------------------------------------|
| `unit_id`                  | string  | Unique probe unit ID (timestamp-based)           |
| `unit_type`                | string  | Always `membrane_crossing_probe`                |
| `actor`                    | string  | Agent that ran the probe                         |
| `affected_paths`           | list    | Cell paths that had hits                         |
| `claim_surface_touched`    | bool    | True if clinical claim patterns found           |
| `model_surface_touched`    | bool    | True if model/calibration patterns found        |
| `suggested_pore`           | string  | Recommended pore name                           |
| `requires_human_judgment`  | bool    | True if clinical claim surface or model surface was touched |
| `blast_radius`             | dict    | Count of affected files and total flags         |
| `agent_recommendation`     | string  | Agent's recommendation string                    |
| `checks`                   | list    | Per-gate check results (PASS/FAIL/FLAG)          |
| `evidence`                 | dict    | Raw pattern hits for both surfaces               |
| `created_at`               | string  | ISO 8601 UTC timestamp                           |

---

## Decision Options

| Decision  | Description                                                      |
|-----------|------------------------------------------------------------------|
| `modify`  | Content needs rewrite before crossing                            |
| `approve` | Content cleared to cross via specified pore                      |
| `reject`  | Content blocked; cannot cross any pore                          |
| `escalate`| Forwarded to higher authority for decision                      |

---

## Pore Decision Table

| claim_surface_touched | model_surface_touched | suggested_pore            |
|------------------------|-----------------------|----------------------------|
| true                   | true/false            | `regulatory_clinical_safety` |
| false                  | true                  | `generative_model`         |
| false                  | false                 | `human_relational` (benign fallback) |

---

## Risk Patterns Detected

### Clinical Claim Patterns (HIGH severity)
- `predicts whether/if/when/which you can work`
- `predicts your ability/capacity to work`
- `diagnos`, `treatment for`, `cure`, `will prevent`

### Model Surface Patterns (MEDIUM severity)
- `model`, `calibrat`, `objective`, `loss function`
- `training data`, `machine learning`, `ai`, `ml`
- `neural network`

---

## Change Log

| Version | Date       | Author        | Notes                      |
|---------|------------|---------------|----------------------------|
| 1.0     | 2026-06-23 | agent-builder | Initial membrane trial doc |
