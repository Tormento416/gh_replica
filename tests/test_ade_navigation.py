import unittest

from hyrlink_platform.ade_navigation import ModuleEntry, Navigation
from hyrlink_platform.contracts import PlatformError
from hyrlink_platform.runtime import Principal


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {'recruiting': ModuleEntry('recruiting', 'Recruiting', 'recruiting:access'),
                        'financials': ModuleEntry('financials', 'Financials', 'financials:access'),
                        'benefits': ModuleEntry('benefits', 'Benefits', 'benefits:access')}
        self.nav = Navigation(self.catalog, frozenset({'recruiting', 'financials'}),
                              {'acme': frozenset({'recruiting'}), 'other': frozenset({'financials'})})

    def principal(self, tenant='acme', permissions=()):
        return Principal('person', tenant, frozenset(permissions))

    def test_staff_dashboard_requires_permission_and_filters_every_boundary(self):
        principal = self.principal(permissions=('platform:staff-dashboard', 'recruiting:access', 'financials:access', 'benefits:access'))
        view = self.nav.landing(principal, 'staff')
        self.assertEqual(view['destination'], 'staff-dashboard')
        self.assertEqual([entry.module_id for entry in view['modules']], ['recruiting'])
        view = self.nav.landing(self.principal(permissions=('platform:staff-dashboard',)), 'staff')
        self.assertEqual(view['modules'], ())
        with self.assertRaisesRegex(PlatformError, 'navigation_unavailable'):
            self.nav.landing(self.principal(permissions=('recruiting:access',)), 'staff')

    def test_candidate_landing_requires_own_permission_and_tenant_license(self):
        candidate = self.principal(permissions=('recruiting:candidate-access',))
        self.assertEqual(self.nav.landing(candidate, 'candidate'), {'destination': 'candidate-profile', 'module': 'recruiting'})
        for principal in (self.principal(), self.principal('other', ('recruiting:candidate-access',)),
                          self.principal('unknown', ('recruiting:candidate-access',))):
            with self.subTest(principal=principal), self.assertRaisesRegex(PlatformError, 'navigation_unavailable'):
                self.nav.landing(principal, 'candidate')
        with self.assertRaisesRegex(PlatformError, 'navigation_unavailable'):
            self.nav.landing(candidate, 'staff')

    def test_caller_cannot_derive_permissions_or_choose_unknown_audience(self):
        with self.assertRaisesRegex(PlatformError, 'invalid_principal'):
            self.nav.landing({'tenant': 'acme'}, 'staff')
        with self.assertRaisesRegex(PlatformError, 'navigation_unavailable'):
            self.nav.landing(self.principal(permissions=('platform:staff-dashboard',)), 'admin')

    def test_configuration_cannot_license_uninstalled_modules(self):
        with self.assertRaisesRegex(ValueError, 'invalid_navigation_config'):
            Navigation(self.catalog, frozenset(), {'acme': frozenset({'recruiting'})})

    def test_configuration_copies_grants(self):
        tenants = {'acme': frozenset({'recruiting'})}
        nav = Navigation(self.catalog, frozenset({'recruiting'}), tenants)
        tenants['acme'] = frozenset()
        self.assertEqual(nav.landing(self.principal(permissions=('recruiting:candidate-access',)), 'candidate')['destination'], 'candidate-profile')
