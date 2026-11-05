"""Provider-neutral contracts for tenant identity, records and event leasing.

Implementations must enforce these semantics independently. A compatible type
signature alone does not establish tenant isolation or transactional correctness.
"""

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from .identity import TenantBinding
from .runtime import Principal


@runtime_checkable
class TenantDirectory(Protocol):
    def tenant_for_host(self, host: str) -> TenantBinding | None:
        """Resolve a trusted host; unknown hosts return None."""

    def grants_for_subject(self, subject: str, tenant: str) -> frozenset[str] | None:
        """Return current tenant-scoped grants, or None for an inactive/missing membership."""


@runtime_checkable
class RecordStore(Protocol):
    def create(self, principal: Principal, body: dict[str, Any]) -> UUID:
        """Atomically create a record and its outbox event under the principal's tenant."""

    def get(self, principal: Principal, record_id: UUID) -> dict[str, Any] | None:
        """Return an authorized tenant's record; absent and cross-tenant IDs return None."""


@runtime_checkable
class OutboxStore(Protocol):
    def claim(self, principal: Principal, limit: int = 20, lease_seconds: int = 60) -> list[dict[str, Any]]:
        """Lease available events without overlapping concurrent claims."""

    def complete(self, principal: Principal, event_id: UUID, lease_id: UUID) -> None:
        """Complete only an unexpired lease in the principal's tenant."""

    def retry(self, principal: Principal, event_id: UUID, lease_id: UUID, delay_seconds: int) -> None:
        """Release a current lease for at-least-once retry after the requested delay."""
