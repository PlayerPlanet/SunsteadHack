# Membrane Rules — Operator Playbooks

This document defines the three **membrane pores** and the **crossing rules** for the
Tangled/ease-health membrane-crossing probe system.

---

## Overview

A **membrane** separates cell surfaces in the ease-health monorepo:

| Cell               | Surface Type  | Risk Level |
|--------------------|---------------|------------|
| `clinical-claims-surface` | Patient-facing copy | HIGH |
| `migraine-risk-core`       | Internal model/calibration surface | MEDIUM |
| `operator-playbooks`       | Internal runbooks / rules | LOW |

A **pore** is a controlled crossing point that allows content to pass from one cell to another
subject to checks and human review.

---

## Three Pores

### 1. `regulatory_clinical_safety`

**Purpose**: Gate all patient-facing clinical claims.

**Crossing Rules**:
- ALL patient-facing copy must pass the `clinical_claim_gate` check.
- No direct predictive claims about ability to work, diagnosis, treatment, or cure without
  qualified uncertainty language and a medical disclaimer.
- Model/calibration terms (model, AI, ML, training data, objective, loss function) are
  PROHIBITED in patient-facing copy.
- Human review by `human-regulatory-001` (or equivalent) is REQUIRED before crossing.
- If `claim_surface_touched == True` in the probe result, MUST use this pore.

**Examples of BLOCKED claims**:
- "Our model predicts whether you can work tomorrow."
- "This AI will cure your migraines."
- "Our system diagnoses migraine with 95% accuracy."

**Examples of ALLOWED claims**:
- "This tool estimates personalized migraine-related work-disruption risk."
- "May help reduce migraine frequency. Consult your doctor."

---

### 2. `model_transparency`

**Purpose**: Enable model information to reach developer/ops audiences with appropriate disclosures.

**Crossing Rules**:
- Model/calibration terms are permitted but must include transparency disclosures.
- Calibration metrics (Brier score, ELBO, calibration curves) may be shared with developers.
- Training data provenance must be documented.
- If `model_surface_touched == True` AND `claim_surface_touched == False`, this pore is suggested.

**Required Disclosures**:
- "This information describes our internal model. It is not medical advice."
- "Model performance metrics are based on historical data and may not predict future outcomes."

---

### 3. `public_benign`

**Purpose**: Allow purely informational, non-clinical, non-model content to circulate freely.

**Crossing Rules**:
- No clinical claims (diagnosis, treatment, cure, work prediction).
- No model/calibration/internal terms.
- No patient-facing content whatsoever.
- General educational information about migraines is permitted.
- If both `claim_surface_touched == False` and `model_surface_touched == False`,
  this pore is suggested.

---

## Crossing Process

1. **Probe**: Run `python scripts/stage_membrane_unit.py` to scan all cells.
2. **Result**: JSON output indicates which surfaces were touched and suggests a pore.
3. **Decision**:
   - If `requires_human_judgment == True`, escalate to human judge.
   - Human runs `python scripts/record_judgment.py --decision <modify|approve|reject> ...`
4. **Log**: All crossings are append-only logged to `cells/agent-escalation-log/crossings.yaml`.

---

## Emergency Override

In case of urgent operational needs, a `human-regulatory-001` judge may invoke emergency override
by appending `emergency_override: true` to the judgment entry and providing written rationale.

---

## Change Log

| Version | Date       | Author        | Notes                         |
|---------|------------|---------------|-------------------------------|
| 1.0     | 2026-06-23 | agent-builder | Initial membrane rule set      |
