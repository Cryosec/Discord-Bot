-- Join-A-Clan dedup by server (cogs/jac.py): the server id of each posted invite.
-- Additive and nullable: the web UI and rows written before this keep working.
-- Idempotent. Run once on the bot database, before or after the bot deploy:
--   mariadb -h <host> -u <user> -p <database> < migrations/2026-10-29_jac_guild_id.sql
-- Rollback: ALTER TABLE jac DROP COLUMN IF EXISTS guild_id;
ALTER TABLE jac ADD COLUMN IF NOT EXISTS guild_id VARCHAR(20) NULL;
