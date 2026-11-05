"""Verified bearer identities and explicit tenant binding for trusted adapters.

Keys, tenant bindings and grants come from server-owned configuration or stores.
This component performs no network discovery and never trusts role or permission
claims from a bearer token. A production ingress must call it for every request.
"""

import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .contracts import PlatformError
from .runtime import Principal

_HOST = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,128}$")


@dataclass(frozen=True)
class TenantBinding:
    host: str
    tenant: str
    organization: str
    active: bool


@dataclass(frozen=True)
class IdentityPolicy:
    issuer: str
    audience: str
    organization_claim: str = "org_id"
    token_use_claim: str = "token_use"
    token_use_value: str = "access"
    max_lifetime_seconds: int = 3600
    clock_skew_seconds: int = 30

    def __post_init__(self):
        if (not self.issuer or not self.audience or not self.organization_claim
                or not self.token_use_claim or not self.token_use_value
                or not 1 <= self.max_lifetime_seconds <= 86400
                or not 0 <= self.clock_skew_seconds <= 60):
            raise ValueError("invalid_identity_policy")


class IdentityBoundary:
    def __init__(self, policy: IdentityPolicy, keys: Mapping[str, object],
                 tenants: Callable[[str], TenantBinding | None],
                 grants: Callable[[str, str], frozenset[str] | None]):
        if (not keys or any(not isinstance(k, str) or not _KEY_ID.fullmatch(k) for k in keys)
                or any(not isinstance(key, RSAPublicKey) or key.key_size < 2048 for key in keys.values())):
            raise ValueError("invalid_key_set")
        self.policy = policy
        self.keys = dict(keys)
        self.tenants = tenants
        self.grants = grants

    def authenticate(self, authorization: str, host: str) -> Principal:
        """Authenticate an access token and bind it to a server-resolved tenant.

        `host` must be supplied by the ingress from a validated request authority;
        do not pass unvalidated forwarded headers. Errors intentionally expose no
        token, key, tenant registry detail, or backend exception.
        """
        try:
            if (not isinstance(authorization, str) or len(authorization) > 8192
                    or not authorization.startswith("Bearer ")):
                raise ValueError()
            token = authorization[7:]
            if not token or any(c.isspace() for c in token):
                raise ValueError()
            if not isinstance(host, str) or not host.isascii() or host != host.strip():
                raise ValueError()
            normalized = host.lower().removesuffix(":443").removesuffix(".")
            if not _HOST.fullmatch(normalized):
                raise ValueError()
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if (header.get("alg") != "RS256" or not isinstance(kid, str)
                    or not _KEY_ID.fullmatch(kid) or kid not in self.keys):
                raise ValueError()
            policy = self.policy
            claims = jwt.decode(token, self.keys[kid], algorithms=["RS256"],
                                issuer=policy.issuer, audience=policy.audience,
                                leeway=policy.clock_skew_seconds,
                                options={"require": ["iss", "aud", "sub", "exp", "iat", "nbf",
                                                     policy.organization_claim, policy.token_use_claim],
                                         "strict_aud": True})
            subject, organization = claims["sub"], claims[policy.organization_claim]
            issued, expires = claims["iat"], claims["exp"]
            if (not isinstance(subject, str) or not subject or len(subject) > 256
                    or not isinstance(organization, str) or not organization or len(organization) > 256
                    or claims[policy.token_use_claim] != policy.token_use_value
                    or type(issued) is not int or type(expires) is not int
                    or expires <= issued or expires - issued > policy.max_lifetime_seconds
                    or issued > time.time() + policy.clock_skew_seconds):
                raise ValueError()
            binding = self.tenants(normalized)
            if (not isinstance(binding, TenantBinding) or binding.active is not True
                    or binding.host != normalized or not binding.tenant
                    or binding.organization != organization):
                raise ValueError()
            permissions = self.grants(subject, binding.tenant)
            if (not isinstance(permissions, frozenset)
                    or any(not isinstance(p, str) or not p for p in permissions)):
                raise ValueError()
            return Principal(actor=subject, tenant=binding.tenant, permissions=permissions)
        except Exception:
            raise PlatformError("authentication_failed") from None
