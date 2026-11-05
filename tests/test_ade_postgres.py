"""Integration tests: run only against an explicitly disposable database."""

import os
import asyncio
import json
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from psycopg.conninfo import make_conninfo

from hyrlink_platform.ade_identity_directory import IdentityDirectory
from hyrlink_platform.ade_transaction_store import TenantRecordStore
from hyrlink_platform.ade_outbox import Outbox
from hyrlink_platform.ade_event_consumer import RecordCreatedConsumer
from hyrlink_platform.ade_storage_contracts import OutboxStore, RecordStore, TenantDirectory
from hyrlink_platform.ade_identity_middleware import IdentityMiddleware
from hyrlink_platform.ade_workos_boundary import WorkOSSessionBoundary
from hyrlink_platform.ade_workos_keys import SessionKeyStore
from hyrlink_platform.identity import IdentityPolicy
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
            connection.execute((ROOT / "migrations/ade_003_outbox_leases.sql").read_text(), prepare=False)
            connection.execute((ROOT / "migrations/ade_004_consumer_inbox.sql").read_text(), prepare=False)
            connection.execute("CREATE ROLE ade_test_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS")
            connection.execute("GRANT USAGE ON SCHEMA ade_identity, ade_core TO ade_test_runtime")
            connection.execute("GRANT SELECT ON ALL TABLES IN SCHEMA ade_identity TO ade_test_runtime")
            connection.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ade_core TO ade_test_runtime")
            connection.execute("INSERT INTO ade_identity.tenants VALUES ('acme', 'acme.example.com', 'org-acme', 'active'), ('globex', 'globex.example.com', 'org-globex', 'active'), ('paused', 'paused.example.com', 'org-paused', 'suspended')")
            connection.execute("INSERT INTO ade_identity.memberships VALUES ('acme', 'user-1', 'active'), ('globex', 'user-1', 'active'), ('acme', 'blocked', 'suspended'), ('acme', 'empty', 'active')")
            connection.execute("INSERT INTO ade_identity.grants VALUES ('acme', 'user-1', 'client-crm:read'), ('globex', 'user-1', 'recruiting:read'), ('acme', 'blocked', 'client-crm:read')")
        cls.runtime_dsn = make_conninfo(DSN, options="-c role=ade_test_runtime")
        cls.directory = IdentityDirectory(cls.runtime_dsn)
        cls.store = TenantRecordStore(cls.runtime_dsn)
        cls.outbox = Outbox(cls.runtime_dsn)
        cls.worker = Principal("worker", "acme", frozenset({"platform:outbox-dispatch"}))
        cls.acme = Principal("user-1", "acme", frozenset({"platform:records-read", "platform:records-write"}))
        cls.globex = Principal("user-1", "globex", cls.acme.permissions)

    def test_directory_binds_host_and_org(self):
        tenant = self.directory.tenant_for_host("acme.example.com")
        self.assertEqual((tenant.tenant, tenant.organization, tenant.active), ("acme", "org-acme", True))
        self.assertFalse(self.directory.tenant_for_host("paused.example.com").active)
        self.assertIsNone(self.directory.tenant_for_host("missing.example.com"))

    def test_postgresql_adapters_satisfy_storage_interfaces(self):
        self.assertIsInstance(self.directory, TenantDirectory)
        self.assertIsInstance(self.store, RecordStore)
        self.assertIsInstance(self.outbox, OutboxStore)

    def test_signed_http_request_uses_fresh_database_grants(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
        key_store = SessionKeyStore("client_0123456789ABCDEF", fetch=lambda _: json.dumps({"keys": [jwk]}).encode())
        boundary = WorkOSSessionBoundary.from_directory(
            IdentityPolicy("https://issuer.example", "hris-api"), key_store, self.directory)
        import time
        now = int(time.time())
        token = jwt.encode({"iss": "https://issuer.example", "aud": "hris-api", "sub": "user-1",
                            "org_id": "org-acme", "token_use": "access", "iat": now, "nbf": now,
                            "exp": now + 300, "permissions": ["platform:approve"]}, key,
                           algorithm="RS256", headers={"kid": "test-key"})
        observed = []
        async def app(scope, receive, send):
            observed.append(scope["ade.principal"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        middleware = IdentityMiddleware(app, boundary)
        async def request(host):
            responses = []
            async def receive(): return {"type": "http.request", "body": b""}
            async def send(message): responses.append(message)
            await middleware({"type": "http", "headers": [(b"host", host),
                             (b"authorization", ("Bearer " + token).encode())]}, receive, send)
            return responses[0]["status"]
        self.assertEqual(asyncio.run(request(b"acme.example.com")), 200)
        self.assertEqual(observed[0].permissions, frozenset({"client-crm:read"}))
        self.assertEqual(asyncio.run(request(b"globex.example.com")), 401)
        with psycopg.connect(DSN) as connection:
            connection.execute("UPDATE ade_identity.memberships SET status='suspended' WHERE tenant_id='acme' AND subject='user-1'")
        try:
            self.assertEqual(asyncio.run(request(b"acme.example.com")), 401)
        finally:
            with psycopg.connect(DSN) as connection:
                connection.execute("UPDATE ade_identity.memberships SET status='active' WHERE tenant_id='acme' AND subject='user-1'")

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

    def test_workers_claim_disjoint_events_and_cannot_cross_tenants(self):
        for i in range(8):
            self.store.create(self.acme, {"synthetic": i})
        self.store.create(self.globex, {"synthetic": "other"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            groups = list(pool.map(lambda _: self.outbox.claim(self.worker, limit=4), range(2)))
        all_events = groups[0] + groups[1]
        self.assertEqual(len(all_events), 8)
        self.assertEqual(len({event["event_id"] for event in all_events}), 8)
        other = Principal("worker", "globex", self.worker.permissions)
        with self.assertRaisesRegex(PlatformError, "outbox_lease_invalid"):
            self.outbox.complete(other, all_events[0]["event_id"], all_events[0]["lease_id"])
        for event in all_events:
            self.outbox.complete(self.worker, event["event_id"], event["lease_id"])

    def test_retry_releases_lease_and_rejects_stale_ack(self):
        self.store.create(self.acme, {"synthetic": "retry"})
        event = self.outbox.claim(self.worker, limit=1)[0]
        self.outbox.retry(self.worker, event["event_id"], event["lease_id"], 0)
        with self.assertRaisesRegex(PlatformError, "outbox_lease_invalid"):
            self.outbox.complete(self.worker, event["event_id"], event["lease_id"])
        reclaimed = self.outbox.claim(self.worker, limit=1)[0]
        self.assertEqual(reclaimed["event_id"], event["event_id"])
        self.assertEqual(reclaimed["attempt"], 2)
        self.outbox.complete(self.worker, reclaimed["event_id"], reclaimed["lease_id"])

    def test_expired_lease_cannot_be_acknowledged(self):
        self.store.create(self.acme, {"synthetic": "expired"})
        event = self.outbox.claim(self.worker, limit=1)[0]
        with psycopg.connect(DSN) as connection:
            connection.execute("UPDATE ade_core.outbox SET lease_until=now() - interval '1 second' WHERE event_id=%s", (event["event_id"],))
        with self.assertRaisesRegex(PlatformError, "outbox_lease_invalid"):
            self.outbox.complete(self.worker, event["event_id"], event["lease_id"])
        reclaimed = self.outbox.claim(self.worker, limit=1)[0]
        self.assertEqual(reclaimed["event_id"], event["event_id"])
        self.outbox.complete(self.worker, reclaimed["event_id"], reclaimed["lease_id"])

    def test_dispatch_permission_required(self):
        with self.assertRaisesRegex(PlatformError, "permission_denied"):
            self.outbox.claim(Principal("user", "acme", frozenset()))

    def test_consumer_deduplicates_concurrent_retries_and_isolates_tenants(self):
        consumer = RecordCreatedConsumer(self.runtime_dsn, "counts")
        worker = Principal("worker", "acme", frozenset({"platform:events-consume"}))
        other = Principal("worker", "globex", worker.permissions)
        event, record = uuid.uuid4(), uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: consumer.apply(worker, event, record), range(2)))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(consumer.count(worker), 1)
        self.assertEqual(consumer.count(other), 0)
        self.assertTrue(consumer.apply(other, event, record))
        self.assertEqual(consumer.count(other), 1)
        with self.assertRaisesRegex(PlatformError, "event_identity_conflict"):
            consumer.apply(worker, event, uuid.uuid4())

    def test_failed_projection_rolls_back_inbox_for_retry(self):
        consumer = RecordCreatedConsumer(self.runtime_dsn, "rollback-check")
        worker = Principal("worker", "acme", frozenset({"platform:events-consume"}))
        event, record = uuid.uuid4(), uuid.uuid4()
        with psycopg.connect(DSN, autocommit=True) as connection:
            connection.execute("REVOKE INSERT, UPDATE ON ade_core.consumer_projection FROM ade_test_runtime")
            try:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    consumer.apply(worker, event, record)
            finally:
                connection.execute("GRANT INSERT, UPDATE ON ade_core.consumer_projection TO ade_test_runtime")
        self.assertTrue(consumer.apply(worker, event, record))
        self.assertFalse(consumer.apply(worker, event, record))
        self.assertEqual(consumer.count(worker), 1)

    def test_consumer_requires_permission(self):
        consumer = RecordCreatedConsumer(self.runtime_dsn, "counts")
        with self.assertRaisesRegex(PlatformError, "permission_denied"):
            consumer.apply(Principal("user", "acme", frozenset()), uuid.uuid4(), uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
