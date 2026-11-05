"""Bounded WorkOS AuthKit session-token key retrieval; no credential required."""

import json
import re
import threading
import time
import urllib.request

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .contracts import PlatformError

_CLIENT_ID = re.compile(r"client_[A-Za-z0-9]{8,128}\Z")
_KID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
_MAX_RESPONSE = 256 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError("unexpected_status")
        data = response.read(_MAX_RESPONSE + 1)
        if len(data) > _MAX_RESPONSE:
            raise ValueError("response_too_large")
        return data


def load_session_keys(client_id, fetch=_fetch):
    """Return a fresh validated key snapshot; caller controls refresh/rotation.

    The URL is fixed and never derived from a token header. Fetch failures
    invalidate this snapshot; callers must not silently extend expired keys.
    """
    try:
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            raise ValueError("invalid_client_id")
        raw = fetch("https://api.workos.com/sso/jwks/" + client_id)
        if not isinstance(raw, bytes) or len(raw) > _MAX_RESPONSE:
            raise ValueError("invalid_response")
        from .contracts import parse_json
        payload = parse_json(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list) or not 1 <= len(payload["keys"]) <= 32:
            raise ValueError("invalid_jwks")
        keys = {}
        seen = set()
        for item in payload["keys"]:
            if not isinstance(item, dict):
                raise ValueError("invalid_key")
            kid = item.get("kid")
            if not isinstance(kid, str) or not _KID.fullmatch(kid) or kid in seen:
                raise ValueError("invalid_key_id")
            seen.add(kid)
            if item.get("kty") != "RSA" or item.get("use", "sig") != "sig" or item.get("alg", "RS256") != "RS256":
                continue
            if any(field in item for field in ("d", "p", "q", "dp", "dq", "qi", "oth")):
                raise ValueError("private_key_material")
            key = jwt.PyJWK.from_dict(item, algorithm="RS256").key
            if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
                raise ValueError("weak_key")
            keys[kid] = key
        if not keys:
            raise ValueError("no_supported_keys")
        return keys
    except Exception:
        raise PlatformError("workos_key_loading_failed") from None


class SessionKeyStore:
    """Refresh trusted keys on a bounded schedule; never use expired snapshots."""

    def __init__(self, client_id, ttl=300, fetch=_fetch, clock=time.monotonic):
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id) or not 1 <= ttl <= 3600:
            raise ValueError("invalid_key_store_configuration")
        self.client_id, self.ttl, self.fetch, self.clock = client_id, ttl, fetch, clock
        self._keys, self._expires = None, 0
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            if self._keys is None or self.clock() >= self._expires:
                self._reload()
            return dict(self._keys)

    def refresh(self):
        """Explicit trusted-operator rotation; never call on arbitrary token kids."""
        with self._lock:
            self._reload()
            return dict(self._keys)

    def _reload(self):
        # Clearing first guarantees an outage cannot extend expired trust.
        self._keys, self._expires = None, 0
        keys = load_session_keys(self.client_id, self.fetch)
        self._keys, self._expires = keys, self.clock() + self.ttl
