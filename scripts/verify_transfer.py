"""Verify extracted transfer files. Run from any directory after extraction."""

import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "TRANSFER_MANIFEST.json").read_text(encoding="utf-8"))
    failures = []
    for entry in manifest["files"]:
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root):
            failures.append("unsafe path")
            continue
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
            failures.append(entry["path"])
    if failures:
        raise SystemExit("Transfer validation failed for: " + ", ".join(failures))
    print(f"Verified {len(manifest['files'])} transferred files, including Git metadata.")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parent)
