-- Runs once, on the first start of the local db container (docker-compose.yml).
-- Mirrors the role script in docs/runbooks/RAILWAY_DEPLOY.md.
--
-- Two roles, on purpose (playbook 14):
--   cw_migrator owns the tables and runs migrations.
--   cw_app runs the application. It is not a superuser, owns nothing and cannot
--   BYPASSRLS, which is what makes row-level security mean something. The app
--   refuses to boot on any other kind of role (playbook 11.1).
-- Passwords are dev-only literals, allowlisted in .gitleaks.toml.
CREATE ROLE cw_migrator LOGIN PASSWORD 'cw-migrator-dev-only' NOSUPERUSER NOBYPASSRLS CREATEDB;
CREATE ROLE cw_app      LOGIN PASSWORD 'cw-app-dev-only'      NOSUPERUSER NOBYPASSRLS;
-- CREATEDB on cw_migrator lets the test runner and migrate_from_zero create and drop
-- throwaway databases locally and in CI. Production grants it nothing of the kind.
GRANT ALL ON DATABASE compliance_watch TO cw_migrator;
\connect compliance_watch
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- The public schema belongs to the migrator so that Django's migrations, run as
-- cw_migrator, own every table. cw_app is granted table privileges by the first
-- migration (and default privileges for later tables), never ownership.
ALTER SCHEMA public OWNER TO cw_migrator;
GRANT USAGE ON SCHEMA public TO cw_app;
-- Extensions must also exist in the throwaway databases the test runner creates.
-- template1 is what CREATE DATABASE copies, so install them there too.
\connect template1
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
