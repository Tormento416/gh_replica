"""Collect honest, machine-readable local verification evidence."""

import contextlib
import io
import json
import platform
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from .contracts import PlatformError, load_catalog, resolve


def verify(root, output, module_root=None):
    root, output = Path(root), Path(output)
    catalog = load_catalog(root / "catalog")
    resolve(catalog, list(catalog))
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        suite = unittest.defaultTestLoader.discover(str(root / "tests"))
        outcome = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    evidence = {
        "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "kernelTests": {"executed": outcome.testsRun, "failures": len(outcome.failures),
                        "errors": len(outcome.errors), "skipped": len(outcome.skipped),
                        "passed": outcome.testsRun - len(outcome.failures) - len(outcome.errors) - len(outcome.skipped),
                        "successful": outcome.wasSuccessful()},
        "validatedManifests": len(catalog),
        "moduleScaffoldTests": [],
        "limitations": ["synthetic workflows only", "no production auth or provider tests",
                        "metadata composition only", "CI defined but not run on GitHub"],
    }
    failed = not outcome.wasSuccessful() or outcome.testsRun == 0
    if module_root:
        for name in sorted(catalog):
            module = Path(module_root) / ("gh-module-" + name)
            if not (module / "tests").is_dir():
                evidence["moduleScaffoldTests"].append({"module": name, "state": "unrun"})
                failed = True
                continue
            check = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(module / "tests"), "-v"],
                                   capture_output=True, text=True, check=False)
            evidence["moduleScaffoldTests"].append({"module": name, "state": "passed" if check.returncode == 0 else "failed",
                                                   "scope": "scaffold consistency only"})
            failed = failed or check.returncode != 0
    diff = subprocess.run(["git", "-C", str(root), "diff", "--check"], capture_output=True, text=True)
    evidence["diffCheck"] = "passed" if diff.returncode == 0 else "failed"
    failed = failed or diff.returncode != 0
    evidence["overall"] = "failed" if failed else "passed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    if failed:
        raise PlatformError("verification_failed_see_evidence")
    return evidence
