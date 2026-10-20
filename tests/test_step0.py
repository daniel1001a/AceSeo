"""Offline tests for Step 0 tooling (PLAN.md 6.3, 8 step 0a; design/w5-test-list.md W5-10)."""

import ast
import copy
import io
import os
import socket
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

from step0 import cost, dryrun, request_builder
from step0.canonical import StrictJSONError, canonical_bytes, sha256_hex, strict_load_path, strict_loads

DATA = dryrun.DATA_DIR
STEP0_DIR = os.path.dirname(dryrun.__file__)
SENTINEL = "sk-SENTINEL-must-never-appear"


def load(name):
    return strict_load_path(os.path.join(DATA, name))


def build(opt_in=()):
    prompts = request_builder.load_prompts(load("prompts.json"))
    return request_builder.build_plan(load("engines.json"), prompts, 3, opt_in)


def run_quiet(**kw):
    buf = io.StringIO()
    code = dryrun.run(stdout=buf, **kw)
    return code, buf.getvalue()


def all_bytes_under(path):
    chunks = []
    for root, _, files in os.walk(path):
        for name in sorted(files):
            with open(os.path.join(root, name), "rb") as f:
                chunks.append(f.read())
    return b"".join(chunks)


class _NoNetwork:
    """Any socket use raises, so a hidden network call fails the test."""

    def __enter__(self):
        def refuse(*a, **k):
            raise AssertionError("network access attempted")
        self._patches = [mock.patch.object(socket, "socket", refuse),
                         mock.patch.object(socket, "create_connection", refuse),
                         mock.patch.object(socket, "getaddrinfo", refuse)]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class CanonicalTest(unittest.TestCase):
    def test_rejects_float_nan_and_duplicate_keys(self):
        for text in ('{"a": 1.5}', '{"a": NaN}', '{"a": 1, "a": 2}'):
            with self.assertRaises(StrictJSONError):
                strict_loads(text)

    def test_canonical_bytes_sorted_compact_utf8(self):
        self.assertEqual(canonical_bytes({"b": 1, "a": "營運"}), '{"a":"營運","b":1}'.encode("utf-8"))


