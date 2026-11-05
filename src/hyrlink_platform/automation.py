"""Repeatable development scaffolding and composition, never production rollout."""

import json
import os
import subprocess
from pathlib import Path

from .contracts import MODULE_SCHEMA, PlatformError, digest, resolve, validate_module

DEPENDENCIES = {
    "lifecycle": ["core-hr"], "benefits": ["core-hr"], "payroll-time": ["core-hr"],
}


def example_manifest(module_id):
    """All generated handlers are synthetic scaffolds, not domain implementations."""
    input_schema = {
        "type": "object", "additionalProperties": False, "properties": {},
    }
    output_schema = {
        "type": "object", "additionalProperties": False,
        "required": ["module", "status"],
        "properties": {"module": {"const": module_id}, "status": {"const": "scaffold-only"}},
    }
    return validate_module({
        "schemaVersion": 1, "id": module_id, "version": "0.1.0", "coreVersion": "0.1.0",
        "requires": DEPENDENCIES.get(module_id, []),
        "agent": {"id": module_id + "-agent", "maxToolCalls": 1,
                  "intents": {"describe": "describe", "prepare": "prepare"}},
        "tools": [
            {"name": "describe", "permission": module_id + ":read", "risk": "read",
             "inputSchema": input_schema, "outputSchema": output_schema},
            {"name": "prepare", "permission": module_id + ":prepare", "risk": "controlled",
             "inputSchema": input_schema, "outputSchema": output_schema},
        ],
    })


def generate_catalog(repository_manifest, output):
    output = Path(output)
    if output.exists():
        raise PlatformError("output_already_exists")
    for repo in repository_manifest["repositories"]:
        module_id = repo["name"].removeprefix("gh-module-")
        destination = output / module_id / "module.json"
        destination.parent.mkdir(parents=True, exist_ok=False)
        destination.write_text(json.dumps(example_manifest(module_id), indent=2) + "\n")


