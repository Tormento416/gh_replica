# Evaluation harness and golden datasets

`hyrlink_platform.evals` measures any model against a golden dataset before you spend on fine-tuning or hosting. It has no cloud or model dependency; provider adapters (Bedrock, SageMaker, NVIDIA, local open models) belong outside the backbone and only need to be a callable `provider(input: str) -> Completion`.

## Dataset format

JSONL, one case per line, validated by `CASE_SCHEMA`. Datasets are synthetic only (`"synthetic": true` is required); real or consented data needs a separately reviewed intake path first.

| Field | Meaning |
|---|---|
| `id` | Unique, `[a-z0-9._-]`, up to 64 chars |
| `task` | `extraction`, `classification`, `qa`, `tool_call` |
| `split` | `train`, `dev`, `test`. The same input may not appear in more than one split |
| `input` / `expected` | Prompt text; expected string or object |
| `scorer` | `exact`, `contains`, `json_fields` (optional `fields`), `tool_call`, or `judge` (needs `rubric`, optional `threshold`) |
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
