"""Tenant-scoped PostgreSQL outbox leasing; delivery is at least once."""

import uuid

import psycopg

from .contracts import PlatformError
from .runtime import Principal


class Outbox:
    def __init__(self, dsn):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("missing_outbox_dsn")
        self._dsn = dsn

    @staticmethod
    def _authorize(principal):
        if (not isinstance(principal, Principal) or not principal.actor or not principal.tenant
                or "platform:outbox-dispatch" not in principal.permissions):
            raise PlatformError("permission_denied")

    def claim(self, principal, limit=20, lease_seconds=60):
        self._authorize(principal)
        if type(limit) is not int or not 1 <= limit <= 100 or type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise PlatformError("invalid_lease_settings")
        lease = uuid.uuid4()
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SELECT set_config('ade.tenant_id', %s, true)", (principal.tenant,))
                cursor.execute("""
                    WITH selected AS (
                        SELECT event_id FROM ade_core.outbox
                        WHERE tenant_id = %s AND delivered_at IS NULL
                          AND next_attempt_at <= now()
                          AND (lease_until IS NULL OR lease_until <= now())
                        ORDER BY created_at, event_id
                        FOR UPDATE SKIP LOCKED LIMIT %s
                    )
                    UPDATE ade_core.outbox AS event
                    SET lease_id = %s, lease_until = now() + make_interval(secs => %s),
                        attempts = event.attempts + 1
                    FROM selected
                    WHERE event.tenant_id = %s AND event.event_id = selected.event_id
                    RETURNING event.event_id, event.record_id, event.event_type, event.attempts
                """, (principal.tenant, limit, lease, lease_seconds, principal.tenant))
                rows = cursor.fetchall()
        return [{"event_id": row[0], "record_id": row[1], "event_type": row[2],
                 "attempt": row[3], "lease_id": lease} for row in rows]

    def complete(self, principal, event_id, lease_id):
        self._finish(principal, event_id, lease_id, None)

    def retry(self, principal, event_id, lease_id, delay_seconds):
        if type(delay_seconds) is not int or not 0 <= delay_seconds <= 86400:
            raise PlatformError("invalid_retry_delay")
        self._finish(principal, event_id, lease_id, delay_seconds)

    def _finish(self, principal, event_id, lease_id, delay):
        self._authorize(principal)
        if not isinstance(event_id, uuid.UUID) or not isinstance(lease_id, uuid.UUID):
            raise PlatformError("invalid_lease")
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SELECT set_config('ade.tenant_id', %s, true)", (principal.tenant,))
                if delay is None:
                    cursor.execute("""
                        UPDATE ade_core.outbox SET delivered_at = now(), lease_id = NULL, lease_until = NULL
                        WHERE tenant_id = %s AND event_id = %s AND lease_id = %s
                          AND delivered_at IS NULL AND lease_until > now()
                    """, (principal.tenant, event_id, lease_id))
                else:
                    cursor.execute("""
                        UPDATE ade_core.outbox SET lease_id = NULL, lease_until = NULL,
                            next_attempt_at = now() + make_interval(secs => %s)
                        WHERE tenant_id = %s AND event_id = %s AND lease_id = %s
                          AND delivered_at IS NULL AND lease_until > now()
                    """, (delay, principal.tenant, event_id, lease_id))
                if cursor.rowcount != 1:
                    raise PlatformError("outbox_lease_invalid")
