"""Minimal record and outbox transaction boundary for synthetic integration tests.

The tenant is taken from a verified Principal, never from a request body. Use
only a non-owner, non-superuser database role without BYPASSRLS. The caller
must not expose database connections or arbitrary SQL to untrusted users: custom
PostgreSQL settings are not cryptographic credentials.
"""

import uuid

import psycopg
from psycopg.types.json import Jsonb

from .contracts import PlatformError
from .runtime import Principal


class TenantRecordStore:
    def __init__(self, dsn):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("missing_store_dsn")
        self._dsn = dsn

    @staticmethod
    def _check(principal, permission):
        if not isinstance(principal, Principal) or not principal.actor or not principal.tenant or permission not in principal.permissions:
            raise PlatformError("permission_denied")

    def create(self, principal, body):
        self._check(principal, "platform:records-write")
        if not isinstance(body, dict):
            raise PlatformError("invalid_record")
        record_id, event_id = uuid.uuid4(), uuid.uuid4()
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SELECT set_config('ade.tenant_id', %s, true)", (principal.tenant,))
                cursor.execute("INSERT INTO ade_core.records (tenant_id, record_id, body) VALUES (%s, %s, %s)",
                               (principal.tenant, record_id, Jsonb(body)))
                cursor.execute("INSERT INTO ade_core.outbox (tenant_id, event_id, record_id, event_type) VALUES (%s, %s, %s, %s)",
                               (principal.tenant, event_id, record_id, "record.created.v1"))
        return record_id

    def get(self, principal, record_id):
        self._check(principal, "platform:records-read")
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("SELECT set_config('ade.tenant_id', %s, true)", (principal.tenant,))
                cursor.execute("SELECT body FROM ade_core.records WHERE record_id = %s", (record_id,))
                row = cursor.fetchone()
                return None if row is None else row[0]
