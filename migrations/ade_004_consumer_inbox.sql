BEGIN;
CREATE TABLE ade_core.consumer_inbox (
    tenant_id text NOT NULL REFERENCES ade_identity.tenants(tenant_id),
    consumer_id text NOT NULL CHECK (length(consumer_id) BETWEEN 1 AND 128),
    event_id uuid NOT NULL,
    record_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, consumer_id, event_id)
);
CREATE TABLE ade_core.consumer_projection (
    tenant_id text NOT NULL REFERENCES ade_identity.tenants(tenant_id),
    consumer_id text NOT NULL CHECK (length(consumer_id) BETWEEN 1 AND 128),
    total bigint NOT NULL DEFAULT 0 CHECK (total >= 0),
    PRIMARY KEY (tenant_id, consumer_id)
);
ALTER TABLE ade_core.consumer_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE ade_core.consumer_inbox FORCE ROW LEVEL SECURITY;
ALTER TABLE ade_core.consumer_projection ENABLE ROW LEVEL SECURITY;
ALTER TABLE ade_core.consumer_projection FORCE ROW LEVEL SECURITY;
CREATE POLICY ade_inbox_tenant ON ade_core.consumer_inbox
    USING (tenant_id = current_setting('ade.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('ade.tenant_id', true));
CREATE POLICY ade_projection_tenant ON ade_core.consumer_projection
    USING (tenant_id = current_setting('ade.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('ade.tenant_id', true));
COMMIT;
