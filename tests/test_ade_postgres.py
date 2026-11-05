"""Integration tests: run only against an explicitly disposable database."""

import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo

from hyrlink_platform.ade_identity_directory import IdentityDirectory
from hyrlink_platform.ade_transaction_store import TenantRecordStore
from hyrlink_platform.contracts import PlatformError
from hyrlink_platform.runtime import Principal

DSN = os.getenv("ADE_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(DSN, "requires ADE_TEST_DATABASE_URL for a disposable PostgreSQL database")
class PostgreSQLBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The test user must provide a new, disposable database/cluster. Refuse
        # to run over existing schemas or a pre-existing role.
        with psycopg.connect(DSN, autocommit=True) as connection:
            row = connection.execute("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN ('ade_identity', 'ade_core')) OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname='ade_test_runtime')").fetchone()
            if row[0]:
                raise RuntimeError("integration tests require a fresh disposable database and role")
            connection.execute((ROOT / "migrations/ade_001_identity_directory.sql").read_text(), prepare=False)
            connection.execute((ROOT / "migrations/ade_002_transaction_boundary.sql").read_text(), prepare=False)
            connection.execute("CREATE ROLE ade_test_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS")
            connection.execute("GRANT USAGE ON SCHEMA ade_identity, ade_core TO ade_test_runtime")
            connection.execute("GRANT SELECT ON ALL TABLES IN SCHEMA ade_identity TO ade_test_runtime")
            connection.execute("GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA ade_core TO ade_test_runtime")
            connection.execute("INSERT INTO ade_identity.tenants VALUES ('acme', 'acme.example.com', 'org-acme', 'active'), ('globex', 'globex.example.com', 'org-globex', 'active'), ('paused', 'paused.example.com', 'org-paused', 'suspended')")
            connection.execute("INSERT INTO ade_identity.memberships VALUES ('acme', 'user-1', 'active'), ('globex', 'user-1', 'active'), ('acme', 'blocked', 'suspended'), ('acme', 'empty', 'active')")
            connection.execute("INSERT INTO ade_identity.grants VALUES ('acme', 'user-1', 'client-crm:read'), ('globex', 'user-1', 'recruiting:read'), ('acme', 'blocked', 'client-crm:read')")
        cls.runtime_dsn = make_conninfo(DSN, options="-c role=ade_test_runtime")
        cls.directory = IdentityDirectory(cls.runtime_dsn)
        cls.store = TenantRecordStore(cls.runtime_dsn)
        cls.acme = Principal("user-1", "acme", frozenset({"platform:records-read", "platform:records-write"}))
        cls.globex = Principal("user-1", "globex", cls.acme.permissions)

    def test_directory_binds_host_and_org(self):
        tenant = self.directory.tenant_for_host("acme.example.com")
        self.assertEqual((tenant.tenant, tenant.organization, tenant.active), ("acme", "org-acme", True))
        self.assertFalse(self.directory.tenant_for_host("paused.example.com").active)
        self.assertIsNone(self.directory.tenant_for_host("missing.example.com"))

    def test_grants_are_scoped_to_active_membership(self):
        self.assertEqual(self.directory.grants_for_subject("user-1", "acme"), frozenset({"client-crm:read"}))
        self.assertEqual(self.directory.grants_for_subject("user-1", "globex"), frozenset({"recruiting:read"}))
        self.assertEqual(self.directory.grants_for_subject("empty", "acme"), frozenset())
        self.assertIsNone(self.directory.grants_for_subject("blocked", "acme"))
        self.assertIsNone(self.directory.grants_for_subject("user-1", "paused"))
        self.assertIsNone(self.directory.grants_for_subject("' OR TRUE --", "acme"))

    def test_revoked_grant_is_visible_without_cache(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM ade_identity.grants WHERE tenant_id='acme' AND subject='user-1' AND permission='client-crm:read'")
        try:
            self.assertEqual(self.directory.grants_for_subject("user-1", "acme"), frozenset())
        finally:
            with psycopg.connect(DSN) as connection:
                connection.execute("INSERT INTO ade_identity.grants VALUES ('acme', 'user-1', 'client-crm:read')")

    def test_record_and_outbox_are_tenant_scoped(self):
        record = self.store.create(self.acme, {"example": "synthetic"})
        self.assertEqual(self.store.get(self.acme, record), {"example": "synthetic"})
        self.assertIsNone(self.store.get(self.globex, record))
        with psycopg.connect(self.runtime_dsn) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM ade_core.records").fetchone()[0], 0)
            connection.execute("SELECT set_config('ade.tenant_id', %s, true)", ("globex",))
            self.assertEqual(connection.execute("SELECT count(*) FROM ade_core.outbox WHERE record_id=%s", (record,)).fetchone()[0], 0)
            connection.execute("SELECT set_config('ade.tenant_id', %s, true)", ("acme",))
            self.assertEqual(connection.execute("SELECT count(*) FROM ade_core.outbox WHERE record_id=%s", (record,)).fetchone()[0], 1)

    def test_rls_rejects_cross_tenant_insert(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with psycopg.connect(self.runtime_dsn) as connection:
                connection.execute("SELECT set_config('ade.tenant_id', %s, true)", ("acme",))
                connection.execute("INSERT INTO ade_core.records VALUES (%s, %s, '{}'::jsonb)", ("globex", uuid.uuid4()))

    def test_missing_permission_prevents_write(self):
        with self.assertRaisesRegex(PlatformError, "permission_denied"):
            self.store.create(Principal("user-1", "acme", frozenset()), {"example": "synthetic"})

    def test_outbox_failure_rolls_back_record(self):
        with psycopg.connect(DSN, autocommit=True) as connection:
            before = connection.execute("SELECT count(*) FROM ade_core.records WHERE tenant_id='acme'").fetchone()[0]
            connection.execute("REVOKE INSERT ON ade_core.outbox FROM ade_test_runtime")
            try:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    self.store.create(self.acme, {"example": "rollback"})
                after = connection.execute("SELECT count(*) FROM ade_core.records WHERE tenant_id='acme'").fetchone()[0]
                self.assertEqual(before, after)
            finally:
                connection.execute("GRANT INSERT ON ade_core.outbox TO ade_test_runtime")


if __name__ == "__main__":
    unittest.main()
