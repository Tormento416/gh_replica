"""OpenAI-compatible chat adapter (Ollama, llama.cpp server, vLLM) for hyrlink_platform.evals.

Standard library only. Servers are expected on loopback; a remote host needs --allow-remote and
carries synthetic eval data only. No credentials are read or sent.
"""

import argparse
import ipaddress
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from hyrlink_platform.contracts import PlatformError, parse_json
from hyrlink_platform.evals import (JUDGE_SYSTEM, Completion, judge_prompt, load_dataset, parse_judge_score,
                                    run_eval, system_prompt)

_MODEL = re.compile(r"[A-Za-z0-9._:/@-]{1,256}\Z")
_LABEL = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_MAX_RESPONSE = 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_base_url(url, allow_remote=False):
    parts = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if parts is None or parts.scheme not in ("http", "https") or not parts.hostname or parts.query \
            or parts.fragment or parts.username or parts.password:
        raise PlatformError("invalid_base_url")
    if not allow_remote and not _is_loopback(parts.hostname):
        raise PlatformError("remote_host_requires_allow_remote")
    return url.rstrip("/")


def _post(url, body, timeout):
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        data = response.read(_MAX_RESPONSE + 1)
    if len(data) > _MAX_RESPONSE:
        raise ValueError("response_too_large")
    return parse_json(data)


def _chat(base_url, model, system, prompt, max_tokens, timeout, post=_post):
    reply = post(base_url + "/chat/completions", {
        "model": model, "temperature": 0, "seed": 0, "max_tokens": max_tokens, "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}, timeout)
    usage = reply.get("usage") or {}
    choice = reply["choices"][0]
    return Completion(choice["message"]["content"] or "", usage.get("prompt_tokens", 0),
                      usage.get("completion_tokens", 0), choice.get("finish_reason") == "length")


def _check_model(model):
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise PlatformError("invalid_model")


def make_provider(base_url, model, case_by_input, max_tokens=512, timeout=300, post=_post):
    _check_model(model)
    return lambda text: _chat(base_url, model, system_prompt(case_by_input[text]), text, max_tokens, timeout, post)


def make_judge(base_url, model, max_tokens=64, timeout=300, post=_post):
    _check_model(model)
    return lambda case, output: parse_judge_score(
        _chat(base_url, model, JUDGE_SYSTEM, judge_prompt(case, output), max_tokens, timeout, post).text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate an OpenAI-compatible server on a golden dataset.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--judge-base-url", help="defaults to --base-url")
    parser.add_argument("--judge-model", help="required when the dataset has judge-scored cases")
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--label", required=True, help="hardware/run label recorded in the report, e.g. rtx4070s")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-warmup", action="store_true", help="skip the uncounted model-load request")
    parser.add_argument("--output", required=True, type=Path, help="new report file; never overwritten")
    args = parser.parse_args(argv)
    try:
        if not _LABEL.fullmatch(args.label) or not 1 <= args.max_tokens <= 4096 or not 1 <= args.timeout <= 3600:
            raise PlatformError("invalid_argument")
        cases = load_dataset(args.dataset.read_bytes())
        selected = [c for c in cases if args.split in (None, c["split"])]
        if any(c["scorer"]["type"] == "judge" for c in selected) and not args.judge_model:
            raise PlatformError("judge_model_required")
        base = check_base_url(args.base_url, args.allow_remote)
        judge_base = check_base_url(args.judge_base_url or args.base_url, args.allow_remote)
        provider = make_provider(base, args.model, {c["input"]: c for c in cases}, args.max_tokens, args.timeout)
        judge = make_judge(judge_base, args.judge_model, timeout=args.timeout) if args.judge_model else None
        if not args.no_warmup:  # first request loads weights; keep that out of the latency numbers
            _chat(base, args.model, "Reply with OK.", "ping", 4, args.timeout)
        report = run_eval(cases, provider, judge, args.split)
        if all(r["reason"] in ("provider_error", "judge_error") for r in report["results"]):
            raise PlatformError("all_cases_failed: check the server, model name and base URL")
        report.update({"label": args.label, "model": args.model, "judgeModel": args.judge_model,
                       "host": urllib.parse.urlsplit(base).hostname, "split": args.split})
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        keys = ("label", "model", "total", "passed", "passRate", "p50LatencyMs", "p95LatencyMs",
                "outputTokensPerSecond", "generationSeconds", "judgeSeconds", "wallSeconds", "truncatedCases", "failures")
        print(json.dumps({k: report[k] for k in keys}, indent=2))
    except (PlatformError, OSError, ValueError) as exc:
        sys.exit(f"Eval failed: {exc}")


if __name__ == "__main__":
    main()
