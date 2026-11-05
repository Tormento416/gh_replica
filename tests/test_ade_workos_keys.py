import json
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from hyrlink_platform.ade_workos_keys import SessionKeyStore, _fetch, load_session_keys
from hyrlink_platform.contracts import PlatformError
from hyrlink_platform.identity import IdentityBoundary, IdentityPolicy, TenantBinding


class WorkOSKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.private.public_key()))
        cls.public_jwk.update({"kid": "key-1", "alg": "RS256", "use": "sig"})

    def payload(self, keys=None):
        return json.dumps({"keys": [self.public_jwk] if keys is None else keys}).encode()

    def test_fixed_url_and_verified_token_round_trip(self):
        urls = []
        keys = load_session_keys("client_0123456789ABCDEF", lambda url: urls.append(url) or self.payload())
        self.assertEqual(urls, ["https://api.workos.com/sso/jwks/client_0123456789ABCDEF"])
        boundary = IdentityBoundary(IdentityPolicy("https://issuer.example", "resource"), keys,
                                    lambda host: TenantBinding(host, "tenant", "org-1", True),
                                    lambda user, tenant: frozenset({"client-crm:read"}))
        now = int(time.time())
        token = jwt.encode({"iss": "https://issuer.example", "aud": "resource", "sub": "person",
                            "org_id": "org-1", "token_use": "access", "iat": now,
                            "nbf": now, "exp": now + 300}, self.private, algorithm="RS256", headers={"kid": "key-1"})
        self.assertEqual(boundary.authenticate("Bearer " + token, "tenant.example.com").tenant, "tenant")

    def test_client_id_cannot_redirect_fetch(self):
        for client_id in ("https://example.com", "client_abcdefgh/../../evil", "client_a?x=y", ""):
            with self.subTest(client_id=client_id), self.assertRaises(PlatformError):
                load_session_keys(client_id, lambda _: self.fail("fetch must not run"))

    def test_invalid_duplicate_weak_private_and_oversized_keys_fail(self):
        weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        weak_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(weak.public_key()))
        weak_jwk["kid"] = "weak"
        private_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private))
        private_jwk["kid"] = "private"
        payloads = [self.payload([]), self.payload([self.public_jwk, self.public_jwk]),
                    self.payload([weak_jwk]), self.payload([private_jwk]),
                    self.payload([self.public_jwk] * 33), b"x" * (256 * 1024 + 1), b'{"keys":[],"keys":[]}']
        for data in payloads:
            with self.subTest(size=len(data)), self.assertRaisesRegex(PlatformError, "workos_key_loading_failed"):
                load_session_keys("client_0123456789ABCDEF", lambda _, value=data: value)

    def test_network_failure_is_sanitized(self):
        def fail(_):
            raise RuntimeError("sensitive response")
        with self.assertRaises(PlatformError) as error:
            load_session_keys("client_0123456789ABCDEF", fail)
        self.assertEqual(str(error.exception), "workos_key_loading_failed")
        self.assertIsNone(error.exception.__cause__)

    def test_default_fetch_refuses_redirects_and_has_timeout(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b"{}"
        with patch("urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = Response()
            self.assertEqual(_fetch("https://api.workos.com/sso/jwks/client_12345678"), b"{}")
            self.assertEqual(factory.call_args.args[0].__class__.__name__, "_NoRedirect")
            self.assertEqual(factory.return_value.open.call_args.kwargs["timeout"], 5)

    def test_rotation_refresh_and_snapshot_copy(self):
        now, calls = [10], []
        rotated = dict(self.public_jwk, kid="rotated")
        def fetch(_):
            calls.append(1)
            return self.payload([self.public_jwk] if len(calls) == 1 else [rotated])
        store = SessionKeyStore("client_0123456789ABCDEF", ttl=10, fetch=fetch, clock=lambda: now[0])
        snapshot = store.get()
        snapshot.clear()
        self.assertEqual(set(store.get()), {"key-1"})
        self.assertEqual(len(calls), 1)
        now[0] = 20
        self.assertEqual(set(store.get()), {"rotated"})
        self.assertEqual(len(calls), 2)

    def test_expired_keys_fail_closed_on_outage(self):
        now = [0]
        def fetch(_):
            if now[0] >= 5:
                raise RuntimeError("offline")
            return self.payload()
        store = SessionKeyStore("client_0123456789ABCDEF", ttl=5, fetch=fetch, clock=lambda: now[0])
        self.assertIn("key-1", store.get())
        now[0] = 5
        with self.assertRaisesRegex(PlatformError, "workos_key_loading_failed"):
            store.get()
        with self.assertRaisesRegex(PlatformError, "workos_key_loading_failed"):
            store.get()

    def test_explicit_refresh_updates_keys_without_waiting_for_expiry(self):
        keys = [self.public_jwk]
        store = SessionKeyStore("client_0123456789ABCDEF", fetch=lambda _: self.payload(keys))
        self.assertEqual(set(store.get()), {"key-1"})
        keys[:] = [dict(self.public_jwk, kid="key-2")]
        self.assertEqual(set(store.refresh()), {"key-2"})


if __name__ == "__main__":
    unittest.main()
