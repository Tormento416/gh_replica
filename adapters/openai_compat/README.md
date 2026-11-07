# OpenAI-compatible eval adapter

Runs `hyrlink_platform.evals` against any server that speaks `/v1/chat/completions`: Ollama, llama.cpp `llama-server`, vLLM. It uses only the standard library, so it needs no installs.

## Safety
- `--base-url` must be a loopback host unless you pass `--allow-remote`. Redirects, embedded credentials and query strings are rejected. No credentials are read or sent.
- Synthetic data only, enforced by the dataset format. Reports hold counts, latency and token totals, never prompts or outputs.

## Single 12 GB GPU: sequential models
Generation finishes for every case before any judge call, so the server loads the model under test, then loads the judge. Ollama evicts the first model when the second does not fit. The first judge call includes that load time, so read `judgeSeconds` accordingly. The model under test is warmed up with an uncounted request, so its latency excludes weight loading.

```sh
uv run --frozen python adapters/openai_compat/openai_compat_eval.py \
  --dataset evals/golden/skill_quiz_50.jsonl --label rtx4070s \
  --model gemma4-e4b --judge-model qwen25-7b \
  --output .local/evals/skill-quiz-rtx4070s.json
```

## Same run on a cloud GPU instance
Copy the repo and models to the instance, serve both models (they fit together on a 24 GB GPU), and run the same command against that server with a new `--label` (for example `g5xlarge`). Keep the dataset, models, quantization, `--max-tokens` and seed identical, otherwise the speed comparison is not valid. Keep the server on loopback and run the adapter on the instance (SSM Session Manager or an SSH tunnel), instead of exposing the port.

## Comparing runs
Accuracy: pass rate by task and the failing case ids. Speed: `p50LatencyMs`, `p95LatencyMs`, `outputTokensPerSecond`, and `generationSeconds`/`judgeSeconds`/`wallSeconds`. Use `hyrlink_platform.evals.compare` on two reports for per-case regressions.
