"""Provider-neutral evaluation harness over synthetic golden datasets (JSONL)."""

import re
import time
from dataclasses import dataclass

from .contracts import PlatformError, digest, parse_json, validate_instance

MAX_CASES = 10000
MAX_FILE = 16 * 1024 * 1024
TASKS = ("extraction", "classification", "qa", "tool_call")
SPLITS = ("train", "dev", "test")
SCORERS = ("exact", "contains", "json_fields", "tool_call", "judge")

CASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "task", "split", "synthetic", "input", "expected", "scorer"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9._-]{0,63}$"},
        "task": {"enum": list(TASKS)},
        "split": {"enum": list(SPLITS)},
        # Real or consented data needs its own reviewed intake path; this format is synthetic only.
        "synthetic": {"const": True},
        "input": {"type": "string", "minLength": 1, "maxLength": 16384},
        "expected": {"type": ["string", "object"]},
        "scorer": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type"],
            "properties": {
                "type": {"enum": list(SCORERS)},
                "fields": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 64},
                "rubric": {"type": "string", "maxLength": 4096},
                "threshold": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "tags": {"type": "array", "items": {"type": "string", "maxLength": 64}, "maxItems": 16},
    },
}


@dataclass(frozen=True)
class Completion:
    """What a provider adapter returns; adapters live outside the backbone."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


def _check_case(case):
    validate_instance(case, CASE_SCHEMA)
    kind, expected = case["scorer"]["type"], case["expected"]
    if kind in ("exact", "contains") and not isinstance(expected, str):
        raise PlatformError("expected_must_be_string")
    if kind in ("json_fields", "tool_call") and not isinstance(expected, dict):
        raise PlatformError("expected_must_be_object")
    if kind == "judge" and "rubric" not in case["scorer"]:
        raise PlatformError("rubric_required")
    fields = case["scorer"].get("fields")
    if fields is not None and (kind != "json_fields" or not set(fields) <= set(expected)):
        raise PlatformError("invalid_scorer_fields")


def load_dataset(data):
    """Parse and validate JSONL bytes; reject duplicate ids and cross-split leakage."""
    if not isinstance(data, bytes) or len(data) > MAX_FILE:
        raise PlatformError("invalid_dataset")
    try:
        lines = [line for line in data.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError as exc:
        raise PlatformError("invalid_dataset") from exc
    if not 1 <= len(lines) <= MAX_CASES:
        raise PlatformError("invalid_dataset_size")
    cases, ids, splits_by_input = [], set(), {}
    for line in lines:
        case = parse_json(line)
        if not isinstance(case, dict):
            raise PlatformError("schema_validation_failed")
        _check_case(case)
        if case["id"] in ids:
            raise PlatformError("duplicate_case_id")
        ids.add(case["id"])
        splits_by_input.setdefault(digest(case["input"]), set()).add(case["split"])
        cases.append(case)
    # An input seen in training must never be scored in dev/test.
    if any(len(splits) > 1 for splits in splits_by_input.values()):
        raise PlatformError("split_leakage")
    return cases


def _object(text):
    try:
        value = parse_json(text)
    except PlatformError:
        return None
    return value if isinstance(value, dict) else None


def score(case, output, judge=None):
    """Return (passed, reason). Reasons are codes, never model output."""
    scorer, expected = case["scorer"], case["expected"]
    kind = scorer["type"]
    if kind == "exact":
        return (output.strip() == expected.strip()), "exact"
    if kind == "contains":
        return (expected.lower() in output.lower()), "contains"
    if kind == "judge":
        if judge is None:
            raise PlatformError("judge_required")
        return (judge(case, output) >= scorer.get("threshold", 0.7)), "judge"
    parsed = _object(output)
    if parsed is None:
        return False, "not_json_object"
    if kind == "tool_call":
        return parsed == expected, "tool_call"
    fields = scorer.get("fields", list(expected))
    return all(f in parsed and parsed[f] == expected[f] for f in fields), "json_fields"


def _p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else 0.0


def run_eval(cases, provider, judge=None, split=None, clock=time.perf_counter):
    """Run provider(input) -> Completion over cases; the report omits inputs and outputs."""
    selected = [c for c in cases if split is None or c["split"] == split]
    if not selected:
        raise PlatformError("no_cases_selected")
    results = []
    for case in selected:
        started = clock()
        try:
            completion = provider(case["input"])
            passed, reason = score(case, completion.text, judge)
            tokens = (completion.input_tokens, completion.output_tokens)
        except PlatformError:
            raise
        except Exception:  # an adapter failure is a failed case, not a crashed run
            passed, reason, tokens = False, "provider_error", (0, 0)
        results.append({"id": case["id"], "task": case["task"], "split": case["split"], "passed": passed,
                        "reason": reason, "latencyMs": round((clock() - started) * 1000, 3),
                        "inputTokens": tokens[0], "outputTokens": tokens[1]})
    by_task = {}
    for r in results:
        bucket = by_task.setdefault(r["task"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += r["passed"]
    passed = sum(r["passed"] for r in results)
    return {"total": len(results), "passed": passed, "passRate": round(passed / len(results), 4),
            "byTask": by_task, "p95LatencyMs": _p95([r["latencyMs"] for r in results]),
            "inputTokens": sum(r["inputTokens"] for r in results),
            "outputTokens": sum(r["outputTokens"] for r in results),
            "failures": [r["id"] for r in results if not r["passed"]], "results": results}


def compare(baseline, candidate):
    """Contrast two reports over the same cases, e.g. base model vs fine-tune."""
    before = {r["id"]: r["passed"] for r in baseline["results"]}
    after = {r["id"]: r["passed"] for r in candidate["results"]}
    if set(before) != set(after):
        raise PlatformError("case_sets_differ")
    return {"passRateDelta": round(candidate["passRate"] - baseline["passRate"], 4),
            "regressions": sorted(i for i in before if before[i] and not after[i]),
            "improvements": sorted(i for i in before if not before[i] and after[i])}
