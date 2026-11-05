import json
import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from hyrlink_platform.ade_identity_middleware import IdentityMiddleware
from hyrlink_platform.ade_workos_boundary import WorkOSSessionBoundary
from hyrlink_platform.ade_workos_keys import SessionKeyStore
from hyrlink_platform.identity import IdentityPolicy, TenantBinding


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.key.public_key()))
        jwk.update({"kid": "trusted", "alg": "RS256", "use": "sig"})
        cls.keyset = json.dumps({"keys": [jwk]}).encode()

    def setUp(self):
        self.calls, self.fetches = [], []
        self.grants = {("user", "acme"): frozenset({"client-crm:read"})}
        def fetch(url):
            self.fetches.append(url)
            return self.keyset
        store = SessionKeyStore("client_0123456789ABCDEF", fetch=fetch)
        self.boundary = WorkOSSessionBoundary(
            IdentityPolicy("https://issuer.example", "api"), store,
            lambda host: {"acme.example.com": TenantBinding(host, "acme", "org-acme", True),
                          "globex.example.com": TenantBinding(host, "globex", "org-globex", True)}.get(host),
            lambda user, tenant: self.grants.get((user, tenant)),
        )
        async def app(scope, receive, send):
            self.calls.append(scope["ade.principal"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        self.app = IdentityMiddleware(app, self.boundary)

    def token(self, kid="trusted", changes=None):
        now = int(time.time())
        claims = {"iss": "https://issuer.example", "aud": "api", "sub": "user", "org_id": "org-acme",
                  "token_use": "access", "iat": now, "nbf": now, "exp": now + 300}
        claims.update(changes or {})
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": kid}).encode()

    async def request(self, headers, extra=None):
        messages = []
        scope = {"type": "http", "headers": headers, **(extra or {})}
        async def receive(): return {"type": "http.request", "body": b""}
        async def send(message): messages.append(message)
        await self.app(scope, receive, send)
        return messages

    async def test_verified_principal_overwrites_untrusted_scope(self):
        result = await self.request([(b"host", b"acme.example.com"), (b"authorization", b"Bearer " + self.token())],
                                    {"ade.principal": "forged"})
        self.assertEqual(result[0]["status"], 200)
        self.assertEqual(self.calls[0].tenant, "acme")
        self.assertEqual(self.calls[0].permissions, frozenset({"client-crm:read"}))

    async def test_forwarded_host_cannot_change_tenant(self):
        result = await self.request([(b"host", b"globex.example.com"), (b"x-forwarded-host", b"acme.example.com"),
                                     (b"authorization", b"Bearer " + self.token())])
        self.assertEqual(result[0]["status"], 401)
        self.assertFalse(self.calls)

    async def test_duplicate_or_missing_auth_headers_fail_closed(self):
        auth = (b"authorization", b"Bearer " + self.token())
        for headers in ([(b"host", b"acme.example.com")],
                        [(b"host", b"acme.example.com"), auth, auth],
                        [(b"host", b"acme.example.com"), (b"host", b"globex.example.com"), auth]):
            self.assertEqual((await self.request(headers))[0]["status"], 401)
        self.assertFalse(self.calls)

    async def test_unknown_key_does_not_trigger_repeated_fetches(self):
        headers = [(b"host", b"acme.example.com"), (b"authorization", b"Bearer " + self.token(kid="unknown"))]
        for _ in range(5):
            self.assertEqual((await self.request(headers))[0]["status"], 401)
        self.assertEqual(len(self.fetches), 1)

    async def test_revoked_server_grant_is_not_cached_by_middleware(self):
        headers = [(b"host", b"acme.example.com"), (b"authorization", b"Bearer " + self.token())]
        self.assertEqual((await self.request(headers))[0]["status"], 200)
        self.grants.clear()
        self.assertEqual((await self.request(headers))[0]["status"], 401)

    async def test_websocket_is_not_implicitly_allowed(self):
        messages = []
        async def send(message): messages.append(message)
        async def receive(): return {}
        await self.app({"type": "websocket"}, receive, send)
        self.assertEqual(messages, [{"type": "websocket.close", "code": 1008}])


if __name__ == "__main__":
    unittest.main()
