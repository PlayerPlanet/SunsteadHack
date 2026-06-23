#!/usr/bin/env python3
"""
stage_membrane_unit.py

Scans cell surfaces for risky clinical claim phrases and model/calibration/objective terms.
Emits a structured JSON unit describing the membrane crossing probe result.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Risk flag patterns
CLINICAL_CLAIM_PATTERNS = [
    re.compile(r"predicts?\s+(whether|if|when|which)\s+you\s+can", re.IGNORECASE),
    re.compile(r"predicts?\s+your\s+(ability|capacity)\s+to\s+work", re.IGNORECASE),
    re.compile(r"will\s+(you|they|he|she)\s+(be\s+able\s+to\s+)?work", re.IGNORECASE),
    re.compile(r"diagnos", re.IGNORECASE),
    re.compile(r"treatment\s+for", re.IGNORECASE),
    re.compile(r"cure", re.IGNORECASE),
    re.compile(r"will\s+prevent", re.IGNORECASE),
    re.compile(r"clinical\s+(decision|trial|study)", re.IGNORECASE),
]

MODEL_SURFACE_PATTERNS = [
    re.compile(r"\bmodel\b", re.IGNORECASE),
    re.compile(r"\bcalibrat", re.IGNORECASE),
    re.compile(r"\bobjective\b", re.IGNORECASE),
    re.compile(r"\bloss\s+function\b", re.IGNORECASE),
    re.compile(r"\btraining\s+data\b", re.IGNORECASE),
    re.compile(r"\bmachine\s+learning\b", re.IGNORECASE),
    re.compile(r"\bai\b", re.IGNORECASE),
    re.compile(r"\bml\b", re.IGNORECASE),
    re.compile(r"\bneural\s+network\b", re.IGNORECASE),
]

CELL_SCAN_ROOTS = [
    "cells/clinical-claims-surface",
    "cells/migraine-risk-core",
    "cells/operator-playbooks",
]


def scan_directory(root: str) -> tuple[list[str], list[str]]:
    """Return (clinical_hits, model_hits) for all .md files under root."""
    clinical_hits = []
    model_hits = []
    path = Path(root)
    if not path.exists():
        return clinical_hits, model_hits
    for md_file in path.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            try:
                content = md_file.read_text(encoding="utf-8-sig")
            except Exception:
                continue
        for pattern in CLINICAL_CLAIM_PATTERNS:
            if pattern.search(content):
                for line in content.splitlines():
                    if pattern.search(line):
                        clinical_hits.append(f"{md_file}: {line.strip()}")
                        break
        for pattern in MODEL_SURFACE_PATTERNS:
            if pattern.search(content):
                for line in content.splitlines():
                    if pattern.search(line):
                        model_hits.append(f"{md_file}: {line.strip()}")
                        break
    return clinical_hits, model_hits


def determine_pore(clinical_hits: list, model_hits: list) -> str:
    """Suggest a pore based on which surface was breached.

    Always returns one of the three human-review pores:
    - regulatory_clinical_safety: clinical claims detected
    - generative_model: model/calibration surface detected
    - human_relational: no surfaces breached (benign fallback)
    """
    if clinical_hits and model_hits:
        return "regulatory_clinical_safety"
    elif clinical_hits:
        return "regulatory_clinical_safety"
    elif model_hits:
        return "generative_model"
    return "human_relational"


def compute_blast_radius(clinical_hits: list, model_hits: list) -> dict:
    """Compute a rough blast radius estimate."""
    return {
        "clinical_claim_files": len(set(h.split(":")[0] for h in clinical_hits)),
        "model_surface_files": len(set(h.split(":")[0] for h in model_hits)),
        "total_flags": len(clinical_hits) + len(model_hits),
    }


def main():
    parser = argparse.ArgumentParser(description="Stage membrane-crossing unit probe")
    parser.add_argument("--actor", default="agent-builder-001")
    parser.add_argument("--output", default="artifacts/staged-unit.json")
    args = parser.parse_args()

    all_clinical_hits = []
    all_model_hits = []
    affected_paths = []

    for cell_root in CELL_SCAN_ROOTS:
        clinical, model = scan_directory(cell_root)
        all_clinical_hits.extend(clinical)
        all_model_hits.extend(model)
        if clinical or model:
            affected_paths.append(cell_root)

    claim_surface_touched = len(all_clinical_hits) > 0
    model_surface_touched = len(all_model_hits) > 0
    suggested_pore = determine_pore(all_clinical_hits, all_model_hits)
    blast_radius = compute_blast_radius(all_clinical_hits, all_model_hits)
    requires_human_judgment = claim_surface_touched or model_surface_touched

    if claim_surface_touched:
        agent_recommendation = "ESCALATE: Risky clinical claim detected in patient-facing surface. Rewrite required before crossing membrane."
    elif model_surface_touched:
        agent_recommendation = "FLAG: Model/calibration surface touched. Ensure transparency disclosures present."
    else:
        agent_recommendation = "CLEAR: No membrane-crossing risk detected."

    checks = []
    if claim_surface_touched:
        checks.append({"check": "clinical_claim_gate", "status": "FAIL", "hits": all_clinical_hits})
    else:
        checks.append({"check": "clinical_claim_gate", "status": "PASS", "hits": []})
    if model_surface_touched:
        checks.append({"check": "model_surface_gate", "status": "FLAG", "hits": all_model_hits})
    else:
        checks.append({"check": "model_surface_gate", "status": "PASS", "hits": []})

    evidence = {
        "clinical_claim_evidence": all_clinical_hits,
        "model_surface_evidence": all_model_hits,
        "scanned_cells": CELL_SCAN_ROOTS,
    }

    unit = {
        "unit_id": f"membrane-probe-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "unit_type": "membrane_crossing_probe",
        "source": "stage_membrane_unit.py",
        "actor": args.actor,
        "repo": "SunsteadHack",
        "affected_paths": affected_paths,
        "claim_surface_touched": claim_surface_touched,
        "model_surface_touched": model_surface_touched,
        "suggested_pore": suggested_pore,
        "blast_radius": blast_radius,
        "requires_human_judgment": requires_human_judgment,
        "agent_recommendation": agent_recommendation,
        "checks": checks,
        "evidence": evidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(unit, indent=2), encoding="utf-8")
    print(f"[stage_membrane_unit] Wrote {output_path}")
    print(f"[stage_membrane_unit] Clinical claim surface touched: {claim_surface_touched}")
    print(f"[stage_membrane_unit] Model surface touched: {model_surface_touched}")
    print(f"[stage_membrane_unit] Suggested pore: {suggested_pore}")
    print(f"[stage_membrane_unit] Human judgment required: {requires_human_judgment}")
    print(json.dumps(unit, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
