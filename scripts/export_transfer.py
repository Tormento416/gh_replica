"""Export the backbone and sibling module repositories without credentials/envs."""

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".venv", "__pycache__", ".pytest_cache", ".ssh", "node_modules", ".aws", ".codex", ".agents"}
SECRET = re.compile(rb"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|BEGIN (?:OPENSSH|RSA|EC) PRIVATE KEY")

INSTRUCTIONS = r"""HRIS PROJECT TRANSFER

Extract this ZIP directly into D:\HRIS_project.
Expected layout:
  D:\HRIS_project\gh_replica
  D:\HRIS_project\platform-modules\gh-module-...
  D:\HRIS_project\TRANSFER_MANIFEST.json
  D:\HRIS_project\verify_transfer.py

This is a transfer copy. The cloud originals are retained until the destination
has been verified; no deletion is performed by extraction or validation.

PowerShell:
  Set-Location 'D:\HRIS_project'
  py -3.12 .\verify_transfer.py
  git -C .\gh_replica status --short
  Set-Location .\gh_replica
  uv sync --frozen
  uv run --frozen python scripts/dev.py check
  uv run --frozen python scripts/dev.py demo
  uv run --frozen python scripts/dev.py evidence

Prerequisites: Python 3.12, Git and uv installed on Windows.
Source code, plans, uncommitted changes, module scaffolds, Git history/config and
rebuildable artifacts are included. Tokens, .env files, SSH keys, caches and Linux
virtual environments are excluded. Recreate the environment with uv sync.

Git commits and branches are preserved. Each module has an unborn main branch;
its origin URL does not mean that a private GitHub repository has been created.

The .local/wheelhouse is a Linux/Python-3.12 dependency artifact retained for
reference. It is not a Windows offline installation bundle. Windows validation
and any platform-specific dependency download must happen on your Windows host.

No reference repositories are included; they were not modified. Point a local
Codex session at this folder to continue. Do not re-clone over this transfer:
uncommitted work is included here and would be missing from a fresh clone.
"""


def collect():
    sources = [(ROOT, "gh_replica")]
    module_root = ROOT.parent / "platform-modules"
    manifest = json.loads((ROOT / "docs/architecture/module-repositories.json").read_text())
    for repo in manifest["repositories"]:
        module = module_root / repo["name"]
        if not (module / ".git").is_dir():
            raise ValueError("Missing module Git directory: " + repo["name"])
        sources.append((module, "platform-modules/" + repo["name"]))
    files = {}
    for source, prefix in sources:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if set(relative.parts) & EXCLUDED:
                continue
            if relative.parts[0] == ".local" and (len(relative.parts) < 2 or relative.parts[1] not in {"wheelhouse", "requirements.txt", "composition"}):
                continue
            if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise ValueError("Symlink requires explicit transfer handling: " + str(relative))
            if not path.is_file():
                continue
            data = path.read_bytes()
            if SECRET.search(data):
                raise ValueError("Credential pattern in file; transfer stopped: " + str(relative))
            if relative.as_posix() == ".git/config" and (b"extraheader" in data.lower() or re.search(rb"https?://[^/\s]+@", data)):
                raise ValueError("Credential-bearing Git configuration; transfer stopped")
            files[prefix + "/" + relative.as_posix()] = data
    files["START_HERE.txt"] = INSTRUCTIONS.encode("utf-8")
    files["verify_transfer.py"] = (ROOT / "scripts/verify_transfer.py").read_bytes()
    if len({name.casefold() for name in files}) != len(files):
        raise ValueError("Case-insensitive path collision")
    return files


def export(output):
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(ROOT.parent / "platform-modules"):
        raise ValueError("Use an unused destination outside project repository roots")
    files = collect()
    manifest = {
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "intendedWindowsRoot": "D:\\HRIS_project",
        "repositories": 15,
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                  for name, data in sorted(files.items())],
    }
    files["TRANSFER_MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
    print(json.dumps({"archive": str(output), "files": len(manifest["files"]),
                      "bytes": output.stat().st_size,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    export(parser.parse_args().output)
