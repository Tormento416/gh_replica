import json
import ssl
import threading
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from hyrlink_platform.ade_event_delivery import HTTPSDelivery, deliver_batch
from hyrlink_platform.contracts import PlatformError
from hyrlink_platform.runtime import Principal


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
                .sign(key, hashes.SHA256()))
        cert_path = Path(cls.tmp.name) / "cert.pem"
        key_path = Path(cls.tmp.name) / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        cls.received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                cls.received.append((self.path, dict(self.headers), self.rfile.read(length)))
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/other")
                else:
                    self.send_response(202)
                self.end_headers()
            def log_message(self, *_): pass
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path, key_path)
        cls.server.socket = server_context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.client_context = ssl.create_default_context(cafile=str(cert_path))
        cls.base = f"https://localhost:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        self.received.clear()
        self.event = {"event_id": uuid.uuid4(), "record_id": uuid.uuid4(), "event_type": "record.created.v1",
                      "attempt": 1, "lease_id": uuid.uuid4()}
        self.principal = Principal("worker", "acme", frozenset({"platform:outbox-dispatch"}))

    def sink(self, path="/events"):
        return HTTPSDelivery(self.base + path, frozenset({"localhost"}), "synthetic-token",
                             ssl_context=self.client_context)

    def test_verified_tls_delivers_scoped_idempotent_envelope(self):
        self.sink().deliver("acme", self.event)
        path, headers, body = self.received[0]
        self.assertEqual(path, "/events")
        self.assertEqual(headers["Authorization"], "Bearer synthetic-token")
        self.assertEqual(headers["Idempotency-Key"], str(self.event["event_id"]))
        self.assertEqual(json.loads(body), {"tenant_id": "acme", "event_id": str(self.event["event_id"]),
                                           "record_id": str(self.event["record_id"]), "event_type": "record.created.v1"})

    def test_redirect_is_not_followed(self):
        with self.assertRaisesRegex(PlatformError, "delivery_failed"):
            self.sink("/redirect").deliver("acme", self.event)
        self.assertEqual([request[0] for request in self.received], ["/redirect"])

    def test_untrusted_certificate_fails(self):
        sink = HTTPSDelivery(self.base + "/events", frozenset({"localhost"}), "synthetic-token")
        with self.assertRaisesRegex(PlatformError, "delivery_failed"):
            sink.deliver("acme", self.event)
        self.assertEqual(self.received, [])

    def test_untrusted_destination_and_insecure_context_rejected(self):
        for endpoint, hosts in (("http://localhost/events", frozenset({"localhost"})),
                                ("https://evil.example/events", frozenset({"trusted.example"})),
                                ("https://user:pass@localhost/events", frozenset({"localhost"})),
                                ("https://localhost/events?secret=x", frozenset({"localhost"}))):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                HTTPSDelivery(endpoint, hosts, "synthetic-token")
        insecure = ssl._create_unverified_context()
        with self.assertRaisesRegex(ValueError, "tls_verification_required"):
            HTTPSDelivery(self.base + "/events", frozenset({"localhost"}), "synthetic-token", ssl_context=insecure)

    def test_dispatch_acknowledges_only_after_success(self):
        class Store:
            def __init__(self, event): self.event, self.completed = event, []
            def claim(self, *_args, **_kwargs): return [self.event]
            def complete(self, principal, event, lease): self.completed.append((event, lease))
            def retry(self, *_args): raise AssertionError("unexpected retry")
        store = Store(self.event)
        result = deliver_batch(store, self.principal, self.sink(), limit=1, lease_seconds=20)
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(store.completed, [(self.event["event_id"], self.event["lease_id"])])

    def test_failed_send_schedules_retry_without_leaking_provider_details(self):
        class Store:
            def __init__(self, event): self.event, self.delays = event, []
            def claim(self, *_args, **_kwargs): return [self.event]
            def complete(self, *_args): raise AssertionError("unexpected acknowledgment")
            def retry(self, principal, event, lease, delay): self.delays.append(delay)
        store = Store(self.event)
        result = deliver_batch(store, self.principal, self.sink("/redirect"), limit=1, lease_seconds=20)
        self.assertEqual(result["retry_scheduled"], 1)
        self.assertEqual(store.delays, [2])

    def test_ack_failure_is_uncertain_and_not_sent_twice(self):
        class Store:
            def claim(self, *_args, **_kwargs): return [self.event]
            def complete(self, *_args): raise RuntimeError("database unavailable")
            def retry(self, *_args): raise AssertionError("must not retry after uncertain ack")
        store = Store()
        store.event = self.event
        result = deliver_batch(store, self.principal, self.sink(), limit=1, lease_seconds=20)
        self.assertEqual(result["uncertain"], 1)
        self.assertEqual(len(self.received), 1)
