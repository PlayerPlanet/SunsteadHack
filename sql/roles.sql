-- Postgres roles for the deployment-grade control plane (the truth boundary).
--
-- APPROVAL-GATED, MANUAL migration. This is NOT run by the server and MUST NOT be
-- auto-applied against the shared Aiven `sunstead-pg-bench` service. An admin runs it
-- once, connected as a superuser (avnadmin), against the target database:
--
--     psql "$CLEANROOM_PG_DSN" -v app_password="$APP_PWD" -f sql/roles.sql
--
-- Rationale: the serving process logs in as `sunstead_app` (NOSUPERUSER, LOGIN) and
-- per request `SET ROLE`s into one of the brokered roles below (see
-- cleanroom/control/server/roles.py). A superuser would bypass every GRANT here, so
-- the server refuses to boot as superuser (assert_not_superuser).
--
-- Idempotent-ish: guarded CREATE ROLEs; re-running is safe.

\set ON_ERROR_STOP on

-- ---- the login role the server authenticates as -----------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sunstead_app') THEN
    EXECUTE format('CREATE ROLE sunstead_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_password');
  END IF;
END$$;

-- ---- the three brokered (non-login) roles the app SET ROLEs into ------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sunstead_readonly') THEN
    CREATE ROLE sunstead_readonly NOLOGIN NOSUPERUSER;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sunstead_operator') THEN
    CREATE ROLE sunstead_operator NOLOGIN NOSUPERUSER;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sunstead_proposer') THEN
    CREATE ROLE sunstead_proposer NOLOGIN NOSUPERUSER;
  END IF;
END$$;

-- The login role may assume any brokered role (this is what makes SET ROLE work).
GRANT sunstead_readonly, sunstead_operator, sunstead_proposer TO sunstead_app;

-- ---- least privilege on the governance log ----------------------------------
-- Nobody gets table privileges by default; we grant explicitly per role.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;

-- readonly: SELECT the log + curves, nothing else.
GRANT USAGE ON SCHEMA public TO sunstead_readonly;
GRANT SELECT ON experiment, crossing, judgment, run TO sunstead_readonly;

-- operator: read everything readonly can, plus write judgments (adjudicate) and runs.
GRANT sunstead_readonly TO sunstead_operator;
GRANT INSERT, UPDATE ON judgment, run TO sunstead_operator;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sunstead_operator;

-- proposer: the optimizer's own role — append experiments + crossings, read the log.
-- It deliberately gets NO access to any held-out / judge / ground-truth tables.
GRANT sunstead_readonly TO sunstead_proposer;
GRANT INSERT ON experiment, crossing TO sunstead_proposer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sunstead_proposer;

-- ---- survive schema rebuilds ------------------------------------------------
-- Recreating a table/schema DROPs its grants, which silently breaks the brokered
-- roles (the server SET ROLEs per request, so it then fails reads with `relation
-- does not exist`). Default privileges re-grant automatically for objects the owner
-- creates later. (For an existing-but-rebuilt schema, re-apply the explicit grants
-- above — see sql/grant_control_roles.sql, an idempotent re-grant that needs no password.)
ALTER DEFAULT PRIVILEGES FOR ROLE avnadmin IN SCHEMA public
  GRANT SELECT ON TABLES TO sunstead_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE avnadmin IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sunstead_operator, sunstead_proposer;

-- ---- truth boundary (effective once held-out tables exist) ------------------
-- When the bio/quant benchmarks add held-out label tables (e.g. held_out_labels),
-- they must be created here and walled off from the proposer. Template:
--
--   REVOKE ALL ON held_out_labels FROM PUBLIC, sunstead_proposer, sunstead_readonly;
--   GRANT SELECT ON held_out_labels TO sunstead_operator;  -- scorer only
--
-- Demo proof the boundary holds:
--   SET ROLE sunstead_proposer; SELECT * FROM held_out_labels;  -- => permission denied
