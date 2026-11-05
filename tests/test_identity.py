import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from hyrlink_platform.contracts import PlatformError, load_catalog
from hyrlink_platform.identity import IdentityBoundary, IdentityPolicy, TenantBinding
from hyrlink_platform.runtime import Kernel
from pathlib import Path


class IdentityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.policy = IdentityPolicy("https://issuer.example", "hris-api")
        self.bindings = {
            "acme.example.com": TenantBinding("acme.example.com", "acme", "org-acme", True),
            "globex.example.com": TenantBinding("globex.example.com", "globex", "org-globex", True),
            "inactive.example.com": TenantBinding("inactive.example.com", "inactive", "org-acme", False),
        }
        self.grant_rows = {("user-1", "acme"): frozenset({"client-crm:read"})}
        self.boundary = IdentityBoundary(self.policy, {"key-1": self.private.public_key()},
                                         self.bindings.get, lambda subject, tenant: self.grant_rows.get((subject, tenant)))

    def token(self, changes=None, key=None, kid="key-1"):
        now = int(time.time())
        claims = {"iss": self.policy.issuer, "aud": self.policy.audience, "sub": "user-1",
                  "org_id": "org-acme", "token_use": "access", "iat": now, "nbf": now - 1,
                  "exp": now + 600, "permissions": ["platform:approve", "client-crm:prepare"]}
        claims.update(changes or {})
        return jwt.encode(claims, key or self.private, algorithm="RS256", headers={"kid": kid})

    def auth(self, token=None, host="acme.example.com"):
        return self.boundary.authenticate("Bearer " + (token or self.token()), host)

    def rejected(self, token=None, host="acme.example.com"):
        with self.assertRaisesRegex(PlatformError, "^authentication_failed$"):
            self.auth(token, host)

    def test_valid_token_uses_server_grants_not_claims(self):
        principal = self.auth(host="ACME.EXAMPLE.COM:443")
        self.assertEqual((principal.actor, principal.tenant), ("user-1", "acme"))
        self.assertEqual(principal.permissions, frozenset({"client-crm:read"}))

    def test_actual_kernel_uses_verified_grants(self):
        catalog = load_catalog(Path(__file__).resolve().parents[1] / "catalog")
        kernel = Kernel(catalog, ["client-crm"], {"acme": ["client-crm"]})
        try:
            kernel.register("client-crm", "describe", lambda _: {"module": "client-crm", "status": "scaffold-only"})
            self.assertEqual(kernel.invoke(self.auth(), "acme", "client-crm", "describe", {}, "r1")["module"], "client-crm")
            with self.assertRaisesRegex(PlatformError, "permission_denied"):
                kernel.invoke(self.auth(), "acme", "client-crm", "prepare", {}, "r2")
        finally:
            kernel.close()

    def test_wrong_signature_and_unknown_key(self):
        self.rejected(self.token(key=self.other))
        self.rejected(self.token(kid="other"))

    def test_expired_future_and_excessive_lifetime(self):
        now = int(time.time())
        self.rejected(self.token({"exp": now - 100}))
        self.rejected(self.token({"nbf": now + 100}))
        self.rejected(self.token({"iat": now + 100}))
        self.rejected(self.token({"exp": now + 3700}))

    def test_wrong_issuer_audience_or_token_type(self):
        self.rejected(self.token({"iss": "https://other.example"}))
        self.rejected(self.token({"aud": "other-service"}))
        self.rejected(self.token({"aud": ["hris-api", "other-service"]}))
        self.rejected(self.token({"token_use": "id"}))

    def test_cross_tenant_unknown_and_suspended_host_rejected(self):
        self.rejected(host="globex.example.com")
        self.rejected(host="unknown.example.com")
        self.rejected(host="inactive.example.com")

    def test_malformed_hosts_and_missing_bearer_rejected(self):
        for host in ("acme.example.com,evil.example.com", "acme.example.com.evil", "acme.example.com/path", "acme.example.com:444", " acme.example.com"):
            self.rejected(host=host)
        with self.assertRaises(PlatformError):
            self.boundary.authenticate(self.token(), "acme.example.com")

    def test_invalid_or_missing_server_grants_fail_closed(self):
        self.grant_rows.clear()
        self.rejected()
        self.grant_rows[("user-1", "acme")] = {"client-crm:read"}
        self.rejected()

    def test_backend_error_does_not_escape(self):
        def fail(_):
            raise RuntimeError("private backend details")
        boundary = IdentityBoundary(self.policy, {"key-1": self.private.public_key()}, fail, lambda *_: frozenset())
        with self.assertRaises(PlatformError) as error:
            boundary.authenticate("Bearer " + self.token(), "acme.example.com")
        self.assertEqual(str(error.exception), "authentication_failed")
        self.assertIsNone(error.exception.__cause__)

    def test_hmac_algorithm_confusion_rejected(self):
        token = jwt.encode({"sub": "user-1"}, "attacker-secret-long-enough-for-hmac", algorithm="HS256", headers={"kid": "key-1"})
        self.rejected(token)

    def test_weak_and_private_keys_rejected_at_configuration(self):
        weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        for key in (weak.public_key(), self.private):
            with self.assertRaisesRegex(ValueError, "invalid_key_set"):
                IdentityBoundary(self.policy, {"key-1": key}, self.bindings.get, lambda *_: frozenset())


if __name__ == "__main__":
    unittest.main()
