-- Apply with a controlled migration role, not with an application connection.
-- This schema stores identity routing metadata, not employee records.
BEGIN;
CREATE SCHEMA ade_identity;

CREATE TABLE ade_identity.tenants (
    tenant_id text PRIMARY KEY CHECK (length(tenant_id) BETWEEN 1 AND 128),
    host text NOT NULL UNIQUE CHECK (host = lower(host) AND length(host) BETWEEN 3 AND 253),
    organization_id text NOT NULL UNIQUE CHECK (length(organization_id) BETWEEN 1 AND 256),
    status text NOT NULL CHECK (status IN ('active', 'suspended'))
);

CREATE TABLE ade_identity.memberships (
    tenant_id text NOT NULL REFERENCES ade_identity.tenants(tenant_id),
    subject text NOT NULL CHECK (length(subject) BETWEEN 1 AND 256),
    status text NOT NULL CHECK (status IN ('active', 'suspended')),
    PRIMARY KEY (tenant_id, subject)
);

CREATE TABLE ade_identity.grants (
    tenant_id text NOT NULL,
    subject text NOT NULL,
    permission text NOT NULL CHECK (length(permission) BETWEEN 3 AND 256),
    PRIMARY KEY (tenant_id, subject, permission),
    FOREIGN KEY (tenant_id, subject) REFERENCES ade_identity.memberships(tenant_id, subject) ON DELETE CASCADE
);
COMMIT;
