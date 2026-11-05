"""Connect independently configured WorkOS session keys to tenant authorization."""

from .contracts import PlatformError
from .identity import IdentityBoundary


class WorkOSSessionBoundary:
    """Create a verifier from a fresh, trusted key snapshot for every request.

    The configured issuer, audience and claim requirements must match the chosen
    token profile. This adapter does not automatically trust token-supplied keys.
    """

    def __init__(self, policy, key_store, tenants, grants):
        self.policy, self.key_store = policy, key_store
        self.tenants, self.grants = tenants, grants

    def authenticate(self, authorization, host):
        try:
            keys = self.key_store.get()
            boundary = IdentityBoundary(self.policy, keys, self.tenants, self.grants)
            return boundary.authenticate(authorization, host)
        except Exception:
            raise PlatformError("authentication_failed") from None
