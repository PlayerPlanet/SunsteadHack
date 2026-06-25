-- Idempotent (re-)grant of brokered-role privileges on the control tables.
--
-- WHY THIS EXISTS: recreating a table — or `DROP SCHEMA public CASCADE; CREATE SCHEMA
-- public` — drops every GRANT on the affected objects. When that happens (e.g. another
-- process rebuilds the schema to load data), the brokered roles silently lose access,
-- and because the serving process now `SET ROLE`s per request (the truth boundary), the
-- control plane starts failing reads with `relation "experiment" does not exist` /
-- permission denied even though it worked before. Re-running this restores the grants.
--
-- APPROVAL-GATED, MANUAL. Run as a privileged role (avnadmin) against sunstead_control:
--     psql "$ADMIN_DSN" -f sql/grant_control_roles.sql
-- Safe to re-run. It does NOT create roles or set passwords (see sql/roles.sql for that).

\set ON_ERROR_STOP on

-- Schema visibility for all three brokered roles (the missing piece after a schema rebuild).
GRANT USAGE ON SCHEMA public TO sunstead_readonly, sunstead_operator, sunstead_proposer;

-- readonly: SELECT the governance log + curves. operator/proposer inherit this via
-- their role membership (GRANT sunstead_readonly TO ... in roles.sql).
GRANT SELECT ON experiment, crossing, judgment, run TO sunstead_readonly;

-- operator: write judgments (adjudicate) and runs (dispatch/cancel).
GRANT INSERT, UPDATE ON judgment, run TO sunstead_operator;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sunstead_operator;

-- proposer: append experiments + crossings; deliberately NO held-out / judge tables.
GRANT INSERT ON experiment, crossing TO sunstead_proposer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sunstead_proposer;

-- Survive the NEXT rebuild: future tables/sequences created by the owner inherit these,
-- so a schema reload no longer silently breaks the brokered roles. Adjust the FOR ROLE
-- to whoever creates the tables (the table owner; avnadmin on this Aiven service).
ALTER DEFAULT PRIVILEGES FOR ROLE avnadmin IN SCHEMA public
  GRANT SELECT ON TABLES TO sunstead_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE avnadmin IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO sunstead_operator, sunstead_proposer;

-- Verify (prints t/t if reads are restored for the readonly role):
SELECT has_schema_privilege('sunstead_readonly','public','USAGE')   AS readonly_schema_usage,
       has_table_privilege('sunstead_readonly','experiment','SELECT') AS readonly_can_select;