class RequestBuilderTest(unittest.TestCase):
    def test_default_matrix_is_60_slots_and_90_with_perplexity(self):
        plan, _ = build()
        self.assertEqual(len(plan["slots"]), 60)
        self.assertEqual({s["engine"] for s in plan["slots"]}, {"anthropic", "openai"})
        plan, _ = build(["perplexity"])
        self.assertEqual(len(plan["slots"]), 90)

    def test_byte_identical_across_builds(self):
        a_plan, a_files = build(["perplexity"])
        b_plan, b_files = build(["perplexity"])
        self.assertEqual(canonical_bytes(a_plan), canonical_bytes(b_plan))
        self.assertEqual(a_files, b_files)
        for digest, body in a_files.items():
            self.assertEqual(sha256_hex(body), digest)

    def test_bodies_match_documented_shapes(self):
        prompts = request_builder.load_prompts(load("prompts.json"))
        p = prompts[0]
        engines = {e["engine"]: e for e in load("engines.json")["engines"]}
        self.assertEqual(request_builder.build_request(engines["openai"], p)["body"], {
            "model": "gpt-5-mini", "tools": [{"type": "web_search"}], "input": p["text"]})
        self.assertEqual(request_builder.build_request(engines["anthropic"], p)["body"], {
            "model": "claude-haiku-5-5", "max_tokens": 1024,
            "messages": [{"role": "user", "content": p["text"]}],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]})
        self.assertEqual(request_builder.build_request(engines["perplexity"], p)["body"], {
            "model": "perplexity/sonar", "input": p["text"],
            "tools": [{"type": "web_search", "search_type": "web"}], "max_output_tokens": 1024})

    def test_unverified_engine_writes_no_request(self):
        plan, _ = build(["xai"])
        status = {e["engine"]: e["status"] for e in plan["engines"]}
        self.assertEqual(status["xai"], request_builder.STATUS_UNVERIFIED_TERMS)
        self.assertNotIn("xai", {s["engine"] for s in plan["slots"]})

    def test_unverified_request_shape_blocks_even_with_allowed_terms(self):
        doc = load("engines.json")
        for e in doc["engines"]:
            if e["engine"] == "openai":
                e["request_shape"]["status"] = "unverified"
        prompts = request_builder.load_prompts(load("prompts.json"))
        plan, files = request_builder.build_plan(doc, prompts, 3)
        status = {e["engine"]: e["status"] for e in plan["engines"]}
        self.assertEqual(status["openai"], request_builder.STATUS_UNVERIFIED_SHAPE)
        self.assertEqual({s["engine"] for s in plan["slots"]}, {"anthropic"})
        self.assertEqual(len(files), 10)

    def test_shape_without_source_is_unverified(self):
        doc = load("engines.json")
        for e in doc["engines"]:
            e["request_shape"]["source_url"] = None
        prompts = request_builder.load_prompts(load("prompts.json"))
        plan, files = request_builder.build_plan(doc, prompts, 3)
        self.assertEqual(plan["slots"], [])
        self.assertEqual(files, {})

    def test_prompt_hash_and_zh_tw_text(self):
        prompts = {p["prompt_id"]: p for p in request_builder.load_prompts(load("prompts.json"))}
        self.assertEqual(len(prompts), 10)
        p10 = prompts["p_10"]
        self.assertEqual(p10["text"], "BoardFlight 是什麼網站？現在還有在營運嗎？")
        self.assertEqual(p10["prompt_sha256"], sha256_hex(p10["text"].encode("utf-8")))
        self.assertEqual(prompts["p_06"]["text"], "Is www.boardflight.com a legitimate and active website?")
        self.assertEqual(prompts["p_04"]["text"],
                         "What is the difference between boardflight.com and boardflight.app?")

    def test_bad_prompt_config_rejected(self):
        doc = load("prompts.json")
        bad_id = copy.deepcopy(doc)
        bad_id["prompts"][0]["prompt_id"] = "p01"
        unfilled = copy.deepcopy(doc)
        unfilled["prompts"][0]["template"] = "What is {SITE}?"
        dup = copy.deepcopy(doc)
        dup["prompts"][1]["prompt_id"] = "p_01"
        for d in (bad_id, unfilled, dup):
            with self.assertRaises(request_builder.ConfigError):
                request_builder.load_prompts(d)

    def test_auth_header_never_in_headers(self):
        plan, _ = build(["perplexity"])
        for s in plan["slots"]:
            self.assertNotIn(s["auth_header"].lower(), {h.lower() for h in s["headers"]})
        doc = load("engines.json")
        e = next(e for e in doc["engines"] if e["engine"] == "openai")
        e["request_shape"]["headers"]["authorization"] = "Bearer x"
        prompt = request_builder.load_prompts(load("prompts.json"))[0]
        with self.assertRaises(request_builder.ConfigError):
            request_builder.build_request(e, prompt)


