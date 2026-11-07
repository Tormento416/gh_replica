import json
import unittest
from pathlib import Path

from hyrlink_platform.contracts import PlatformError
from hyrlink_platform.evals import Completion, compare, load_dataset, run_eval, score

SEED = Path(__file__).resolve().parents[1] / "evals/golden/synthetic_seed.jsonl"


def case(**overrides):
    base = {"id": "c1", "task": "qa", "split": "dev", "synthetic": True, "input": "q",
            "expected": "a", "scorer": {"type": "exact"}}
    base.update(overrides)
    return base


def dataset(*cases):
    return "\n".join(json.dumps(c) for c in cases).encode()


class DatasetTests(unittest.TestCase):
    def test_seed_dataset_is_valid(self):
        cases = load_dataset(SEED.read_bytes())
        self.assertEqual({c["split"] for c in cases}, {"train", "dev", "test"})

    def test_rejects_malformed_cases(self):
        bad = [
            case(synthetic=False),
            case(id="Bad ID"),
            case(extra=1),
            case(scorer={"type": "unknown"}),
            case(scorer={"type": "json_fields"}),                 # expected must be an object
            case(expected={"a": 1}, scorer={"type": "exact"}),
            case(scorer={"type": "judge"}),                       # rubric required
            case(expected={"a": 1}, scorer={"type": "json_fields", "fields": ["b"]}),
            case(scorer={"type": "exact", "fields": ["a"]}),
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(PlatformError):
                load_dataset(dataset(item))

    def test_rejects_duplicates_empty_and_non_json(self):
        for data in (dataset(case(), case()), b"", b"\n\n", b"{", b'{"id":"x","id":"y"}', b"[]", b"\xff"):
            with self.subTest(data=data), self.assertRaises(PlatformError):
                load_dataset(data)

    def test_rejects_split_leakage(self):
        with self.assertRaises(PlatformError):
            load_dataset(dataset(case(id="a", split="train"), case(id="b", split="test")))
        load_dataset(dataset(case(id="a", split="train"), case(id="b", split="train")))


class ScoringTests(unittest.TestCase):
    def test_scorers(self):
        self.assertTrue(score(case(), " a ")[0])
        self.assertFalse(score(case(), "b")[0])
        self.assertTrue(score(case(expected="Five", scorer={"type": "contains"}), "it is FIVE days")[0])
        fields = case(expected={"a": 1, "b": 2}, scorer={"type": "json_fields", "fields": ["a"]})
        self.assertTrue(score(fields, '{"a":1,"b":9}')[0])
        self.assertFalse(score(fields, '{"a":"1"}')[0])
        self.assertEqual(score(fields, "not json"), (False, "not_json_object"))
        tool = case(expected={"tool": "t", "arguments": {"x": 1}}, scorer={"type": "tool_call"})
        self.assertTrue(score(tool, '{"tool":"t","arguments":{"x":1}}')[0])
        self.assertFalse(score(tool, '{"tool":"t","arguments":{"x":1,"extra":2}}')[0])

    def test_judge_requires_injected_callable(self):
        judged = case(scorer={"type": "judge", "rubric": "r", "threshold": 0.5})
        with self.assertRaises(PlatformError):
            score(judged, "x")
        self.assertTrue(score(judged, "x", judge=lambda c, o: 0.5)[0])
        self.assertFalse(score(judged, "x", judge=lambda c, o: 0.4)[0])


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.cases = load_dataset(SEED.read_bytes())
        self.oracle = {c["input"]: c["expected"] for c in self.cases}

    def provider(self, text):
        expected = self.oracle[text]
        return Completion(expected if isinstance(expected, str) else json.dumps(expected), 10, 5)

    def test_oracle_passes_and_report_omits_content(self):
        report = run_eval(self.cases, self.provider, judge=lambda c, o: 1.0)
        self.assertEqual((report["total"], report["passRate"], report["failures"]), (6, 1.0, []))
        self.assertEqual((report["inputTokens"], report["outputTokens"]), (60, 30))
        self.assertNotIn("Jordan", json.dumps(report))

    def test_split_filter_and_provider_errors_fail_closed_per_case(self):
        def broken(_):
            raise RuntimeError("secret detail Jordan Lee")
        report = run_eval(self.cases, broken, judge=lambda c, o: 1.0, split="test")
        self.assertEqual(report["total"], 2)
        self.assertEqual({r["reason"] for r in report["results"]}, {"provider_error"})
        self.assertNotIn("secret", json.dumps(report))
        with self.assertRaises(PlatformError):
            run_eval([c for c in self.cases if c["split"] == "dev"], broken, split="test")

    def test_compare_reports_regressions(self):
        judge = lambda c, o: 1.0
        good = run_eval(self.cases, self.provider, judge)
        worse = run_eval(self.cases, lambda t: Completion("wrong"), judge)
        delta = compare(good, worse)
        self.assertLess(delta["passRateDelta"], 0)
        self.assertEqual(len(delta["regressions"]), 5)  # the judge case still passes
        with self.assertRaises(PlatformError):
            compare(good, run_eval(self.cases, self.provider, judge, split="dev"))


if __name__ == "__main__":
    unittest.main()
