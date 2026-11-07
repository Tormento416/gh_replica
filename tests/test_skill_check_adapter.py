import importlib.util
import json
import types
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from hyrlink_platform.contracts import PlatformError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill_check_eval", ROOT / "adapters/hyrlink_skill_check/skill_check_eval.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

PRODUCTION_SNIPPET = '''
generation_params = {
    "max_new_tokens": 512,
    "temperature": 0.2,
    "top_p": 0.9,
    "top_k": 40,
}
def _default_messages(p):
    return [{"role": "system", "content": "You are a helpful, precise AI assistant."}]
body_obj = {
    "messages": messages,
    "max_tokens": max_tokens,
    "temperature": 0.2,
    "top_p": 0.9,
    "top_k": 40,
    "stream": False,
}
body_obj["chat_template_kwargs"] = {"enable_thinking": False}
'''


def fake_skill_check(fail_ids=()):
    """Stand-in for slm_core.skill_check with the same public surface the adapter uses."""
    mod = types.SimpleNamespace(N_MCQ=3, N_SHORT=2, MAX_REGEN_ROUNDS=2, GENERATE_MAX_TOKENS=1000)

    @dataclass(frozen=True)
    class Blueprint:
        requested_skill: str
        canonical_skill: str
        match_method: str
        roles: tuple
        tasks: tuple

    @dataclass
    class Outcome:
        rounds: int = 0
        records: list = field(default_factory=list)

    class SkillCheckUnavailable(Exception):
        def __init__(self, reason, outcome):
            super().__init__(reason)
            self.reason, self.outcome = reason, outcome

    async def run_skill_check(blueprint, calibration, *, generate_items, verify_items, rng=None):
        outcome = Outcome(rounds=1)
        try:
            await generate_items("gen prompt", 1000)
        except Exception as exc:
            raise SkillCheckUnavailable(f"generator call failed: {exc}", outcome) from exc
        await verify_items("verify prompt", 320)
        outcome.records = [{"reject_reason": None}, {"reject_reason": "verifier_disagreed"}]
        if blueprint.requested_skill in fail_ids:
            raise SkillCheckUnavailable("only 2/3 MCQ survived", outcome)
        return outcome

    mod.Blueprint, mod.SkillCheckUnavailable, mod.run_skill_check = Blueprint, SkillCheckUnavailable, run_skill_check
    return mod


def blueprint(i, **kw):
    row = {"id": f"bp-{i}", "split": "dev", "synthetic": True, "skill": f"skill{i}", "roles": ["Analyst"],
           "tasks": ["Build reports"], "calibration": "Years of experience: 3"}
    row.update(kw)
    return row


def reply(content="{}", reasoning="", finish="stop", tokens=10):
    return {"choices": [{"message": {"content": content, "reasoning_content": reasoning}, "finish_reason": finish}],
            "usage": {"completion_tokens": tokens}}


class SkillCheckAdapterTests(unittest.TestCase):
    def test_request_body_mirrors_production_and_sets_reasoning_mode(self):
        on, off, auto = (adapter.request_body("p", 1000, m) for m in ("on", "off", "auto"))
        self.assertEqual(on["chat_template_kwargs"], {"enable_thinking": True})
        self.assertEqual(off["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn("chat_template_kwargs", auto)
        self.assertEqual((auto["temperature"], auto["top_p"], auto["top_k"], auto["max_tokens"]), (0.2, 0.9, 40, 1000))
        self.assertEqual(auto["messages"][0], {"role": "system", "content": "You are a helpful, precise AI assistant."})

    def test_drift_check(self):
        self.assertEqual(adapter.drift_check(PRODUCTION_SNIPPET), [])
        self.assertEqual(adapter.drift_check(PRODUCTION_SNIPPET.replace('"top_k": 40', '"top_k": 50')), ["top_k"])
        self.assertIn("system_prompt", adapter.drift_check(PRODUCTION_SNIPPET.replace("precise", "concise")))
        self.assertEqual(len(adapter.drift_check("nothing here")), 6)

    def test_blueprint_validation(self):
        good = json.dumps(blueprint(1)).encode()
        self.assertEqual(len(adapter.load_blueprints(good)), 1)
        for bad in (blueprint(1, synthetic=False), blueprint(1, extra=1), blueprint(1, roles=["a"] * 4), blueprint(1, id="Bad")):
            with self.subTest(bad=bad), self.assertRaises(PlatformError):
                adapter.load_blueprints(json.dumps(bad).encode())
        with self.assertRaises(PlatformError):
            adapter.load_blueprints((json.dumps(blueprint(1)) + "\n" + json.dumps(blueprint(1))).encode())

    def test_same_skill_in_two_splits_is_leakage(self):
        rows = [blueprint(1, skill="SQL", split="train"), blueprint(2, skill="sql ", split="test")]
        with self.assertRaises(PlatformError):
            adapter.load_blueprints("\n".join(json.dumps(r) for r in rows).encode())
        rows[1]["split"] = "train"
        self.assertEqual(len(adapter.load_blueprints("\n".join(json.dumps(r) for r in rows).encode())), 2)

    def test_tier_metrics(self):
        replies = iter([reply("x", reasoning="thinking...", tokens=40), reply("", finish="length", tokens=1000)])
        tier = adapter.Tier("generator", "http://127.0.0.1:1", "on", 5, post=lambda url, body, t: next(replies))
        tier._call("p", 1000)
        tier._call("p", 1000)
        s = tier.summary()
        self.assertEqual((s["calls"], s["callsWithReasoning"], s["truncatedCalls"], s["emptyContentCalls"]), (2, 1, 1, 1))
        self.assertEqual(s["meanOutputTokens"], 520.0)

    def test_run_and_report_classify_outcomes(self):
        sc = fake_skill_check(fail_ids={"skill2"})
        gen = adapter.Tier("generator", "http://127.0.0.1:1", "off", 5, post=lambda *a: reply())
        ver = adapter.Tier("verifier", "http://127.0.0.1:2", "off", 5, post=lambda *a: reply())
        rows, aborted = adapter.run(sc, [blueprint(1), blueprint(2)], gen, ver)
        self.assertIsNone(aborted)
        result = adapter.report(rows, gen, ver)
        self.assertEqual((result["total"], result["complete"], result["failures"]), (2, 1, {"check_incomplete": 1}))
        self.assertEqual(result["rejectReasons"], {"verifier_disagreed": 2})
        self.assertEqual(result["generator"]["calls"], 2)
        self.assertNotIn("gen prompt", json.dumps(result))

    def test_dead_server_stops_the_run(self):
        sc = fake_skill_check()
        def down(*a):
            raise ConnectionRefusedError("down")
        gen = adapter.Tier("generator", "http://127.0.0.1:1", "auto", 5, post=down)
        ver = adapter.Tier("verifier", "http://127.0.0.1:2", "auto", 5, post=lambda *a: reply())
        rows, aborted = adapter.run(sc, [blueprint(i) for i in range(10)], gen, ver)
        self.assertEqual(len(rows), 5)
        self.assertTrue(aborted.startswith("server_unavailable"))
        self.assertEqual({r["failure"] for r in rows}, {"generator_call_failed"})
        self.assertEqual(len(gen.calls), 5)
        self.assertEqual(gen.summary()["errorCodes"], {"connectionrefusederror": 5})


if __name__ == "__main__":
    unittest.main()
