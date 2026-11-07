import importlib.util
import json
import unittest
from pathlib import Path

from hyrlink_platform.contracts import PlatformError
from hyrlink_platform.evals import load_dataset, run_eval

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("openai_compat_eval", ROOT / "adapters/openai_compat/openai_compat_eval.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def reply(text, prompt=5, completion=2):
    return {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


class OpenAICompatTests(unittest.TestCase):
    def test_base_url_policy(self):
        for url in ("http://127.0.0.1:11434/v1/", "http://localhost:8080/v1", "http://[::1]:8080/v1"):
            self.assertFalse(adapter.check_base_url(url).endswith("/"))
        for url in ("http://10.0.0.5:8080/v1", "http://example.com/v1"):
            with self.subTest(url=url), self.assertRaises(PlatformError):
                adapter.check_base_url(url)
            adapter.check_base_url(url, allow_remote=True)
        for url in ("file:///etc/passwd", "ftp://127.0.0.1", "http://user:pw@127.0.0.1/v1", "http://127.0.0.1/v1?x=1", "", None):
            with self.subTest(url=url), self.assertRaises(PlatformError):
                adapter.check_base_url(url, allow_remote=True)

    def test_request_shape_and_usage(self):
        seen = []
        post = lambda url, body, timeout: seen.append((url, body)) or reply("hi")
        case = {"task": "classification", "instructions": "Labels: a, b."}
        completion = adapter.make_provider("http://127.0.0.1:1/v1", "gemma:e4b", {"q": case}, 33, post=post)("q")
        self.assertEqual((completion.text, completion.input_tokens, completion.output_tokens), ("hi", 5, 2))
        url, body = seen[0]
        self.assertEqual(url, "http://127.0.0.1:1/v1/chat/completions")
        self.assertEqual((body["temperature"], body["seed"], body["max_tokens"], body["model"]), (0, 0, 33, "gemma:e4b"))
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        self.assertTrue(body["messages"][0]["content"].endswith("Labels: a, b."))

    def test_full_run_two_phases_with_fake_server(self):
        cases = load_dataset((ROOT / "evals/golden/synthetic_seed.jsonl").read_bytes())
        oracle = {c["input"]: c["expected"] for c in cases}
        order = []

        def post(url, body, timeout):
            if body["model"] == "judge":
                order.append("judge")
                return reply('{"score": 1}')
            order.append("gen")
            expected = oracle[body["messages"][1]["content"]]
            return reply(expected if isinstance(expected, str) else json.dumps(expected))
        by_input = {c["input"]: c for c in cases}
        report = run_eval(cases, adapter.make_provider("http://127.0.0.1:1/v1", "gen", by_input, post=post),
                          adapter.make_judge("http://127.0.0.1:1/v1", "judge", post=post))
        self.assertEqual(report["passRate"], 1.0)
        self.assertEqual(order[:len(cases)], ["gen"] * len(cases))

    def test_truncation_is_reported(self):
        post = lambda url, body, timeout: {"choices": [{"message": {"content": "{"}, "finish_reason": "length"}],
                                           "usage": {"completion_tokens": 9}}
        provider = adapter.make_provider("http://127.0.0.1:1/v1", "m", {"q": {"task": "qa"}}, post=post)
        self.assertTrue(provider("q").truncated)
        case = {"id": "a", "task": "qa", "split": "dev", "synthetic": True, "input": "q", "expected": "x",
                "scorer": {"type": "exact"}}
        self.assertEqual(run_eval([case], provider)["truncatedCases"], 1)

    def test_structured_sends_schema_only_for_quiz_cases(self):
        seen = []
        post = lambda url, body, timeout: seen.append(body) or reply("{}")
        quiz = {"task": "generation", "expected": {"questions": 3}, "scorer": {"type": "quiz_json"}}
        other = {"task": "qa", "expected": "x", "scorer": {"type": "exact"}}
        cases = {"q": quiz, "o": other}
        adapter.make_provider("http://127.0.0.1:1/v1", "m", cases, structured=True, post=post)("q")
        adapter.make_provider("http://127.0.0.1:1/v1", "m", cases, structured=True, post=post)("o")
        adapter.make_provider("http://127.0.0.1:1/v1", "m", cases, structured=False, post=post)("q")
        fmt = seen[0]["response_format"]
        self.assertEqual(fmt["type"], "json_schema")
        questions = fmt["json_schema"]["schema"]["properties"]["questions"]
        self.assertEqual((questions["minItems"], questions["maxItems"]), (3, 3))
        self.assertNotIn("response_format", seen[1])
        self.assertNotIn("response_format", seen[2])

    def test_invalid_model_rejected(self):
        for model in ("", "a b", "x;y", None):
            with self.subTest(model=model), self.assertRaises(PlatformError):
                adapter.make_provider("http://127.0.0.1:1/v1", model, {})


if __name__ == "__main__":
    unittest.main()
