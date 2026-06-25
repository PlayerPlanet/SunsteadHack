export const mockStats = {
  totalExperiments: 144,
  activeRuns: 2,
  bestP99: 25.3,
  baselineP99: 58.4,
  escalationRate: 10.4,
  autonomousCorrectness: 94.2,
};

export const mockBoundaryCurve = [
  { drift: 0.0, escalation_rate: 0, correctness: 98, n: 24 },
  { drift: 0.1, escalation_rate: 0, correctness: 97, n: 18 },
  { drift: 0.2, escalation_rate: 0, correctness: 95, n: 12 },
  { drift: 0.3, escalation_rate: 0, correctness: 94, n: 10 },
  { drift: 0.4, escalation_rate: 5, correctness: 91, n: 8 },
  { drift: 0.5, escalation_rate: 8, correctness: 88, n: 8 },
  { drift: 0.6, escalation_rate: 18, correctness: 79, n: 6 },
  { drift: 0.7, escalation_rate: 42, correctness: 61, n: 6 },
  { drift: 0.8, escalation_rate: 67, correctness: 41, n: 8 },
  { drift: 0.9, escalation_rate: 90, correctness: 18, n: 21 },
  { drift: 1.0, escalation_rate: 100, correctness: 0, n: 3 },
];

export const mockLongitudinal = [
  { volume: 10, escalations_frozen: 1, escalations_membrane: 1 },
  { volume: 20, escalations_frozen: 2, escalations_membrane: 2 },
  { volume: 30, escalations_frozen: 3, escalations_membrane: 2 },
  { volume: 40, escalations_frozen: 4, escalations_membrane: 3 },
  { volume: 60, escalations_frozen: 6, escalations_membrane: 4 },
  { volume: 80, escalations_frozen: 8, escalations_membrane: 5 },
  { volume: 100, escalations_frozen: 10, escalations_membrane: 6 },
  { volume: 120, escalations_frozen: 12, escalations_membrane: 7 },
  { volume: 144, escalations_frozen: 15, escalations_membrane: 11 },
];

export const mockRuns = [
  {
    run_id: "run-pg-001",
    task_id: "pg-latency-v1",
    model: "claude-haiku-4-5",
    state: "running",
    iterations_done: 8,
    iterations_target: 20,
    best_p99: 31.2,
    started_at: new Date(Date.now() - 12 * 60000).toISOString(),
  },
  {
    run_id: "run-quant-001",
    task_id: "quant-walkforward",
    model: "claude-haiku-4-5",
    state: "running",
    iterations_done: 5,
    iterations_target: 15,
    best_p99: null,
    started_at: new Date(Date.now() - 4 * 60000).toISOString(),
  },
  {
    run_id: "run-pg-000",
    task_id: "pg-latency-v1",
    model: "claude-haiku-4-5",
    state: "completed",
    iterations_done: 20,
    iterations_target: 20,
    best_p99: 25.3,
    started_at: new Date(Date.now() - 90 * 60000).toISOString(),
  },
];

export const mockExperiments = [
  { n: 1, p99: 58.4, decision: "keep", action: "CREATE INDEX ON orders(user_id)" },
  { n: 2, p99: 48.1, decision: "keep", action: "SET work_mem = '64MB'" },
  { n: 3, p99: 48.1, decision: "discard", action: "SET jit = 'off'" },
  { n: 4, p99: 41.7, decision: "keep", action: "CREATE INDEX ON orders(created_at)" },
  { n: 5, p99: 41.7, decision: "discard", action: "SET random_page_cost = 1.5" },
  { n: 6, p99: 38.2, decision: "keep", action: "CREATE INDEX ON orders(user_id, created_at)" },
  { n: 7, p99: 38.2, decision: "escalated", action: "DROP INDEX orders_pkey" },
  { n: 8, p99: 33.9, decision: "keep", action: "SET effective_cache_size = '1GB'" },
  { n: 9, p99: 33.9, decision: "discard", action: "SET enable_hashjoin = 'off'" },
  { n: 10, p99: 29.4, decision: "keep", action: "REWRITE query to use CTE" },
  { n: 11, p99: 29.4, decision: "discard", action: "SET max_parallel_workers = 4" },
  { n: 12, p99: 25.3, decision: "keep", action: "CREATE INDEX ON orders(status) WHERE status = 'pending'" },
];

