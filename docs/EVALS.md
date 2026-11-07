# Evaluation harness and golden datasets

`hyrlink_platform.evals` measures any model against a golden dataset before you spend on fine-tuning or hosting. It has no cloud or model dependency; provider adapters (Bedrock, SageMaker, NVIDIA, local open models) belong outside the backbone and only need to be a callable `provider(input: str) -> Completion`.

## Dataset format

JSONL, one case per line, validated by `CASE_SCHEMA`. Datasets are synthetic only (`"synthetic": true` is required); real or consented data needs a separately reviewed intake path first.

| Field | Meaning |
|---|---|
| `id` | Unique, `[a-z0-9._-]`, up to 64 chars |
| `task` | `extraction`, `classification`, `qa`, `tool_call`, `generation` |
| `split` | `train`, `dev`, `test`. The same input may not appear in more than one split |
| `input` / `expected` | Prompt text; expected string or object |
| `instructions` | Optional task contract shown to the model (schema, labels, tool list) |
| `scorer` | `exact`, `contains`, `json_fields` (optional `fields`), `tool_call`, or `judge` (needs `rubric`, optional `threshold`), or `quiz_json` (expected `{"questions": n}`; checks structure, then judges with an optional `rubric`) |
| `tags` | Optional labels such as the module name |

See `evals/golden/synthetic_seed.jsonl`.

## Use

```sh
uv run --frozen hyrlink eval-validate --dataset evals/golden/synthetic_seed.jsonl
```

```python
from hyrlink_platform.evals import load_dataset, run_eval, compare, Completion
cases = load_dataset(path.read_bytes())
base = run_eval(cases, base_model_adapter, judge=judge_adapter, split="test")
tuned = run_eval(cases, tuned_model_adapter, judge=judge_adapter, split="test")
compare(base, tuned)  # pass-rate delta, regressions, improvements
```

Reports contain pass rate, per-task counts, p95 latency, token totals and failing case ids, never inputs or outputs. A provider exception fails that case with `provider_error`. A fine-tune is justified only when `test` pass rate stays below your target after prompt and few-shot work. Never tune on `dev` or `test` cases, and hold the `test` split out of every training export.

## Speed metrics and two-phase scoring

`run_eval` finishes generation for every case before judge scoring. The report adds `p50LatencyMs`, `p95LatencyMs` (generation only), `outputTokensPerSecond`, `generationSeconds`, `judgeSeconds` and `wallSeconds`, so the same dataset can compare hardware as well as accuracy. Adapters: `adapters/bedrock` (Converse API) and `adapters/openai_compat` (Ollama, llama.cpp, vLLM).

Datasets: `synthetic_seed.jsonl` (format example), `core_hr_50.jsonl` (extraction, classification, QA, tool calls, summaries), `skill_quiz_50.jsonl` and `skill_quiz_100.jsonl` (skill-validation quiz generation; the 100-case set is 30 train / 30 dev / 40 test, varies question count and constraints, and checks two constraints deterministically).

## Failure diagnosis

Each failed case carries `reason` (`provider_error`, `judge_error`, or a scorer reason) and an `errorCode` such as `http_503` or `connectionrefusederror`; the report totals them in `errorCodes`. Codes never include server messages. A run aborts with `server_unavailable_after_5_consecutive_errors_...` when five generation calls fail in a row, instead of spending minutes on a dead server. `quiz_json` scorers may also set `forbid` (substrings no option may contain) and `max_words` (per-question word limit).

## Production skill-check pipeline

`adapters/hyrlink_skill_check/skill_check_eval.py` runs hyrlink-pro's real `slm_core/skill_check.py` (generate, deterministic checks, independent Qwen solve, bounded regeneration, fail closed) against a node's Gemma and Qwen servers. It imports that module from `--hyrlink-root` at run time, so no product code lives here. Model calls mirror `model_loader._generate_via_server`; `drift_check` refuses to run if the mirrored sampling values, system prompt or request keys no longer match. `--reasoning on|off|auto` sets `chat_template_kwargs.enable_thinking` on both tiers (auto sends nothing).

Inputs are `evals/golden/skill_check_blueprints_100.jsonl`: 25 skills by 4 synthetic candidate contexts, with each skill in exactly one split; a quarter have no roles or tasks, exercising the uncanonical path. Reports hold completion rate, rounds, reject-reason counts, per-check latency and per-tier call metrics (tokens, truncation, reasoning, empty content, error codes), never item text. A run that stops because the servers look down still writes a partial report.

On a node, `adapters/hyrlink_skill_check/node_run.sh LABEL HYRLINK_ROOT DATASET OUTPUT_DIR [MODES]` runs each mode, resolves container IPs by name, snapshots the server flags (secrets masked) and marks a mode INVALID if a model container restarted.
