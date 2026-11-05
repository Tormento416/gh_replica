"""In-process reference runtime with durable local audit and approval records.

SQLite is for development. Handlers must be bounded trusted code. This runtime
does not sandbox plugins or supply distributed execution / exactly-once effects.
"""

import json
import copy
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass

from .contracts import PlatformError, canonical, digest, resolve, validate_instance, validate_module


@dataclass(frozen=True)
class Principal:
    actor: str
    tenant: str
    permissions: frozenset[str]


class Kernel:
    def __init__(self, catalog, selected, tenants, database=":memory:"):
        self.installed = {name: copy.deepcopy(validate_module(catalog[name])) for name in resolve(catalog, selected)}
        self.tenants = {tenant: frozenset(modules) for tenant, modules in tenants.items()}
        if any(modules - self.installed.keys() for modules in self.tenants.values()):
            raise PlatformError("tenant_module_not_installed")
        self.handlers = {}
        self.lock = threading.RLock()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY, event TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, actor TEXT NOT NULL,
                module TEXT NOT NULL, tool TEXT NOT NULL, payload_hash TEXT NOT NULL,
                reviewer TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS operations (
                tenant TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, state TEXT NOT NULL, result TEXT,
                PRIMARY KEY (tenant, actor, request_id));
        """)

    def close(self):
        self.db.close()

    def _audit(self, event, **metadata):
        record = canonical({"event": event, "time": time.time(), **metadata})
        row = self.db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        chain_hash = digest({"previous": previous, "record": record})
        self.db.execute("INSERT INTO audit(event, previous, hash) VALUES (?, ?, ?)",
                        (record, previous, chain_hash))
        self.db.commit()

    def verify_audit(self):
        previous = "0" * 64
        for record, parent, chain_hash in self.db.execute("SELECT event, previous, hash FROM audit ORDER BY seq"):
            if parent != previous or chain_hash != digest({"previous": previous, "record": record}):
                return False
            previous = chain_hash
        return True

    def register(self, module, tool, handler):
        if module not in self.installed:
            raise PlatformError("module_not_installed")
        if not any(t["name"] == tool for t in self.installed[module]["tools"]):
            raise PlatformError("unknown_tool")
        if (module, tool) in self.handlers or not callable(handler):
            raise PlatformError("invalid_handler_registration")
        self.handlers[module, tool] = handler

    def _authorize(self, principal, tenant, module, tool):
        if not principal.actor or not tenant or principal.tenant != tenant:
            raise PlatformError("tenant_mismatch")
        if module not in self.installed:
            raise PlatformError("module_not_installed")
        if module not in self.tenants.get(tenant, ()):
            raise PlatformError("tenant_not_entitled")
        descriptor = next((t for t in self.installed[module]["tools"] if t["name"] == tool), None)
        if descriptor is None:
            raise PlatformError("unknown_tool")
        if descriptor["permission"] not in principal.permissions:
            raise PlatformError("permission_denied")
        return descriptor

    def _operation_hash(self, module, tool, payload):
        return digest({"module": module, "moduleVersion": self.installed[module]["version"],
                       "tool": tool, "payload": payload})

    def approve(self, reviewer, requester, module, tool, payload, ttl=300):
        with self.lock:
            descriptor = self._authorize(requester, requester.tenant, module, tool)
            if (reviewer.tenant != requester.tenant or reviewer.actor == requester.actor
                    or "platform:approve" not in reviewer.permissions or not reviewer.actor):
                raise PlatformError("approval_permission_denied")
            if descriptor["risk"] != "controlled" or not 0 < ttl <= 3600:
                raise PlatformError("invalid_approval")
            validate_instance(payload, descriptor["inputSchema"])
            approval_id = str(uuid.uuid4())
            self.db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                            (approval_id, requester.tenant, requester.actor, module, tool,
                             self._operation_hash(module, tool, payload), reviewer.actor, time.time() + ttl))
            self._audit("approval_created", tenant=requester.tenant, actor=requester.actor,
                        reviewer=reviewer.actor, module=module, tool=tool, approval=approval_id)
            return approval_id

    def invoke(self, principal, tenant, module, tool, payload, request_id, approval_id=None):
        """Called only with a principal supplied by a trusted authentication adapter."""
        with self.lock:
            try:
                descriptor = self._authorize(principal, tenant, module, tool)
                if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
                    raise PlatformError("invalid_request_id")
                validate_instance(payload, descriptor["inputSchema"])
                handler = self.handlers.get((module, tool))
                if handler is None:
                    raise PlatformError("handler_unavailable")
                fingerprint = self._operation_hash(module, tool, payload)
                key = (tenant, principal.actor, request_id)
                previous = self.db.execute(
                    "SELECT fingerprint, state, result FROM operations WHERE tenant=? AND actor=? AND request_id=?", key
                ).fetchone()
                if previous:
                    if previous[0] != fingerprint:
                        raise PlatformError("idempotency_conflict")
                    if previous[1] != "completed":
                        raise PlatformError("operation_requires_reconciliation")
                    self._audit("tool_replayed", tenant=tenant, actor=principal.actor, module=module, tool=tool)
                    return json.loads(previous[2])
                if descriptor["risk"] == "controlled":
                    approval = self.db.execute(
                        "SELECT tenant, actor, module, tool, payload_hash, expires, used FROM approvals WHERE id=?",
                        (approval_id,),
                    ).fetchone()
                    if (not approval or approval[:5] != (tenant, principal.actor, module, tool, fingerprint)
                            or approval[5] <= time.time() or approval[6]):
                        raise PlatformError("approval_required")
                    self.db.execute("UPDATE approvals SET used=1 WHERE id=?", (approval_id,))
                self.db.execute("INSERT INTO operations VALUES (?, ?, ?, ?, 'started', NULL)", (*key, fingerprint))
                self._audit("tool_started", tenant=tenant, actor=principal.actor, module=module, tool=tool,
                            request_id=request_id, payload_hash=digest(payload))
                try:
                    result = handler(payload)
                    validate_instance(result, descriptor["outputSchema"])
                    encoded = canonical(result)
                except Exception as exc:
                    self._audit("tool_uncertain", tenant=tenant, actor=principal.actor, module=module, tool=tool)
                    raise PlatformError("operation_requires_reconciliation") from exc
                self.db.execute(
                    "UPDATE operations SET state='completed', result=? WHERE tenant=? AND actor=? AND request_id=?",
                    (encoded, *key),
                )
                self._audit("tool_completed", tenant=tenant, actor=principal.actor, module=module, tool=tool,
                            request_id=request_id)
                return result
            except PlatformError as exc:
                self._audit("tool_denied", tenant=tenant, actor=principal.actor,
                            module=module, tool=tool, reason=str(exc))
                raise


class ModuleAgent:
    """Deterministic intent routing reference, with no model or arbitrary-code path."""

    def __init__(self, kernel, module):
        if module not in kernel.installed:
            raise PlatformError("module_not_installed")
        self.kernel, self.module = kernel, module

    def execute(self, principal, intent, payload, request_id, approval_id=None):
        tool = self.kernel.installed[self.module]["agent"]["intents"].get(intent)
        if tool is None:
            raise PlatformError("unsupported_intent")
        return self.kernel.invoke(principal, principal.tenant, self.module, tool,
                                  payload, request_id, approval_id)


class PlatformAgent:
    def __init__(self, kernel):
        self.agents = {module: ModuleAgent(kernel, module) for module in kernel.installed}

    def execute(self, principal, module, intent, payload, request_id, approval_id=None):
        agent = self.agents.get(module)
        if agent is None:
            raise PlatformError("module_not_installed")
        return agent.execute(principal, intent, payload, request_id, approval_id)
