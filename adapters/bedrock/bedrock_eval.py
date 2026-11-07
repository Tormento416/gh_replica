"""Amazon Bedrock (Converse API) provider and judge adapters for hyrlink_platform.evals.

Optional tooling: boto3 is not a backbone dependency. Install adapters/bedrock/requirements.txt.
Running this spends AWS credits; nothing here runs without an explicit command.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from hyrlink_platform.contracts import PlatformError, parse_json
from hyrlink_platform.evals import (JUDGE_SYSTEM, Completion, judge_prompt, load_dataset, parse_judge_score,
                                    needs_judge, run_eval, system_prompt)

_MODEL_ID = re.compile(r"[A-Za-z0-9._:/-]{1,2048}\Z")
_REGION = re.compile(r"[a-z]{2}(?:-[a-z]+)+-\d\Z")

def make_client(region, profile=None):
    """Create a bedrock-runtime client with bounded adaptive retries for throttling."""
    if not isinstance(region, str) or not _REGION.fullmatch(region):
        raise PlatformError("invalid_region")
    import boto3
    from botocore.config import Config
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("bedrock-runtime", config=Config(
        retries={"mode": "adaptive", "max_attempts": 6}, read_timeout=60, connect_timeout=5))


def _converse(client, model_id, system, prompt, max_tokens, temperature):
    response = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature})
    blocks = response["output"]["message"]["content"]
    text = "".join(b["text"] for b in blocks if "text" in b)
    usage = response.get("usage", {})
    return Completion(text, usage.get("inputTokens", 0), usage.get("outputTokens", 0),
                      response.get("stopReason") == "max_tokens")


def _check_model(model_id):
    if not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id):
        raise PlatformError("invalid_model_id")


def make_provider(client, model_id, case_by_input, max_tokens=512, temperature=0.0):
    """Return provider(input) -> Completion. The case supplies the task prompt and its instructions."""
    _check_model(model_id)

    def provider(text):
        system = system_prompt(case_by_input[text])
        return _converse(client, model_id, system, text, max_tokens, temperature)
    return provider


def make_judge(client, model_id, max_tokens=64):
    """Return judge(case, output) -> score in [0, 1] using a separate, fixed-temperature model call."""
    _check_model(model_id)

    def judge(case, output):
        reply = _converse(client, model_id, JUDGE_SYSTEM, judge_prompt(case, output), max_tokens, 0.0).text
        return parse_judge_score(reply)
    return judge


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate a Bedrock model on a golden dataset.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--model", required=True, help="Bedrock model id or inference profile id")
    parser.add_argument("--region", required=True)
    parser.add_argument("--judge-model", help="required when the dataset has judge-scored cases")
    parser.add_argument("--split", choices=("train", "dev", "test"))
    parser.add_argument("--profile")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--output", required=True, type=Path, help="new report file; never overwritten")
    args = parser.parse_args(argv)
    try:
        cases = load_dataset(args.dataset.read_bytes())
        selected = [c for c in cases if args.split in (None, c["split"])]
        if needs_judge(selected) and not args.judge_model:
            raise PlatformError("judge_model_required")
        if not 1 <= args.max_tokens <= 4096:
            raise PlatformError("invalid_max_tokens")
        client = make_client(args.region, args.profile)
        provider = make_provider(client, args.model, {c["input"]: c for c in cases}, args.max_tokens)
        judge = make_judge(client, args.judge_model) if args.judge_model else None
        report = run_eval(cases, provider, judge, args.split)
        if all(r["reason"] in ("provider_error", "judge_error") for r in report["results"]):
            raise PlatformError("all_cases_provider_error: check credentials, region and model access")
        report.update({"model": args.model, "judgeModel": args.judge_model, "region": args.region,
                       "split": args.split})
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(json.dumps({k: report[k] for k in ("model", "total", "passed", "passRate", "p95LatencyMs",
                                                  "outputTokensPerSecond", "wallSeconds", "inputTokens", "outputTokens", "failures")}, indent=2))
    except (PlatformError, OSError) as exc:
        sys.exit(f"Eval failed: {exc}")


if __name__ == "__main__":
    main()
