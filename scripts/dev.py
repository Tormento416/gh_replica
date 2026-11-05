"""Cross-platform development commands; paths derive from this checkout."""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT.parent / "platform-modules"


def commands(action):
    cli = ["uv", "run", "--frozen", "hyrlink"]
    if action == "setup":
        return [["uv", "sync", "--frozen"]]
    if action in ("check", "test"):
        return [
            ["uv", "run", "--frozen", "python", "-m", "unittest", "discover", "-s", "tests", "-v"],
            [*cli, "validate"],
            ["git", "diff", "--check"],
        ]
    if action == "evidence":
        return [[*cli, "verify", "--output", "docs/reports/verification.json", "--module-root", str(MODULES)]]
    if action == "scaffold":
        return [[*cli, "scaffold", "--output", str(MODULES), "--git"]]
    if action == "compose":
        return [[*cli, "compose", "--modules", "client-crm,recruiting", "--output", ".local/composition"]]
    return [[*cli, action]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "check", "test", "demo", "evidence", "scaffold", "compose", "serve"])
    args = parser.parse_args()
    for command in commands(args.action):
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
