import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from hyrlink_platform.automation import compose, scaffold
from hyrlink_platform.cli import demo, diagnostic_server
from hyrlink_platform.contracts import PlatformError, load_catalog, parse_json, resolve, validate_module
from hyrlink_platform.runtime import Kernel, PlatformAgent, Principal

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "catalog")

    def test_all_fourteen_contracts_load(self):
        self.assertEqual(len(self.catalog), 14)

    def test_duplicate_module_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("one", "two"):
                path = Path(directory) / name
                path.mkdir()
                (path / "module.json").write_text(json.dumps(self.catalog["client-crm"]))
            with self.assertRaisesRegex(PlatformError, "duplicate_module"):
                load_catalog(directory)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(PlatformError):
            parse_json('{"tenant":"a","tenant":"b"}')

    def test_nonfinite_number_rejected(self):
        with self.assertRaises(PlatformError):
            parse_json('{"amount":NaN}')

    def test_missing_dependency_never_silently_installed(self):
        with self.assertRaisesRegex(PlatformError, "missing_required_module"):
            resolve(self.catalog, ["payroll-time"])

    def test_dependencies_install_before_dependents(self):
        self.assertEqual(resolve(self.catalog, ["payroll-time", "core-hr"]), ["core-hr", "payroll-time"])

    def test_dependency_cycle_rejected(self):
        self.catalog["core-hr"]["requires"] = ["payroll-time"]
        with self.assertRaisesRegex(PlatformError, "dependency_cycle"):
            resolve(self.catalog, ["payroll-time", "core-hr"])

    def test_unknown_module_rejected(self):
        with self.assertRaisesRegex(PlatformError, "unknown_module"):
            resolve(self.catalog, ["does-not-exist"])

    def test_duplicate_selection_rejected(self):
        with self.assertRaisesRegex(PlatformError, "duplicate_selection"):
            resolve(self.catalog, ["client-crm", "client-crm"])

    def test_empty_cell_is_valid(self):
        self.assertEqual(resolve(self.catalog, []), [])

    def test_core_version_mismatch_rejected(self):
        module = self.catalog["client-crm"]
        module["coreVersion"] = "0.2.0"
        with self.assertRaisesRegex(PlatformError, "incompatible_core"):
            validate_module(module)

    def test_unknown_contract_fields_rejected(self):
        module = self.catalog["client-crm"]
        module["shellCommand"] = "curl attacker"
        with self.assertRaises(PlatformError):
            validate_module(module)

    def test_agent_cannot_reference_undeclared_tool(self):
        module = self.catalog["client-crm"]
        module["agent"]["intents"]["describe"] = "shell"
        with self.assertRaisesRegex(PlatformError, "unknown_agent_tool"):
            validate_module(module)

    def test_tool_cannot_claim_another_modules_permission(self):
        module = self.catalog["client-crm"]
        module["tools"][0]["permission"] = "payroll-time:read"
        with self.assertRaisesRegex(PlatformError, "permission_namespace"):
            validate_module(module)

    def test_remote_schema_reference_rejected(self):
        module = self.catalog["client-crm"]
        module["tools"][0]["inputSchema"]["$ref"] = "https://attacker.invalid/identity"
        with self.assertRaisesRegex(PlatformError, "schema_references"):
            validate_module(module)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "catalog")
        self.kernel = Kernel(self.catalog, ["client-crm", "recruiting"],
                             {"acme": ["client-crm", "recruiting"], "globex": ["client-crm"]})
        self.user = Principal("operator", "acme", frozenset({"client-crm:read", "client-crm:prepare"}))
        self.reviewer = Principal("reviewer", "acme", frozenset({"platform:approve"}))
        self.calls = []

        def handler(payload):
            self.calls.append(payload)
            return {"module": "client-crm", "status": "scaffold-only"}

        self.kernel.register("client-crm", "describe", handler)
        self.kernel.register("client-crm", "prepare", handler)

    def tearDown(self):
        self.kernel.close()

    def invoke(self, **overrides):
        values = dict(principal=self.user, tenant="acme", module="client-crm", tool="describe", payload={}, request_id="request-1")
        values.update(overrides)
        return self.kernel.invoke(**values)

    def approval(self):
        return self.kernel.approve(self.reviewer, self.user, "client-crm", "prepare", {})

    def test_platform_delegates_through_module_agent(self):
        result = PlatformAgent(self.kernel).execute(self.user, "client-crm", "describe", {}, "agent-read")
        self.assertEqual(result["module"], "client-crm")
        self.assertEqual(len(self.calls), 1)

    def test_cross_tenant_request_denied_before_handler(self):
        with self.assertRaisesRegex(PlatformError, "tenant_mismatch"):
            self.invoke(tenant="globex")
        self.assertEqual(self.calls, [])

    def test_no_permissions_denied(self):
        with self.assertRaisesRegex(PlatformError, "permission_denied"):
            self.invoke(principal=Principal("viewer", "acme", frozenset()))

    def test_unknown_tenant_denied(self):
        with self.assertRaisesRegex(PlatformError, "tenant_not_entitled"):
            self.invoke(tenant="unknown", principal=Principal("viewer", "unknown", frozenset({"client-crm:read"})))

    def test_absent_module_has_no_handler_or_agent(self):
        with self.assertRaisesRegex(PlatformError, "module_not_installed"):
            self.kernel.register("benefits", "describe", lambda _: {})
        with self.assertRaisesRegex(PlatformError, "module_not_installed"):
            PlatformAgent(self.kernel).execute(self.user, "benefits", "describe", {}, "no-module")

    def test_installed_module_still_requires_tenant_entitlement(self):
        user = Principal("globex-user", "globex", frozenset({"recruiting:read"}))
        with self.assertRaisesRegex(PlatformError, "tenant_not_entitled"):
            self.invoke(principal=user, tenant="globex", module="recruiting")

    def test_payload_cannot_supply_identity_or_permissions(self):
        with self.assertRaisesRegex(PlatformError, "schema_validation"):
            self.invoke(payload={"tenant": "globex", "permissions": ["platform:approve"]})

    def test_controlled_tool_requires_approval(self):
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(tool="prepare")
        self.assertEqual(self.calls, [])

    def test_independent_approval_allows_one_execution(self):
        approval = self.approval()
        self.invoke(tool="prepare", approval_id=approval)
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(tool="prepare", approval_id=approval, request_id="second-operation")
        self.assertEqual(len(self.calls), 1)

    def test_controlled_action_audit_links_its_approval(self):
        approval = self.approval()
        self.invoke(tool="prepare", approval_id=approval)
        events = [json.loads(row[0]) for row in self.kernel.db.execute("SELECT event FROM audit")]
        started = next(event for event in events if event["event"] == "tool_started")
        self.assertEqual(started["approval"], approval)
        self.assertEqual(started["request_id"], "request-1")

    def test_self_approval_rejected(self):
        reviewer = Principal(self.user.actor, "acme", frozenset({"platform:approve"}))
        with self.assertRaisesRegex(PlatformError, "approval_permission_denied"):
            self.kernel.approve(reviewer, self.user, "client-crm", "prepare", {})

    def test_cross_tenant_approver_rejected(self):
        reviewer = Principal("reviewer", "globex", frozenset({"platform:approve"}))
        with self.assertRaisesRegex(PlatformError, "approval_permission_denied"):
            self.kernel.approve(reviewer, self.user, "client-crm", "prepare", {})

    def test_approver_requires_explicit_permission(self):
        with self.assertRaisesRegex(PlatformError, "approval_permission_denied"):
            self.kernel.approve(Principal("reviewer", "acme", frozenset()), self.user, "client-crm", "prepare", {})

    def test_expired_approval_rejected(self):
        approval = self.approval()
        self.kernel.db.execute("UPDATE approvals SET expires=0")
        self.kernel.db.commit()
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(tool="prepare", approval_id=approval)

    def test_approval_bound_to_requester(self):
        approval = self.approval()
        other = Principal("other", "acme", self.user.permissions)
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(principal=other, tool="prepare", approval_id=approval)

    def test_read_tool_cannot_request_approval(self):
        with self.assertRaisesRegex(PlatformError, "invalid_approval"):
            self.kernel.approve(self.reviewer, self.user, "client-crm", "describe", {})

    def test_retry_returns_same_result_without_second_call(self):
        first = self.invoke()
        self.assertEqual(first, self.invoke())
        self.assertEqual(len(self.calls), 1)

    def test_retry_controlled_action_does_not_need_second_approval(self):
        first = self.invoke(tool="prepare", approval_id=self.approval())
        self.assertEqual(first, self.invoke(tool="prepare"))
        self.assertEqual(len(self.calls), 1)

    def test_request_id_reuse_for_different_operation_denied(self):
        self.invoke()
        with self.assertRaisesRegex(PlatformError, "idempotency_conflict"):
            self.invoke(tool="prepare", approval_id=self.approval())

    def test_module_upgrade_does_not_reuse_old_result(self):
        self.invoke()
        self.kernel.installed["client-crm"]["version"] = "0.1.1"
        with self.assertRaisesRegex(PlatformError, "idempotency_conflict"):
            self.invoke()

    def test_module_upgrade_invalidates_prior_approval(self):
        approval = self.approval()
        self.kernel.installed["client-crm"]["version"] = "0.1.1"
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(tool="prepare", approval_id=approval)

    def test_failed_handler_is_not_retried_automatically(self):
        def fail(_):
            self.calls.append("failure")
            raise RuntimeError("private provider response")
        self.kernel.handlers["client-crm", "describe"] = fail
        for _ in range(2):
            with self.assertRaisesRegex(PlatformError, "operation_requires_reconciliation"):
                self.invoke()
        self.assertEqual(self.calls, ["failure"])

    def test_malformed_handler_output_is_not_accepted(self):
        self.kernel.handlers["client-crm", "describe"] = lambda _: {"secret": "unexpected-data"}
        with self.assertRaisesRegex(PlatformError, "operation_requires_reconciliation"):
            self.invoke()

    def test_unknown_intent_cannot_escape_tool_allowlist(self):
        with self.assertRaisesRegex(PlatformError, "unsupported_intent"):
            PlatformAgent(self.kernel).execute(self.user, "client-crm", "execute-shell", {}, "attack")

    def test_duplicate_handler_rejected(self):
        with self.assertRaisesRegex(PlatformError, "invalid_handler_registration"):
            self.kernel.register("client-crm", "describe", lambda _: {})

    def test_contextual_handler_receives_verified_principal_and_request_id(self):
        del self.kernel.handlers["client-crm", "describe"]
        observed = []
        def handler(principal, payload, request_id):
            observed.append((principal, payload, request_id))
            return {"module": "client-crm", "status": "scaffold-only"}
        self.kernel.register_with_context("client-crm", "describe", handler)
        self.invoke(request_id="server-request")
        self.invoke(request_id="server-request")
        self.assertEqual(observed, [(self.user, {}, "server-request")])

    def test_contextual_handler_is_not_called_before_permission_or_approval(self):
        del self.kernel.handlers["client-crm", "prepare"]
        observed = []
        self.kernel.register_with_context("client-crm", "prepare", lambda *args: observed.append(args))
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(tool="prepare")
        with self.assertRaisesRegex(PlatformError, "permission_denied"):
            self.invoke(tool="prepare", principal=Principal("user", "acme", frozenset()))
        self.assertEqual(observed, [])

    def test_source_catalog_mutation_cannot_downgrade_runtime_approval(self):
        self.catalog["client-crm"]["tools"][1]["risk"] = "read"
        with self.assertRaisesRegex(PlatformError, "approval_required"):
            self.invoke(tool="prepare")

    def test_unregistered_handler_unavailable(self):
        del self.kernel.handlers["client-crm", "describe"]
        with self.assertRaisesRegex(PlatformError, "handler_unavailable"):
            self.invoke()

    def test_audit_records_denials_and_detects_tampering(self):
        with self.assertRaises(PlatformError):
            self.invoke(tenant="globex")
        self.assertTrue(self.kernel.verify_audit())
        record = self.kernel.db.execute("SELECT event FROM audit").fetchone()[0]
        self.assertIn("tool_denied", record)
        self.kernel.db.execute("UPDATE audit SET event='modified'")
        self.kernel.db.commit()
        self.assertFalse(self.kernel.verify_audit())

    def test_audit_does_not_include_payload_or_provider_error(self):
        with self.assertRaises(PlatformError):
            self.invoke(payload={"secret": "never-log-this"})
        events = str(self.kernel.db.execute("SELECT event FROM audit").fetchall())
        self.assertNotIn("never-log-this", events)

    def test_tenant_configuration_cannot_enable_uninstalled_module(self):
        with self.assertRaisesRegex(PlatformError, "tenant_module_not_installed"):
            Kernel(self.catalog, ["client-crm"], {"acme": ["recruiting"]})

    def test_restart_preserves_completed_idempotency_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "kernel.sqlite3")
            for _ in range(2):
                kernel = Kernel(self.catalog, ["client-crm"], {"acme": ["client-crm"]}, path)
                kernel.register("client-crm", "describe", lambda p: self.calls.append(p) or {"module": "client-crm", "status": "scaffold-only"})
                kernel.invoke(self.user, "acme", "client-crm", "describe", {}, "persistent")
                self.assertTrue(kernel.verify_audit())
                kernel.close()
            self.assertEqual(len(self.calls), 1)


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "catalog")

    def test_composition_physically_omits_unselected_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cell"
            lock = compose(self.catalog, ["recruiting"], target)
            self.assertEqual([m["id"] for m in lock["modules"]], ["recruiting"])
            self.assertEqual([p.name for p in (target / "modules").iterdir()], ["recruiting"])
            self.assertFalse((target / "modules/payroll-time").exists())

    def test_composition_cannot_overwrite_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PlatformError, "output_already_exists"):
                compose(self.catalog, ["recruiting"], directory)

    def test_missing_dependency_leaves_no_partial_composition(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cell"
            with self.assertRaises(PlatformError):
                compose(self.catalog, ["benefits"], target)
            self.assertFalse(target.exists())

    def test_scaffold_is_private_and_contains_no_business_claim(self):
        manifest = {"owner": "Hyrlink-dev", "repositories": [
            {"name": "gh-module-recruiting", "description": "Recruiting"}]}
        with tempfile.TemporaryDirectory() as directory:
            targets = scaffold(manifest, Path(directory) / "new")
            root = Path(targets[0])
            self.assertIn("All rights reserved", (root / "LICENSE").read_text())
            self.assertIn("no business capability", (root / "README.md").read_text())
            validate_module(parse_json((root / "module.json").read_bytes()))

    def test_local_http_reports_only_selected_modules(self):
        server, kernel = diagnostic_server(self.catalog, ["recruiting"], port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(base + "/health/ready", timeout=5) as response:
                self.assertEqual(json.load(response)["status"], "ready")
            with urllib.request.urlopen(base + "/v1/modules", timeout=5) as response:
                self.assertEqual(json.load(response)["installed"], ["recruiting"])
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + "/v1/payroll", timeout=5)
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            kernel.close()

    def test_demo_completes_with_audit_integrity(self):
        self.assertTrue(demo(self.catalog)["auditVerified"])


if __name__ == "__main__":
    unittest.main()
