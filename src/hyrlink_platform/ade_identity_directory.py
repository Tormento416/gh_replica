"""Thread-safe PostgreSQL identity directory: fresh connection per lookup.

The configured database role must have SELECT only on the identity-directory
tables. This adapter does not administer tenants, grant roles, or expose SQL to
clients. Never use a superuser or migration credential in an application.
"""

import psycopg

from .identity import TenantBinding


class IdentityDirectory:
    def __init__(self, dsn):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("missing_directory_dsn")
        self._dsn = dsn

    def tenant_for_host(self, host):
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute(
                    "SELECT host, tenant_id, organization_id, status FROM ade_identity.tenants WHERE host = %s",
                    (host,),
                )
                row = cursor.fetchone()
                return None if row is None else TenantBinding(row[0], row[1], row[2], row[3] == "active")

    def grants_for_subject(self, subject, tenant):
        with psycopg.connect(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '3s'")
                cursor.execute("""
                    SELECT g.permission
                    FROM ade_identity.tenants t
                    JOIN ade_identity.memberships m ON m.tenant_id = t.tenant_id
                    LEFT JOIN ade_identity.grants g ON g.tenant_id = m.tenant_id AND g.subject = m.subject
                    WHERE t.tenant_id = %s AND m.subject = %s
                      AND t.status = 'active' AND m.status = 'active'
                """, (tenant, subject))
                rows = cursor.fetchall()
                if not rows:
                    return None
                return frozenset(row[0] for row in rows if row[0] is not None)
