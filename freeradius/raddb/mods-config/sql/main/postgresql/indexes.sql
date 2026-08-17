-- NetGrid hardening indexes. The official schema.sql above is left untouched;
-- these are additive. Requires the rad* tables to exist (runs after 10-radius-schema.sql).
CREATE UNIQUE INDEX IF NOT EXISTS uq_radcheck_username_attribute ON radcheck (username, attribute);
CREATE INDEX IF NOT EXISTS ix_radacct_username ON radacct (username);
CREATE INDEX IF NOT EXISTS ix_radacct_acctstoptime ON radacct (acctstoptime);
CREATE INDEX IF NOT EXISTS ix_radacct_framedipaddress ON radacct (framedipaddress);
