create table experiment (
  id bigserial primary key,
  task_id text not null,
  model text not null,
  drift_level double precision default 0,
  candidate jsonb not null,              -- {type, params, reversible}
  baseline_p99 double precision, candidate_p99 double precision,
  cost_estimate double precision,
  correctness_ok boolean, within_noise boolean,
  decision text not null,                -- 'keep'|'discard'|'rollback'|'escalated'
  created_at timestamptz default now()
);
create table crossing (
  id bigserial primary key, experiment_id bigint references experiment(id),
  pore text not null, risk_level text not null,
  requires_human_judgment boolean not null, action jsonb not null,
  created_at timestamptz default now()
);
create table judgment (
  id bigserial primary key, crossing_id bigint references crossing(id),
  judge text not null, judge_kind text not null,   -- rule|human|agent
  decision text not null, rationale text,           -- approve|reject|escalate
  created_at timestamptz default now()
);
create table run (
  run_id text primary key,
  task_id text not null,
  model text not null,
  state text not null,
  iterations_done integer not null default 0,
  best_p99 double precision,
  started_at timestamptz,
  ended_at timestamptz,
  error_msg text,
  iterations_target integer not null default 0
);
-- A worker polls for queued runs; this partial index keeps the claim query cheap.
create index if not exists run_queued_idx on run (run_id) where state = 'queued';
