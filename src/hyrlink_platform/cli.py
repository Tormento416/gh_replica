"""Local-only operator tools. Production rollout is deliberately a separate gate."""

import argparse
import json
import os
import psycopg
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .automation import compose, generate_catalog, provision_repositories, scaffold
from .contracts import PlatformError, load_catalog, parse_json
from .runtime import Kernel, PlatformAgent, Principal


def workos_config_status(environ):
    """Report presence only; never return credentials or configuration values."""
    names = ("WORKOS_CLIENT_ID", "WORKOS_API_KEY", "WORKOS_ISSUER", "WORKOS_AUDIENCE",
             "WORKOS_REDIRECT_URI", "WORKOS_COOKIE_PASSWORD")
    return {name: "set" if environ.get(name, "").strip() else "not set" for name in names}


def demo(catalog):
    kernel = Kernel(catalog, ["client-crm", "recruiting"], {"demo": ["client-crm", "recruiting"]})
    try:
        for module in kernel.installed:
            for tool in ("describe", "prepare"):
                kernel.register(module, tool, lambda payload, name=module: {"module": name, "status": "scaffold-only"})
        user = Principal("demo-operator", "demo", frozenset({"recruiting:read", "recruiting:prepare"}))
        reviewer = Principal("demo-reviewer", "demo", frozenset({"platform:approve"}))
        agent = PlatformAgent(kernel)
        result = agent.execute(user, "recruiting", "describe", {}, "demo-read")
        approval = kernel.approve(reviewer, user, "recruiting", "prepare", {})
        prepared = agent.execute(user, "recruiting", "prepare", {}, "demo-prepare", approval)
        return {"mode": "synthetic-reference", "installed": sorted(kernel.installed),
                "read": result, "approved": prepared, "auditVerified": kernel.verify_audit()}
    finally:
        kernel.close()


def diagnostic_server(catalog, selected, port=8080):
    kernel = Kernel(catalog, selected, {"demo": selected})

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health/ready":
                body = {"status": "ready", "mode": "local-diagnostic-only"}
            elif self.path == "/v1/modules":
                body = {"installed": sorted(kernel.installed)}
            else:
                self.send_error(404)
                return
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    return server, kernel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="gh_replica source checkout")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    commands.add_parser("demo")
    commands.add_parser("workos-config")
    commands.add_parser("migration-plan")
    commands.add_parser("migration-apply")
    for command in ("compose", "scaffold", "catalog"):
        child = commands.add_parser(command)
        child.add_argument("--output", required=True, type=Path)
        if command == "compose":
            child.add_argument("--modules", required=True)
        if command == "scaffold":
            child.add_argument("--git", action="store_true")
    child = commands.add_parser("repositories")
    child.add_argument("--apply", action="store_true")
    child = commands.add_parser("verify")
    child.add_argument("--output", required=True, type=Path)
    child.add_argument("--module-root", type=Path)
    child = commands.add_parser("serve")
    child.add_argument("--modules", default="client-crm,recruiting")
    child.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        manifest = parse_json((root / "docs/architecture/module-repositories.json").read_bytes())
        if args.command in ("migration-plan", "migration-apply"):
            from .ade_migrations import apply, plan
            dsn = os.environ.get("ADE_MIGRATION_DSN", "")
            if not dsn:
                raise PlatformError("migration_dsn_not_configured")
            result = (plan if args.command == "migration-plan" else apply)(dsn, root / "migrations")
        elif args.command == "workos-config":
            result = {"workos": workos_config_status(os.environ), "connectivity": "not tested"}
        elif args.command == "catalog":
            generate_catalog(manifest, args.output)
            result = {"generated": len(manifest["repositories"])}
        elif args.command == "scaffold":
            result = {"repositories": scaffold(manifest, args.output, args.git)}
        elif args.command == "repositories":
            result = {"repositories": provision_repositories(manifest, args.apply)}
        elif args.command == "verify":
            from .verification import verify
            result = verify(root, args.output, args.module_root)
        else:
            catalog = load_catalog(root / "catalog")
            if args.command == "validate":
                expected = {r["name"].removeprefix("gh-module-") for r in manifest["repositories"]}
                if expected != set(catalog):
                    raise PlatformError("catalog_membership_mismatch")
                # Resolve every module with all dependencies to catch global cycles.
                from .contracts import resolve
                resolve(catalog, list(catalog))
                result = {"validModules": len(catalog), "coreVersion": "0.1.0"}
            elif args.command == "demo":
                result = demo(catalog)
            elif args.command == "compose":
                result = compose(catalog, args.modules.split(","), args.output)
            elif args.command == "serve":
                server, kernel = diagnostic_server(catalog, args.modules.split(","), args.port)
                print(json.dumps({"mode": "loopback-diagnostics", "port": server.server_port}), flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                    kernel.close()
                return
        print(json.dumps(result, indent=2))
    except psycopg.Error:
        parser.exit(1, "Setup failed: migration_database_error\n")
    except (PlatformError, OSError) as exc:
        parser.exit(1, f"Setup failed: {exc}\n")


if __name__ == "__main__":
    main()
