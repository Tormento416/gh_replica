BEGIN;
ALTER TABLE ade_core.outbox
    ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    ADD COLUMN lease_id uuid,
    ADD COLUMN lease_until timestamptz,
    ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN delivered_at timestamptz,
    ADD CONSTRAINT ade_lease_pair CHECK ((lease_id IS NULL) = (lease_until IS NULL));
CREATE INDEX ade_outbox_pending ON ade_core.outbox (tenant_id, next_attempt_at, created_at, event_id)
    WHERE delivered_at IS NULL;
COMMIT;