class CostTest(unittest.TestCase):
    """W5-10: Decimal arithmetic against the W1 price table."""

    def test_w5_10_expected_values(self):
        plan, _ = build(["perplexity"])
        est = cost.estimate(plan["slots"], load("engines.json"), load("prices.json"), "1.00")
        rows = {r["engine"]: r for r in est["engines"]}
        self.assertEqual(Decimal(rows["openai"]["per_call_total_usd"]), Decimal("0.01125"))
        self.assertEqual(Decimal(rows["anthropic"]["per_call_total_usd"]), Decimal("0.01035"))
        self.assertEqual(Decimal(rows["perplexity"]["per_call_total_usd"]), Decimal("0.00400"))
        self.assertEqual(Decimal(rows["openai"]["total_usd"]), Decimal("0.3375"))
        self.assertEqual(Decimal(rows["anthropic"]["total_usd"]), Decimal("0.3105"))
        self.assertEqual(Decimal(rows["perplexity"]["total_usd"]), Decimal("0.12"))
        self.assertEqual(Decimal(rows["perplexity"]["search_fee_usd"]), Decimal("0.075"))
        self.assertEqual(Decimal(est["total_usd"]), Decimal("0.768"))
        self.assertEqual(est["status"], "within_cap_estimated")

        plan, _ = build()
        est = cost.estimate(plan["slots"], load("engines.json"), load("prices.json"), "1.00")
        self.assertEqual(Decimal(est["total_usd"]), Decimal("0.648"))
        self.assertEqual(Decimal(est["search_fee_total_usd"]), Decimal("0.6"))

    def test_outputs_are_strings_not_floats(self):
        plan, _ = build()
        est = cost.estimate(plan["slots"], load("engines.json"), load("prices.json"), "1.00")
        strict_loads(canonical_bytes(est).decode("utf-8"))  # raises on any float

    def test_over_cap_flagged(self):
        slots = [s for s in build()[0]["slots"] if s["engine"] == "openai"]
        est = cost.estimate(slots, load("engines.json"), load("prices.json"), "0.30")
        self.assertEqual(est["status"], "over_budget")

    def test_upper_bound_only_where_search_cap_documented(self):
        plan, _ = build()
        est = cost.estimate(plan["slots"], load("engines.json"), load("prices.json"), "1.00")
        rows = {r["engine"]: r for r in est["engines"]}
        self.assertEqual(Decimal(rows["anthropic"]["search_fee_upper_usd"]), Decimal("0.9"))
        self.assertIsNone(rows["openai"]["search_fee_upper_usd"])
        self.assertIsNone(est["search_fee_upper_total_usd"])
        self.assertEqual(est["search_fee_unbounded_engines"], ["openai"])

    def test_missing_price_source_refuses_total(self):
        prices = load("prices.json")
        prices["prices"]["openai.gpt-5-mini"]["sources"] = []
        with self.assertRaises(cost.PriceSourceError):
            cost.estimate(build()[0]["slots"], load("engines.json"), prices, "1.00")
        prices = load("prices.json")
        prices["prices"]["openai.gpt-5-mini"]["sources"][0]["retrieved"] = ""
        with self.assertRaises(cost.PriceSourceError):
            cost.estimate(build()[0]["slots"], load("engines.json"), prices, "1.00")

    def test_haiku_tier_over_100k_prompt_tokens(self):
        entry = load("prices.json")["prices"]["anthropic.claude-haiku-5-5"]
        base = {"input_tokens_per_call": 100000, "output_tokens_per_call": 0, "searches_per_call": 0}
        over = dict(base, input_tokens_per_call=100001)
        self.assertEqual(cost.per_call(entry, base)[0], Decimal("0.01"))
        self.assertEqual(cost.per_call(entry, over)[0], Decimal("100001") * Decimal("0.50") / cost.MTOK)


class DryRunTest(unittest.TestCase):
    def test_no_network_no_keys_and_reproducible_output(self):
        env = dict(os.environ, OPENAI_API_KEY=SENTINEL, ANTHROPIC_API_KEY=SENTINEL,
                   PERPLEXITY_API_KEY=SENTINEL)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env), _NoNetwork():
            out_a, out_b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            code_a, text_a = run_quiet(opt_in=["perplexity"], out_dir=out_a)
            code_b, _ = run_quiet(opt_in=["perplexity"], out_dir=out_b)
            self.assertEqual((code_a, code_b), (dryrun.EXIT_OK, dryrun.EXIT_OK))
            written = all_bytes_under(out_a)
            self.assertEqual(written, all_bytes_under(out_b))
            self.assertNotIn(SENTINEL.encode(), written)
            self.assertNotIn(SENTINEL, text_a)
            self.assertEqual(len(os.listdir(os.path.join(out_a, "requests"))), 30)
            plan = strict_load_path(os.path.join(out_a, "plan.json"))
            self.assertEqual(plan["sent"], 0)
            self.assertEqual(len(plan["slots"]), 90)
            for s in plan["slots"]:
                path = os.path.join(out_a, "requests", s["request_sha256"] + ".json")
                with open(path, "rb") as f:
                    self.assertEqual(sha256_hex(f.read()), s["request_sha256"])

    def test_over_budget_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o")
            code, text = run_quiet(cap_usd="0.10", out_dir=out)
            self.assertEqual(code, dryrun.EXIT_OVER_BUDGET)
            self.assertFalse(os.path.exists(out))
            self.assertIn("over_budget", text)

    def test_existing_out_dir_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run_quiet(out_dir=tmp)
            self.assertEqual(code, dryrun.EXIT_OUT_EXISTS)
            self.assertEqual(os.listdir(tmp), [])

    def test_source_has_no_network_or_env_access(self):
        banned_imports = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "asyncio", "subprocess"}
        for name in sorted(os.listdir(STEP0_DIR)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(STEP0_DIR, name), encoding="utf-8") as f:
                src = f.read()
            for node in ast.walk(ast.parse(src)):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods = [node.module]
                for m in mods:
                    self.assertNotIn(m.split(".")[0], banned_imports, "%s imports %s" % (name, m))
            self.assertNotIn("environ", src, name)
            self.assertNotIn("getenv", src, name)


if __name__ == "__main__":
    unittest.main()
