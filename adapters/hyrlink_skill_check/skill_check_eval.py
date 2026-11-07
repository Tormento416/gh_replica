"""Evaluate hyrlink-pro's production skill-check pipeline (slm_core/skill_check.py) on a node.

The pipeline code is imported at run time from a hyrlink-pro checkout (--hyrlink-root), so the
prompts, rules and regeneration loop under test are exactly the production ones and none of that
private code is copied into this repository. Model calls mirror slm_core/model_loader.py's
_generate_via_server request; a drift guard reads that file's text and refuses to run if the
mirrored sampling parameters or system prompt no longer match.

--reasoning picks how Gemma/Qwen reasoning is requested on every call, as the production switch
does for both tiers: on (enable_thinking true), off (false), auto (no kwarg; server/template default,
today's production behaviour). Reports hold counts, timings and reject reasons, never item text.
Synthetic blueprints only.
"""

import argparse
import asyncio
import importlib
import json
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from hyrlink_platform.contracts import PlatformError, parse_json, validate_instance
from hyrlink_platform.evals import _error_code, _percentile

# Mirrors slm_core/model_loader.py (generation_params and _default_messages). Checked by drift_check().
SYSTEM_PROMPT = "You are a helpful, precise AI assistant."
SAMPLING = {"temperature": 0.2, "top_p": 0.9, "top_k": 40}
# Every key production sets; a new one (min_p, repeat_penalty, seed, ...) is drift the mirror lacks.
PRODUCTION_PARAM_KEYS = {"max_new_tokens", "temperature", "top_p", "top_k"}
PRODUCTION_BODY_KEYS = {"messages", "max_tokens", "temperature", "top_p", "top_k", "stream"}
REASONING = {"on": {"enable_thinking": True}, "off": {"enable_thinking": False}, "auto": None}
_MAX_RESPONSE = 1024 * 1024
_LABEL = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")

BLUEPRINT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "split", "synthetic", "skill", "roles", "tasks", "calibration"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9._-]{0,63}$"},
        "split": {"enum": ["train", "dev", "test"]},
        "synthetic": {"const": True},
        "skill": {"type": "string", "minLength": 2, "maxLength": 80},
        "roles": {"type": "array", "items": {"type": "string", "minLength": 2, "maxLength": 80},
                  "minItems": 0, "maxItems": 3},
        "tasks": {"type": "array", "items": {"type": "string", "minLength": 3, "maxLength": 200},
                  "minItems": 0, "maxItems": 6},
        "calibration": {"type": "string", "maxLength": 2000},
    },
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_blueprints(data):
    if not isinstance(data, bytes):
        raise PlatformError("invalid_dataset")
    rows, ids = [], set()
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        row = parse_json(line)
        validate_instance(row, BLUEPRINT_SCHEMA)
        if row["id"] in ids:
            raise PlatformError("duplicate_case_id")
        ids.add(row["id"])
        rows.append(row)
    if not rows:
        raise PlatformError("invalid_dataset_size")
    # The same skill in two splits would let anything tuned on train be scored on its own content.
    splits = {}
    for row in rows:
        splits.setdefault(row["skill"].strip().lower(), set()).add(row["split"])
    if any(len(s) > 1 for s in splits.values()):
        raise PlatformError("split_leakage")
    return rows


def drift_check(model_loader_source):
    """Return the mirrored values that no longer match production, or [] when in sync."""
    drifted = []
    block = re.search(r"generation_params\s*=\s*\{(.*?)\}", model_loader_source, re.DOTALL)
    for key, want in SAMPLING.items():
        found = re.search(rf'"{key}"\s*:\s*([0-9.]+)', block.group(1)) if block else None
        if not found or float(found.group(1)) != want:
            drifted.append(key)
    if f'"content": "{SYSTEM_PROMPT}"' not in model_loader_source:
        drifted.append("system_prompt")
    if '"chat_template_kwargs"' not in model_loader_source:
        drifted.append("reasoning_switch")
    if block and set(re.findall(r'"([a-z_]+)"\s*:', block.group(1))) != PRODUCTION_PARAM_KEYS:
        drifted.append("generation_params_keys")
    body = re.search(r"body_obj\s*=\s*\{(.*?)\n\s*\}", model_loader_source, re.DOTALL)
    if not body or set(re.findall(r'"([a-z_]+)"\s*:', body.group(1))) != PRODUCTION_BODY_KEYS:
        drifted.append("request_body_keys")
    return drifted