// Curve format matching tool_read_curve output (handoff spec field names)
export const mockCurve = [
  { n: 1, candidate_p99: 58.4, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "index", params: { table: "orders", columns: ["user_id"] } }, correctness_ok: true },
  { n: 2, candidate_p99: 48.1, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "guc", params: { name: "work_mem", value: "64MB" } }, correctness_ok: true },
  { n: 3, candidate_p99: 49.2, baseline_p99: 58.4, decision: "reject", within_noise: true, candidate: { type: "guc", params: { name: "jit", value: "off" } }, correctness_ok: true },
  { n: 4, candidate_p99: 41.7, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "index", params: { table: "orders", columns: ["created_at"] } }, correctness_ok: true },
  { n: 5, candidate_p99: 42.1, baseline_p99: 58.4, decision: "reject", within_noise: true, candidate: { type: "guc", params: { name: "random_page_cost", value: "1.5" } }, correctness_ok: true },
  { n: 6, candidate_p99: 38.2, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "index", params: { table: "orders", columns: ["user_id", "created_at"] } }, correctness_ok: true },
  { n: 7, candidate_p99: 38.2, baseline_p99: 58.4, decision: "reject", within_noise: false, candidate: { type: "index_drop", params: { name: "orders_pkey" } }, correctness_ok: false },
  { n: 8, candidate_p99: 33.9, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "guc", params: { name: "effective_cache_size", value: "1GB" } }, correctness_ok: true },
  { n: 9, candidate_p99: 34.5, baseline_p99: 58.4, decision: "reject", within_noise: true, candidate: { type: "guc", params: { name: "enable_hashjoin", value: "off" } }, correctness_ok: true },
  { n: 10, candidate_p99: 29.4, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "index", params: { table: "orders", columns: ["status"], where: "status = 'pending'" } }, correctness_ok: true },
  { n: 11, candidate_p99: 29.8, baseline_p99: 58.4, decision: "reject", within_noise: true, candidate: { type: "guc", params: { name: "max_parallel_workers", value: "4" } }, correctness_ok: true },
  { n: 12, candidate_p99: 25.3, baseline_p99: 58.4, decision: "keep", within_noise: false, candidate: { type: "index", params: { table: "orders", columns: ["status"], where: "status = 'pending'" } }, correctness_ok: true },
];

export const mockEscalations = [
  {
    id: 1,
    pore: "blast_radius",
    risk_level: "HIGH",
    action: { type: "guc", params: { name: "synchronous_commit", value: "off" } },
    rationale: "Disabling synchronous_commit trades durability for latency — up to 200ms of committed transactions could be lost on a hard crash.",
    created_at: new Date(Date.now() - 8 * 60000).toISOString(),
    judgment: null,
  },
  {
    id: 2,
    pore: "irreversible",
    risk_level: "HIGH",
    action: { type: "index_drop", params: { name: "orders_pkey" } },
    rationale: "Dropping a primary key index is irreversible without a full table rebuild.",
    created_at: new Date(Date.now() - 35 * 60000).toISOString(),
    judgment: { decision: "reject", judge_kind: "human", rationale: "Primary key required for referential integrity." },
  },
  {
    id: 3,
    pore: "blast_radius",
    risk_level: "MEDIUM",
    action: { type: "guc", params: { name: "max_connections", value: "500" } },
    rationale: "max_connections requires a service restart — cannot be rolled back mid-run.",
    created_at: new Date(Date.now() - 70 * 60000).toISOString(),
    judgment: { decision: "approve", judge_kind: "human", rationale: "Acceptable during low-traffic window." },
  },
];
