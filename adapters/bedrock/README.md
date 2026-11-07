# Bedrock eval adapter

Runs `hyrlink_platform.evals` against any Bedrock model through the Converse API, so one adapter covers Nova, Llama, Qwen and other Bedrock-hosted models. It is optional tooling: boto3 is not in the backbone `pyproject.toml` or `uv.lock`.

```sh
uv run --frozen --with-requirements adapters/bedrock/requirements.txt \
  python adapters/bedrock/bedrock_eval.py \
  --dataset evals/golden/synthetic_seed.jsonl --split dev \
  --model <model-or-inference-profile-id> --judge-model <model-id> \
  --region <region> --output .local/evals/<run-name>.json
```

- **Cost:** every case is one billed call, plus one more per judge-scored case. Start with `--split dev`. Check current pricing and enable model access in the Bedrock console first; some models need an inference profile id.
- **Reports** hold pass rate, latency, token totals and failing case ids, never prompts or outputs. The output file is created exclusively and an existing file is never overwritten. Use `evals.compare` on two reports' cases to contrast models.
- **Judge:** use a different, stronger model than the one under test. Candidate text is passed as delimited untrusted data, and a malformed score counts as a failed case.
- **Credentials** come from the standard AWS chain (`--profile` optional). Do not put credentials in files.
- Synthetic data only; the dataset format enforces it.