def request_body(prompt, max_tokens, reasoning, model=None):
    body = {"messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "stream": False, **SAMPLING}
    if REASONING[reasoning] is not None:
        body["chat_template_kwargs"] = REASONING[reasoning]
    if model:  # production sends none (llama-server serves one model); Ollama needs it
        body["model"] = model
    return body


def _post(url, body, timeout):
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        data = response.read(_MAX_RESPONSE + 1)
    if len(data) > _MAX_RESPONSE:
        raise ValueError("response_too_large")
    try:
        return parse_json(data)
    except PlatformError as exc:
        raise ValueError("invalid_json_response") from exc


class Tier:
    """One model endpoint plus the per-call metrics the report needs."""

    def __init__(self, name, base_url, reasoning, timeout, post=_post, model=None):
        self.name, self.url, self.reasoning, self.timeout, self.post = name, base_url, reasoning, timeout, post
        self.model = model
        self.calls = []

    def _call(self, prompt, max_tokens):
        started = time.perf_counter()
        try:
            reply = self.post(self.url + "/v1/chat/completions", request_body(prompt, max_tokens, self.reasoning, self.model),
                              self.timeout)
            choice = reply["choices"][0]
            usage = reply.get("usage") or {}
            reasoning_text = choice["message"].get("reasoning_content") or choice["message"].get("reasoning") or ""
            self.calls.append({"seconds": time.perf_counter() - started, "ok": True,
                               "outputTokens": usage.get("completion_tokens", 0),
                               "truncated": choice.get("finish_reason") == "length",
                               "reasoned": bool(reasoning_text.strip()),
                               "emptyContent": not (choice["message"].get("content") or "").strip()})
            return choice["message"].get("content") or ""
        except Exception as exc:
            self.calls.append({"seconds": time.perf_counter() - started, "ok": False, "errorCode": _error_code(exc)})
            raise

    async def __call__(self, prompt, max_tokens):
        return await asyncio.to_thread(self._call, prompt, max_tokens)

    def summary(self):
        ok = [c for c in self.calls if c["ok"]]
        seconds = [c["seconds"] for c in ok]
        tokens = sum(c["outputTokens"] for c in ok)
        return {"calls": len(self.calls), "failedCalls": len(self.calls) - len(ok),
                "errorCodes": dict(Counter(c["errorCode"] for c in self.calls if not c["ok"])),
                "p50CallSeconds": round(_percentile(seconds, 0.5), 3),
                "p95CallSeconds": round(_percentile(seconds, 0.95), 3),
                "outputTokens": tokens, "meanOutputTokens": round(tokens / len(ok), 1) if ok else 0.0,
                "outputTokensPerSecond": round(tokens / sum(seconds), 2) if seconds else 0.0,
                "truncatedCalls": sum(c["truncated"] for c in ok),
                "callsWithReasoning": sum(c["reasoned"] for c in ok),
                "emptyContentCalls": sum(c["emptyContent"] for c in ok)}


def run(skill_check, blueprints, generator, verifier, max_consecutive_errors=5):
    """Run the production pipeline once per blueprint.

    Returns (rows, aborted): aborted is None, or the reason the run stopped early because the model
    servers look down. The rows so far are kept so the report still shows the error codes.
    """
    rows, streak = [], 0
    for bp in blueprints:
        blueprint = skill_check.Blueprint(requested_skill=bp["skill"], canonical_skill=bp["skill"],
                                          match_method="eval", roles=tuple(bp["roles"]), tasks=tuple(bp["tasks"]))
        started = time.perf_counter()
        before = (len(generator.calls), len(verifier.calls))
        try:
            outcome = asyncio.run(skill_check.run_skill_check(
                blueprint, bp["calibration"], generate_items=generator, verify_items=verifier,
                rng=random.Random(bp["id"])))
            complete, failure = True, None
            streak = 0
        except skill_check.SkillCheckUnavailable as exc:
            outcome, complete = exc.outcome, False
            # Classified from what the tiers observed in this check, not from the exception's wording.
            if any(not c["ok"] for c in generator.calls[before[0]:]):
                failure = "generator_call_failed"
            elif any(not c["ok"] for c in verifier.calls[before[1]:]):
                failure = "verifier_call_failed"
            else:
                failure = "check_incomplete"
            streak = streak + 1 if failure.endswith("call_failed") else 0
        records = outcome.records
        rows.append({"id": bp["id"], "split": bp["split"], "complete": complete, "failure": failure,
                     "rounds": outcome.rounds, "seconds": round(time.perf_counter() - started, 3),
                     "generatorCalls": len(generator.calls) - before[0], "verifierCalls": len(verifier.calls) - before[1],
                     "itemsGenerated": len(records),
                     "rejectReasons": dict(Counter(r["reject_reason"] for r in records if r["reject_reason"]))})
        if max_consecutive_errors and streak >= max_consecutive_errors:
            return rows, f"server_unavailable_after_{streak}_consecutive_failed_checks"
    return rows, None


def report(rows, generator, verifier):
    complete = [r for r in rows if r["complete"]]
    seconds = [r["seconds"] for r in rows]
    reasons = Counter()
    for r in rows:
        reasons.update(r["rejectReasons"])
    return {"total": len(rows), "complete": len(complete), "completionRate": round(len(complete) / len(rows), 4),
            "failures": dict(Counter(r["failure"] for r in rows if r["failure"])),
            "meanRounds": round(sum(r["rounds"] for r in rows) / len(rows), 3),
            "firstRoundCompletions": sum(1 for r in complete if r["rounds"] == 1),
            "p50CheckSeconds": round(_percentile(seconds, 0.5), 3), "p95CheckSeconds": round(_percentile(seconds, 0.95), 3),
            "itemsGenerated": sum(r["itemsGenerated"] for r in rows), "rejectReasons": dict(reasons.most_common()),
            "generator": generator.summary(), "verifier": verifier.summary(), "checks": rows}


def _git_commit(root):
    try:
        return subprocess.run(["git", "-c", f"safe.directory={root}", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate hyrlink-pro's skill-check pipeline on a node.")
    parser.add_argument("--hyrlink-root", required=True, type=Path, help="hyrlink-pro checkout to import from")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--generator-url", required=True, help="Gemma llama-server base URL, e.g. http://172.18.0.15:8080")
    parser.add_argument("--verifier-url", required=True, help="Qwen llama-server base URL")
    parser.add_argument("--reasoning", required=True, choices=sorted(REASONING))
    parser.add_argument("--label", required=True)
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--generator-model", help="only for servers that need a model name (Ollama)")
    parser.add_argument("--verifier-model", help="only for servers that need a model name (Ollama)")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", required=True, type=Path, help="new report file; never overwritten")
    args = parser.parse_args(argv)
    try:
        if not _LABEL.fullmatch(args.label) or not 1 <= args.timeout <= 3600:
            raise PlatformError("invalid_argument")
        root = args.hyrlink_root.resolve()
        drifted = drift_check((root / "slm_core/model_loader.py").read_text(encoding="utf-8"))
        if drifted:
            raise PlatformError("production_request_drifted: " + ",".join(drifted))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "openai_compat"))
        from openai_compat_eval import check_base_url
        gen_url = check_base_url(args.generator_url, args.allow_remote)
        ver_url = check_base_url(args.verifier_url, args.allow_remote)
        sys.path.insert(0, str(root))
        skill_check = importlib.import_module("slm_core.skill_check")
        blueprints = [b for b in load_blueprints(args.dataset.read_bytes()) if args.split in (None, b["split"])]
        if not blueprints:
            raise PlatformError("no_cases_selected")
        generator = Tier("generator", gen_url, args.reasoning, args.timeout, model=args.generator_model)
        verifier = Tier("verifier", ver_url, args.reasoning, args.timeout, model=args.verifier_model)
        wall = time.perf_counter()
        rows, aborted = run(skill_check, blueprints, generator, verifier)
        result = report(rows, generator, verifier)
        result.update({"aborted": aborted, "plannedChecks": len(blueprints), "label": args.label, "reasoning": args.reasoning, "wallSeconds": round(time.perf_counter() - wall, 3),
                       "hyrlinkCommit": _git_commit(root), "dataset": args.dataset.name, "split": args.split,
                       "pipeline": {"nMcq": skill_check.N_MCQ, "nShort": skill_check.N_SHORT,
                                    "maxRegenRounds": skill_check.MAX_REGEN_ROUNDS,
                                    "generateMaxTokens": skill_check.GENERATE_MAX_TOKENS},
                       "generatorHost": urllib.parse.urlsplit(gen_url).hostname,
                       "verifierHost": urllib.parse.urlsplit(ver_url).hostname})
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        keys = ("label", "reasoning", "aborted", "total", "complete", "completionRate", "meanRounds", "firstRoundCompletions",
                "p50CheckSeconds", "p95CheckSeconds", "wallSeconds", "failures")
        summary = {k: result[k] for k in keys}
        summary["topRejectReasons"] = dict(list(result["rejectReasons"].items())[:6])
        for tier in ("generator", "verifier"):
            t = result[tier]
            summary[tier] = {k: t[k] for k in ("calls", "failedCalls", "meanOutputTokens", "outputTokensPerSecond",
                                               "truncatedCalls", "callsWithReasoning", "emptyContentCalls", "errorCodes")}
        print(json.dumps(summary, indent=2))
        if aborted:
            sys.exit(f"Eval aborted: {aborted} (partial report written)")
    except (PlatformError, OSError, ValueError, ImportError) as exc:
        sys.exit(f"Eval failed: {exc}")


if __name__ == "__main__":
    main()
