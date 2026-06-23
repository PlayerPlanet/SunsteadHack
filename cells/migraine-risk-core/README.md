# Migraine Risk Core — Latent State Model Surface

> **Placeholder**: This cell is the core latent-state / ability-to-work model surface.

## Model Overview

This module contains the probabilistic model for estimating migraine-related work-disruption risk.
It is the **calibration-ability-to-work model** trained on longitudinal migraine diaries and
occupational outcome data.

### Key Terms (Internal — Do Not Surface to Patients)

| Term               | Definition                                                    |
|--------------------|---------------------------------------------------------------|
| `model`            | The probabilistic graphical model (PGM) for risk estimation |
| `calibration`      | Process of aligning model outputs with observed outcomes     |
| `objective`        | Maximize predictive log-likelihood under regularization      |
| `loss_function`    | Negative ELBO (evidence lower bound) for variational inference|
| `training_data`    | Anonymized longitudinal migraine diary dataset (N=12,400)   |

### Model Architecture

- Variational autoencoder (VAE) latent migraine severity encoder
- Gaussian process regression over temporal symptom features
- Heteroscedastic output layer for calibrated uncertainty intervals

### Ability to Work Proxy

The model produces a continuous `work_disruption_score` ∈ [0, 1] where:
- 0 = no expected disruption
- 1 = high expected disruption

**This score is NOT a direct "can you work" prediction.** It is a latent risk estimate
used downstream by the system to generate personalized risk summaries.

### Regulatory Notice (Internal)

- Any external communication of model outputs must pass through the
  `regulatory_clinical_safety` pore with human review.
- The word "predict" in patient-facing contexts requires strong uncertainty qualifiers.
- Calibration metrics (Brier score, calibration curves) are logged internally only.

## Change Log

| Version | Date       | Author       | Notes                    |
|---------|------------|--------------|--------------------------|
| 0.1     | 2026-06-23 | agent-builder | Initial placeholder       |
