"""Reference post-login navigation, using server-provided identity and grants.

No HTTP endpoint, session management, license authority, or routing is supplied.
The trusted caller must resolve the effective tenant and refresh entitlements.
"""
from dataclasses import dataclass
from typing import Mapping

from .contracts import PlatformError
from .runtime import Principal


@dataclass(frozen=True)
class ModuleEntry:
    module_id: str
    label: str
    permission: str


class Navigation:
    """Select views; downstream services must independently authorize requests."""

    def __init__(self, catalog: Mapping[str, ModuleEntry], installed: frozenset[str],
                 tenant_modules: Mapping[str, frozenset[str]]):
        if (not isinstance(installed, frozenset) or not isinstance(catalog, Mapping)
                or not isinstance(tenant_modules, Mapping)):
            raise ValueError('invalid_navigation_config')
        catalog = dict(catalog)
        if (any(not isinstance(k, str) or not k or not isinstance(v, ModuleEntry)
                or v.module_id != k or not isinstance(v.label, str) or not v.label
                or not isinstance(v.permission, str) or not v.permission for k, v in catalog.items())
                or any(not isinstance(k, str) or not k for k in installed)
                or any(not isinstance(t, str) or not t or not isinstance(modules, frozenset)
                       or not modules <= installed for t, modules in tenant_modules.items())):
            raise ValueError('invalid_navigation_config')
        self._catalog = catalog
        self._installed = installed
        self._tenant_modules = dict(tenant_modules)

    def landing(self, principal: Principal, audience: str):
        """Return logical destinations only; the audience is a user choice, not a grant."""
        if (not isinstance(principal, Principal) or not isinstance(principal.actor, str) or not principal.actor
                or not isinstance(principal.tenant, str) or not principal.tenant
                or not isinstance(principal.permissions, frozenset)):
            raise PlatformError('invalid_principal')
        if principal.tenant not in self._tenant_modules:
            raise PlatformError('navigation_unavailable')
        enabled = self._tenant_modules[principal.tenant]
        if audience == 'staff':
            if 'platform:staff-dashboard' not in principal.permissions:
                raise PlatformError('navigation_unavailable')
            entries = tuple(entry for key, entry in sorted(self._catalog.items())
                            if key in self._installed and key in enabled and entry.permission in principal.permissions)
            return {'destination': 'staff-dashboard', 'modules': entries}
        if audience == 'candidate':
            if ('recruiting' not in self._installed or 'recruiting' not in enabled
                    or 'recruiting:candidate-access' not in principal.permissions):
                raise PlatformError('navigation_unavailable')
            return {'destination': 'candidate-profile', 'module': 'recruiting'}
        raise PlatformError('navigation_unavailable')
