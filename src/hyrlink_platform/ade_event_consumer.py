"""Synthetic record-created projection demonstrating atomic deduplication.

Accept events only from a separately authenticated, authorized transport.
The inbox and local database effect share one transaction; external side
effects need their own idempotency and must not run inside this transaction.
"""

import re
import uuid

import psycopg

from .contracts import PlatformError
from .runtime import Principal

_CONSUMER = re.compile(r"[a-z][a-z0-9-]{1,127}\Z")


class RecordCreatedConsumer:
    def __init__(self, dsn, consumer_id):
        if not isinstance(dsn, str) or not dsn.strip() or not isinstance(consumer_id, str) or not _CONSUMER.fullmatch(consumer_id):
            raise ValueError("invalid_consumer_configuration")
        self._dsn, self.consumer_id = dsn, consumer_id

    def apply(self, principal, event_id, record_id):
        if (not isinstance(principal, Principal) or not principal.actor or not principal.tenant
                or "platform:events-consume" not in principal.permissions):
            raise PlatformError("permission_denied")
        if not isinstance(event_id, uuid.UUID) or not isinstance(record_id, uuid.UUID):
            raise PlatformError("invalid_event")
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SELECT set_config('ade.tenant_id', %s, true)", (principal.tenant,))
                cursor.execute("""
                    INSERT INTO ade_core.consumer_inbox (tenant_id, consumer_id, event_id, record_id)
                    VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING event_id
                """, (principal.tenant, self.consumer_id, event_id, record_id))
                if cursor.fetchone() is None:
                    cursor.execute("""
                        SELECT record_id FROM ade_core.consumer_inbox
                        WHERE tenant_id = %s AND consumer_id = %s AND event_id = %s
                    """, (principal.tenant, self.consumer_id, event_id))
                    existing = cursor.fetchone()
                    if existing is None or existing[0] != record_id:
                        raise PlatformError("event_identity_conflict")
                    return False
                cursor.execute("""
                    INSERT INTO ade_core.consumer_projection (tenant_id, consumer_id, total)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (tenant_id, consumer_id)
                    DO UPDATE SET total = ade_core.consumer_projection.total + 1
                """, (principal.tenant, self.consumer_id))
        return True

    def count(self, principal):
        if (not isinstance(principal, Principal) or not principal.actor or not principal.tenant
                or "platform:events-consume" not in principal.permissions):
            raise PlatformError("permission_denied")
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SELECT set_config('ade.tenant_id', %s, true)", (principal.tenant,))
                cursor.execute("SELECT total FROM ade_core.consumer_projection WHERE tenant_id = %s AND consumer_id = %s",
                               (principal.tenant, self.consumer_id))
                row = cursor.fetchone()
                return 0 if row is None else row[0]
