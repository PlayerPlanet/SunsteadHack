# Patient Copy — Clinical Claims Surface

## Risky Original (DO NOT USE without rewrite)

> "Our model predicts whether you can work tomorrow."

## Risk Assessment

- **Claim type**: Direct predictive claim about ability to work
- **Severity**: HIGH — Patient-facing, no uncertainty language, no medical disclaimers
- **Membrane crossing**: REQUIRES human judgment before use
- **Suggested rewrite**: See below

## Safe Rewrite

> "This tool estimates personalized migraine-related work-disruption risk based on your symptom patterns. It is not a medical diagnosis. Always consult a healthcare professional for medical advice."

## Notes

- Any patient-facing communication that mentions "predicts whether you can work" is a
  regulatory_clinical_safety membrane breach.
- Model/calibration terms (model, training, objective) must not appear in patient-facing copy.
- All claims must include uncertainty language and a medical disclaimer.

## Membrane Rules Reference

See: `cells/operator-playbooks/membrane-rules.md`

## Change Log

| Version | Date       | Author        | Notes                     |
|---------|------------|---------------|---------------------------|
| 1.0     | 2026-06-23 | agent-builder | Initial risky draft       |
| 1.1     | 2026-06-23 | human-regulatory-001 | Rewrite required |