def compose(catalog, selected, output):
    """Export only selected metadata. Does not install domain images or run migrations."""
    ordered = resolve(catalog, selected)
    output = Path(output)
    if output.exists():
        raise PlatformError("output_already_exists")
    output.mkdir(parents=True)
    locked = []
    for name in ordered:
        module = catalog[name]
        destination = output / "modules" / name / "module.json"
        destination.parent.mkdir(parents=True)
        destination.write_text(json.dumps(module, indent=2) + "\n")
        locked.append({"id": name, "version": module["version"], "manifestSha256": digest(module)})
    lock = {"schemaVersion": 1, "coreVersion": "0.1.0", "kind": "metadata-composition", "modules": locked}
    (output / "composition.lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def scaffold(repository_manifest, output, git=False):
    output = Path(output)
    if output.exists():
        raise PlatformError("output_already_exists")
    output.mkdir(parents=True)
    generated = []
    for repo in repository_manifest["repositories"]:
        name = repo["name"]
        module_id = name.removeprefix("gh-module-")
        root = output / name
        root.mkdir()
        for directory in ("agent", "contracts", "src", "migrations", "deploy", "tests", "docs", ".github/workflows"):
            (root / directory).mkdir(parents=True)
        module = example_manifest(module_id)
        (root / "module.json").write_text(json.dumps(module, indent=2) + "\n")
        (root / "agent" / "policy.json").write_text(json.dumps({
            "module": module_id, "default": "deny", "trustedIdentityRequired": True,
            "dataBoundary": "tenant", "externalDataIsUntrusted": True,
            "approval": "server-issued-single-use-for-controlled-actions",
            "modelProvider": "unconfigured", "networkAccess": "none",
        }, indent=2) + "\n")
        (root / "contracts" / "module.schema.json").write_text(json.dumps(MODULE_SCHEMA, indent=2) + "\n")
        (root / "README.md").write_text(
            f"# {name}\n\n{repo['description']}.\n\n"
            "Status: private development scaffold; no business capability is implemented.\n\n"
            "Canonical platform: Tormento416/gh_replica. Implement this bounded domain here; "
            "depend on versioned platform contracts, never other modules' internal code.\n\n"
            "The agent routes describe/prepare intents through deterministic authorization. "
            "The prepare tool requires an independent, server-issued approval. "
            "Both handlers return synthetic scaffold metadata only.\n\n"
            "Validate: `python3 -m unittest discover -s tests -v`\n\n"
            "Before release: domain tests, tenant isolation, migrations, lifecycle rollback, "
            "signed artifacts, SBOM, security review, operational runbook and platform compatibility CI.\n"
        )
        (root / "AGENTS.md").write_text(
            "# Module ownership\n\nThis repository owns only its module. gh_replica owns core contracts and "
            "composition. Reference Hyrlink repositories are read-only. Do not implement direct "
            "cross-module database access or let model output grant permissions. "
            "Use synthetic data. Do not publish, deploy, transfer production data, or add live "
            "provider credentials as part of tests. Document decisions and unresolved gaps.\n"
        )
        (root / "src" / "handler.py").write_text(
            '"""Synthetic example. Replace with a tested module-specific adapter."""\n\n'
            f'def describe(payload):\n    return {{"module": "{module_id}", "status": "scaffold-only"}}\n'
        )
        (root / "tests" / "test_contract.py").write_text(
            '"""Scaffold consistency only; platform conformance tests are required before release."""\n'
            "import json\nimport unittest\nfrom pathlib import Path\n\n"
            "class ManifestTest(unittest.TestCase):\n"
            "    def test_agent_intents_reference_declared_tools(self):\n"
            "        root = Path(__file__).resolve().parents[1]\n"
            "        module = json.loads((root / 'module.json').read_text())\n"
            "        tools = {tool['name'] for tool in module['tools']}\n"
            "        self.assertLessEqual(set(module['agent']['intents'].values()), tools)\n"
            "        self.assertEqual(module['coreVersion'], '0.1.0')\n"
        )
        (root / "SECURITY.md").write_text(
            "# Security status\n\nUnreleased scaffold. No production identity, data, or provider access. "
            "Release requires tenant isolation, deny-by-default tools, replay/approval tests, "
            "dependency review, vulnerability triage, and a private reporting contact.\n"
        )
        (root / "LICENSE").write_text(
            "Copyright (c) 2026 Hyrlink-dev. All rights reserved.\n\n"
            "Private development material. No open-source license is granted. "
            "Third-party components retain their own licenses.\n"
        )
        (root / ".gitignore").write_text("__pycache__/\n.venv/\n.env\n*.sqlite3\n")
        (root / ".github/workflows/ci.yml").write_text(
            "name: Scaffold contract checks\non: [push, pull_request]\n"
            "permissions:\n  contents: read\njobs:\n  contract:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683\n"
            "      - run: python3 -m unittest discover -s tests -v\n"
        )
        if git:
            subprocess.run(["git", "init", "--initial-branch=main", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "remote", "add", "origin",
                            f"https://github.com/{repository_manifest['owner']}/{name}.git"], check=True)
        generated.append(str(root))
    return generated


def provision_repositories(manifest, apply=False):
    """Uses the supplied PAT only for fixed api.github.com requests through gh."""
    env = os.environ.copy()
    if env.get("gh_replica_fg_pat"):
        env["GH_TOKEN"] = env["gh_replica_fg_pat"]
    results = []
    for repo in manifest["repositories"]:
        full_name = f"{manifest['owner']}/{repo['name']}"
        if not apply:
            results.append({"repository": full_name, "visibility": "private", "state": "planned"})
            continue
        # A missing repository and an access denial are distinct; stop on errors.
        found = subprocess.run(["gh", "api", f"repos/{full_name}", "--jq", ".private"],
                               env=env, capture_output=True, text=True)
        if found.returncode == 0:
            if found.stdout.strip() != "true":
                raise PlatformError("existing_repository_is_not_private")
            results.append({"repository": full_name, "state": "exists-private"})
            continue
        if "HTTP 404" not in found.stderr:
            raise PlatformError("repository_lookup_denied")
        created = subprocess.run([
            "gh", "api", "--method", "POST", f"orgs/{manifest['owner']}/repos",
            "-f", f"name={repo['name']}", "-f", f"description={repo['description']}", "-F", "private=true",
            "--jq", ".private",
        ], env=env, capture_output=True, text=True)
        if created.returncode or created.stdout.strip() != "true":
            raise PlatformError("repository_creation_denied")
        results.append({"repository": full_name, "state": "created-private"})
    return results
