# 03 — Lexicon Design (Draft)

Draft custom lexicons that promote the membrane probe's flat `crossings.yaml` into signed
ATProto records. **These are drafts for discussion**, not final — field names and required/
optional status are up for debate. NSID prefix `com.sunstead.*` (placeholder — swap for a domain
we actually control before writing records).

Three record types model the governance loop:

```
com.sunstead.crossing   →  a proposed change wanting to cross a pore (the request + evidence)
com.sunstead.judgment   →  a verdict on a crossing (approve/modify/reject/escalate)
com.sunstead.outcome    →  what actually happened after applying (before/after metrics)
```

Each references the others (and `sh.tangled.*` records) by AT-URI, so an appview can join them
into a timeline: Tangled PR → crossing → judgment → outcome.

## `com.sunstead.crossing`

```json
{
  "lexicon": 1,
  "id": "com.sunstead.crossing",
  "defs": {
    "main": {
      "type": "record",
      "key": "tid",
      "record": {
        "type": "object",
        "required": ["actor", "pore", "surface", "action", "riskLevel", "createdAt"],
        "properties": {
          "actor":   { "type": "string", "format": "did", "description": "Agent that proposed the change" },
          "pore":    { "type": "string", "description": "e.g. data_schema_safety | data_cost_envelope | data_blast_radius" },
          "surface": { "type": "string", "description": "Cell/surface touched, e.g. data-infra-surface" },
          "subject": { "type": "string", "format": "at-uri", "description": "Optional ref to the sh.tangled.repo.pull / .issue / commit that triggered this" },
          "action":  { "type": "ref", "ref": "#actionSpec", "description": "The proposed Aiven mutation" },
          "evidence":{ "type": "ref", "ref": "#evidence", "description": "Why now: metrics, projected cost, compat result" },
          "riskLevel": { "type": "string", "enum": ["LOW", "MEDIUM", "HIGH"] },
          "requiresHumanJudgment": { "type": "boolean" },
          "rationale": { "type": "string", "maxLength": 3000 },
          "createdAt": { "type": "string", "format": "datetime" }
        }
      }
    },
    "actionSpec": {
      "type": "object",
      "required": ["tool", "summary"],
      "properties": {
        "tool":    { "type": "string", "description": "e.g. aiven_pg_write | aiven_service_update | aiven_kafka_topic_create" },
        "summary": { "type": "string", "description": "Human-readable description of the mutation" },
        "params":  { "type": "string", "description": "JSON-encoded params (credentials redacted)" },
        "reversible": { "type": "boolean" }
      }
    },
    "evidence": {
      "type": "object",
      "properties": {
        "metrics":       { "type": "string", "description": "JSON-encoded triggering metrics" },
        "projectedCost": { "type": "string", "description": "From aiven_service_plan_pricing" },
        "compatResult":  { "type": "string", "description": "schema-compat / correctness check outcome" }
      }
    }
  }
}
```

## `com.sunstead.judgment`

```json
{
  "lexicon": 1,
  "id": "com.sunstead.judgment",
  "defs": {
    "main": {
      "type": "record",
      "key": "tid",
      "record": {
        "type": "object",
        "required": ["crossing", "judge", "decision", "createdAt"],
        "properties": {
          "crossing":  { "type": "string", "format": "at-uri", "description": "The com.sunstead.crossing being judged" },
          "judge":     { "type": "string", "format": "did", "description": "Human OR agent DID — distinguishes who decided" },
          "judgeKind": { "type": "string", "enum": ["human", "agent"] },
          "decision":  { "type": "string", "enum": ["approve", "modify", "reject", "escalate"] },
          "pore":      { "type": "string" },
          "rationale": { "type": "string", "maxLength": 3000 },
          "transform": { "type": "string", "description": "If decision=modify: the required change" },
          "confidence":   { "type": "number", "description": "If judgeKind=agent: calibrated confidence (v2 amortized judge)" },
          "precedents":   { "type": "array", "items": { "type": "string", "format": "at-uri" }, "description": "If agent: prior judgments relied on" },
          "modelVersion": { "type": "string", "description": "If agent: judge model/version for audit" },
          "emergencyOverride": { "type": "boolean" },
          "createdAt": { "type": "string", "format": "datetime" }
        }
      }
    }
  }
}
```

> The `judge` DID + `judgeKind` is what makes amortization (v2) auditable: an agent-issued
> verdict is signed by the *agent's* DID and carries `confidence` + `precedents` + `modelVersion`,
> so "why did the agent approve this" is answerable from the record itself.

## `com.sunstead.outcome` (optional, nice-to-have)

```json
{
  "lexicon": 1,
  "id": "com.sunstead.outcome",
  "defs": {
    "main": {
      "type": "record",
      "key": "tid",
      "record": {
        "type": "object",
        "required": ["crossing", "applied", "createdAt"],
        "properties": {
          "crossing": { "type": "string", "format": "at-uri" },
          "judgment": { "type": "string", "format": "at-uri" },
          "applied":  { "type": "boolean", "description": "Was the action actually executed?" },
          "rolledBack": { "type": "boolean" },
          "beforeMetrics": { "type": "string", "description": "JSON-encoded" },
          "afterMetrics":  { "type": "string", "description": "JSON-encoded" },
          "createdAt": { "type": "string", "format": "datetime" }
        }
      }
    }
  }
}
```

## Open design questions

- **Where do records live?** Crossing on the *agent's* PDS, judgment on the *judge's* PDS
  (so each is signed by its true author), outcome on the agent's PDS. Confirm this matches how we
  provision identities (see spikes).
- **Embedding vs JSON-string params.** ATProto prefers typed fields; we're using JSON-encoded
  strings for `params`/`metrics` to stay flexible during exploration. Tighten later.
- **Linking to `sh.tangled.*`.** Need to confirm AT-URI refs to Tangled records resolve cleanly
  (spike 5).
- **Domain for the NSID.** `com.sunstead.*` is a placeholder; pick a domain we control.
