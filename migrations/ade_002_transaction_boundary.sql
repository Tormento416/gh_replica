-- Demonstration of transaction-scoped tenant isolation and atomic outbox writes.
-- Apply as a migration owner; application roles must not own tables or BYPASSRLS.
BEGIN;
CREATE SCHEMA ade_core;
CREATE TABLE ade_core.records (
    tenant_id text NOT NULL REFERENCES ade_identity.tenants(tenant_id),
    record_id uuid NOT NULL,
    body jsonb NOT NULL,
    PRIMARY KEY (tenant_id, record_id)
);
CREATE TABLE ade_core.outbox (
    tenant_id text NOT NULL REFERENCES ade_identity.tenants(tenant_id),
    event_id uuid NOT NULL,
    record_id uuid NOT NULL,
    event_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, record_id) REFERENCES ade_core.records(tenant_id, record_id)
);
ALTER TABLE ade_core.records ENABLE ROW LEVEL SECURITY;
ALTER TABLE ade_core.records FORCE ROW LEVEL SECURITY;
ALTER TABLE ade_core.outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE ade_core.outbox FORCE ROW LEVEL SECURITY;
CREATE POLICY ade_record_tenant ON ade_core.records
    USING (tenant_id = current_setting('ade.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('ade.tenant_id', true));
CREATE POLICY ade_outbox_tenant ON ade_core.outbox
    USING (tenant_id = current_setting('ade.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('ade.tenant_id', true));
COMMIT;
