"""Step 3 tests: provider adapters and the capture collector (W4 3.3, W5-02).

Fixture labels:
  SYNTHETIC  every provider response body below. Shapes follow the documented
             examples (OpenAI web search guide, Anthropic web search tool doc,
             read 2026-10-19); fields marked unverified in FIELD_STATUS are not
             in those docs. No real provider response has been recorded yet.
  Keys are fake (fx.SECRET). No test opens a socket.
"""

import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error

from geo import adapters, collect, records
from geo.adapters import ADAPTERS, NotImplementedAdapter
from geo.canonical import canonical_bytes, strict_load_path
from geo.collect import CollectError, FixtureTransport, TermsGateError, TransportError, UrllibTransport
from geo.validate import validate_run
from step0 import request_builder

from tests import geo_fixtures as fx

OAI = "https://api.openai.com/v1/responses"
ANT = "https://api.anthropic.com/v1/messages"
KEYS = {"openai": fx.SECRET, "anthropic": fx.SECRET + "-anthropic"}
SITE = "https://www.boardflight.com/"


def jb(doc):
    return json.dumps(doc).encode("utf-8")


def oai_body(text="BoardFlight covers 33 US airports.", searches=1, annotations=None, status="completed",
             content=None, usage=True):
    out = [{"type": "web_search_call", "id": "ws_%d" % i, "status": "completed",
            "action": {"type": "search", "query": "airport security wait"}} for i in range(searches)]
    if annotations is None:
        annotations = [{"type": "url_citation", "start_index": 0, "end_index": 11, "url": SITE,
                        "title": "BoardFlight"}] if searches else []
    if content is None:
        content = [{"type": "output_text", "text": text, "annotations": annotations}]
    out.append({"type": "message", "id": "msg_1", "status": "completed", "role": "assistant", "content": content})
    doc = {"id": "resp_1", "object": "response", "status": status, "output": out}
    if usage:
        doc["usage"] = {"input_tokens": 1200, "output_tokens": 300}
    return jb(doc)


def ant_body(text="BoardFlight covers 33 US airports.", searches=1, stop="end_turn", tool_error=None,
             cache_creation=0):
    content = []
    if searches or tool_error:
        content.append({"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search",
                        "input": {"query": "airport security wait"}})
        result = ({"type": "web_search_tool_result_error", "error_code": tool_error} if tool_error else
                  [{"type": "web_search_result", "url": SITE, "title": "BoardFlight", "encrypted_content": "x",
                    "page_age": None}])
        content.append({"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": result})
    cits = [{"type": "web_search_result_location", "url": SITE, "title": "BoardFlight", "encrypted_index": "x",
             "cited_text": "Covers 33 US airports"}] if searches and not tool_error else []
    if text is not None:
        block = {"type": "text", "text": text}
        if cits:
            block["citations"] = cits
        content.append(block)
    usage = {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": cache_creation}
    if searches:
        usage["server_tool_use"] = {"web_search_requests": searches}
    return jb({"id": "msg_1", "type": "message", "role": "assistant", "content": content,
               "stop_reason": stop, "usage": usage})


class OpenAIParse(unittest.TestCase):
    a = ADAPTERS["openai"]

    def test_success(self):
        o = self.a.parse(200, oai_body())
        self.assertEqual((o.status, o.error_class, o.search_observed), ("ok", None, 1))
        self.assertEqual(o.answer_text, "BoardFlight covers 33 US airports.")
        self.assertEqual(o.citations, [{"url": SITE, "title": "BoardFlight", "cited_text": None, "position": 0,
                                        "provider_field": "output[1].content[0].annotations[0]"}])
        self.assertEqual(o.usage, {"input_tokens": 1200, "output_tokens": 300, "cached_input_tokens": None,
                                   "search_calls": 1})

    def test_no_search(self):
        o = self.a.parse(200, oai_body(searches=0))
        self.assertEqual((o.status, o.search_observed, o.citations), ("ok", 0, []))

    def test_refused(self):
        o = self.a.parse(200, oai_body(searches=0, content=[{"type": "refusal", "refusal": "I can't help."}]))
        self.assertEqual((o.status, o.error_class, o.answer_text, o.citations), ("refused", None, "I can't help.", []))

    def test_failures(self):
        self.assertEqual(self.a.parse(429, b'{"error":{}}').error_class, "rate_limited")
        self.assertEqual(self.a.parse(500, b"<html>oops</html>").error_class, "http_error")
        self.assertEqual(self.a.parse(200, b"not json").error_class, "parse_error")
        self.assertEqual(self.a.parse(200, b'{"output": 3}').error_class, "parse_error")
        self.assertEqual(self.a.parse(200, oai_body(text="  ", searches=0)).error_class, "empty_answer")
        o = self.a.parse(200, oai_body(status="incomplete"))
        self.assertEqual((o.status, o.error_class), ("failed", "incomplete"))

    def test_auth_and_build(self):
        self.assertEqual(self.a.auth_value("k"), "Bearer k")
        doc = fx.engines_doc()
        with self.assertRaises(request_builder.ConfigError):
            self.a.build(fx.engine_entry(doc, "anthropic"), {"text": "x"})


class AnthropicParse(unittest.TestCase):
    a = ADAPTERS["anthropic"]

    def test_success(self):
        o = self.a.parse(200, ant_body())
        self.assertEqual((o.status, o.search_observed), ("ok", 1))
        self.assertEqual(o.citations, [{"url": SITE, "title": "BoardFlight", "cited_text": "Covers 33 US airports",
                                        "position": 0, "provider_field": "content[2].citations[0]"}])
        self.assertEqual(o.usage, {"input_tokens": 1000, "output_tokens": 200, "cached_input_tokens": 0,
                                   "search_calls": 1})

    def test_no_search(self):
        o = self.a.parse(200, ant_body(searches=0))
        self.assertEqual((o.status, o.search_observed, o.citations), ("ok", 0, []))
        self.assertEqual(o.usage["search_calls"], 0)

    def test_refused(self):
        o = self.a.parse(200, ant_body(searches=0, text="", stop="refusal"))
        self.assertEqual((o.status, o.error_class, o.citations), ("refused", None, []))

    def test_failures(self):
        self.assertEqual(self.a.parse(429, b"{}").error_class, "rate_limited")
        self.assertEqual(self.a.parse(529, b"{}").error_class, "http_error")
        self.assertEqual(self.a.parse(200, b"\xff").error_class, "parse_error")
        self.assertEqual(self.a.parse(200, ant_body(text=None, searches=0)).error_class, "empty_answer")
        self.assertEqual(self.a.parse(200, ant_body(stop="pause_turn")).error_class, "incomplete")

    def test_tool_error_in_200(self):
        self.assertEqual(self.a.parse(200, ant_body(tool_error="unavailable")).error_class, "tool_error")
        self.assertEqual(self.a.parse(200, ant_body(tool_error="too_many_requests")).error_class, "rate_limited")
        self.assertEqual(self.a.parse(200, ant_body(tool_error="max_uses_exceeded")).status, "ok")

    def test_cache_write_drops_usage(self):
        self.assertIsNone(self.a.parse(200, ant_body(cache_creation=5)).usage)

    def test_auth(self):
        self.assertEqual(self.a.auth_value("k"), "k")


class PerplexityInterface(unittest.TestCase):
    def test_build_only(self):
        a = ADAPTERS["perplexity"]
        req = a.build(fx.engine_entry(fx.engines_doc(), "perplexity"), {"text": "x"})
        self.assertEqual(req["auth_header"], "Authorization")
        with self.assertRaises(NotImplementedAdapter):
            a.parse(200, b"{}")
        self.assertNotIn("perplexity", adapters.IMPLEMENTED)


class Clock:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return fx.ts(self.n)


def prompts(ids=("p_09",)):
    return [{"prompt_id": p["prompt_id"], "text": p["text"]}
            for p in request_builder.load_prompts(fx.load("prompts.json")) if p["prompt_id"] in ids]


FACTS = canonical_bytes(strict_load_path(fx.FACTS_PATH))


class CollectBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "runs")

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, responses=None, *, only=None, overrides=None, prompt_ids=("p_09",), repeats=1, cap="5",
                max_attempts=2, send=True, opt_in=(), keys=KEYS, transport=None):
        ov = dict(overrides or {})
        if only:
            for e in ("anthropic", "openai"):
                if e != only:
                    ov.setdefault(e, {})["enabled"] = False
        self.transport = transport or (FixtureTransport(responses or {}) if send else None)
        return collect.collect(
            fx.engines_doc(ov), fx.load("prices.json"), prompts(prompt_ids), FACTS, root=self.root,
            repeats=repeats, cap_usd=cap, key_pages=fx.KEY_PAGES, mention_terms=fx.MENTION_TERMS,
            opt_in_selected=opt_in, max_attempts=max_attempts, send=send, transport=self.transport,
            api_keys=keys if send else None, clock=Clock(), sleep=lambda s: None)

    def captures(self, run_dir):
        path = os.path.join(run_dir, "captures.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, "rb") as f:
            return [json.loads(line) for line in f]

    def manifest(self, run_dir):
        with open(os.path.join(run_dir, "manifest.json"), "rb") as f:
            return json.loads(f.read())

    def assert_clean(self, run_dir):
        self.assertEqual(validate_run(run_dir, secrets=tuple(KEYS.values())), [])
        for dirpath, _, names in os.walk(run_dir):
            for n in names:
                with open(os.path.join(dirpath, n), "rb") as f:
                    data = f.read()
                for k in KEYS.values():
                    self.assertNotIn(k.encode(), data, n)
                self.assertNotIn(b"Bearer", data, n)


class DryRunAndRefusals(CollectBase):
    def test_dry_run_writes_nothing(self):
        s = self.collect(send=False, prompt_ids=("p_01", "p_09"), repeats=3)
        self.assertFalse(os.path.exists(self.root))
        self.assertEqual((s["mode"], s["writes"], s["sendable_slots"]), ("dry_run", "none", 12))
        # perplexity (opt-in not selected) and xai (terms unverified): 2 prompts x 3 repeats each
        self.assertEqual(s["planned_slots"], 24)
        self.assertEqual({x["engine"] for x in s["skipped_slots"]}, {"perplexity", "xai"})
        self.assertEqual({x["reason"] for x in s["skipped_slots"]}, {"terms_gate"})
        est = s["estimate"]
        self.assertEqual(est["label"], "Estimated")
        self.assertEqual(est["per_call"]["openai"]["upper_basis"], "assumed_1_search_per_call_estimated")
        self.assertEqual(est["per_call"]["anthropic"]["upper_basis"], "documented_max_searches_per_call")
        self.assertEqual(est["per_call"]["anthropic"]["upper_searches"], 3)
        self.assertTrue(all("auth_header" in r and fx.SECRET not in json.dumps(r) for r in s["requests"]))

    def test_dry_run_rejects_transport(self):
        t = FixtureTransport({})
        with self.assertRaises(CollectError):
            collect.collect(fx.engines_doc(), fx.load("prices.json"), prompts(), FACTS, root=self.root,
                            repeats=1, cap_usd="5", key_pages=fx.KEY_PAGES, mention_terms=fx.MENTION_TERMS,
                            transport=t)
        self.assertEqual((t.calls, os.path.exists(self.root)), ([], False))

    def test_send_needs_transport_and_keys(self):
        with self.assertRaises(CollectError):
            self.collect(transport=object())
        with self.assertRaises(CollectError):
            self.collect(keys={"openai": fx.SECRET})
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(os.path.exists(self.root))

    def test_over_budget_sends_nothing(self):
        with self.assertRaises(CollectError):
            self.collect(cap="0.01", repeats=3)
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(os.path.exists(self.root))

    def test_perplexity_refused(self):
        for send in (False, True):
            with self.assertRaises(CollectError):
                self.collect(opt_in=("perplexity",), send=send)
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(os.path.exists(self.root))


class Send(CollectBase):
    def test_success_both_engines(self):
        d = self.collect({OAI: [(200, oai_body())], ANT: [(200, ant_body())]})
        self.assert_clean(d)
        caps = self.captures(d)
        self.assertEqual(sorted((c["engine"], c["status"], c["search_observed"]) for c in caps),
                         [("anthropic", "ok", 1), ("openai", "ok", 1)])
        m = self.manifest(d)
        self.assertEqual((m["transport"], m["planned_slots"]), ("fixture", 4))
        self.assertEqual(sorted((s["engine"], s["reason"]) for s in m["skipped_slots"]),
                         [("perplexity", "terms_gate"), ("xai", "terms_gate")])
        self.assertEqual(m["budget"]["spent_estimate_usd"], "0.0216")  # 0.01035 + 0.01125 (W5-10), Estimated
        ant = next(c for c in caps if c["engine"] == "anthropic")
        self.assertIsNotNone(ant["cost_from_usage_usd"])
        oai = next(c for c in caps if c["engine"] == "openai")
        self.assertIsNone(oai["cost_from_usage_usd"])  # cached token semantics unverified

    def test_auth_header_built_not_stored(self):
        d = self.collect({OAI: [(200, oai_body())], ANT: [(200, ant_body())]})
        by_url = {c["url"]: c for c in self.transport.calls}
        self.assertEqual(by_url[OAI]["headers"]["Authorization"], "Bearer " + KEYS["openai"])
        self.assertEqual(by_url[ANT]["headers"]["x-api-key"], KEYS["anthropic"])
        self.assertEqual(by_url[ANT]["headers"]["anthropic-version"], "2023-06-01")
        for c in self.captures(d):
            with open(os.path.join(d, "raw", c["request_sha256"] + ".json"), "rb") as f:
                body = f.read()
            self.assertEqual(body, by_url[OAI if c["engine"] == "openai" else ANT]["body"])
        self.assert_clean(d)

    def test_no_search(self):
        d = self.collect({OAI: [(200, oai_body(searches=0))]}, only="openai")
        (c,) = self.captures(d)
        self.assertEqual((c["status"], c["search_observed"], c["citations"]), ("ok", 0, []))
        self.assert_clean(d)

    def test_refused_not_retried(self):
        d = self.collect({ANT: [(200, ant_body(searches=0, text="", stop="refusal"))]}, only="anthropic",
                         max_attempts=3)
        (c,) = self.captures(d)
        self.assertEqual((c["status"], c["attempt"]), ("refused", 1))
        self.assertEqual(len(self.transport.calls), 1)
        self.assert_clean(d)

    def test_timeout_then_ok(self):
        d = self.collect({OAI: [TransportError("timeout"), (200, oai_body())]}, only="openai")
        a1, a2 = sorted(self.captures(d), key=lambda c: c["attempt"])
        self.assertEqual((a1["status"], a1["error_class"], a1["raw_sha256"], a1["http_status"]),
                         ("failed", "timeout", None, None))
        self.assertEqual(a2["status"], "ok")
        self.assertEqual(a1["series_key"], a2["series_key"])
        self.assert_clean(d)

    def test_failures_exhaust_attempts(self):
        d = self.collect({ANT: [(429, b'{"type":"error"}'), (500, b"<html>down</html>")]}, only="anthropic")
        caps = sorted(self.captures(d), key=lambda c: c["attempt"])
        self.assertEqual([(c["error_class"], c["http_status"]) for c in caps],
                         [("rate_limited", 429), ("http_error", 500)])
        self.assertTrue(caps[1]["raw_path"].endswith(".bin"))
        self.assert_clean(d)

    def test_parse_error_and_tool_error(self):
        d = self.collect({ANT: [(200, b"{truncated"), (200, ant_body(tool_error="unavailable"))]}, only="anthropic")
        self.assertEqual([c["error_class"] for c in sorted(self.captures(d), key=lambda c: c["attempt"])],
                         ["parse_error", "tool_error"])
        self.assert_clean(d)

    def test_pause_turn_incomplete(self):
        d = self.collect({ANT: [(200, ant_body(stop="pause_turn"))]}, only="anthropic", max_attempts=1)
        (c,) = self.captures(d)
        self.assertEqual((c["status"], c["error_class"]), ("failed", "incomplete"))
        self.assert_clean(d)

    def test_budget_cap_mid_run(self):
        est = "0.01125"  # openai Estimated per call (W5-10)
        d = self.collect({OAI: [(500, b"{}"), (500, b"{}"), (200, oai_body())]}, only="openai",
                         repeats=2, cap="0.0225", max_attempts=2)
        caps = self.captures(d)
        self.assertEqual([(c["repeat_index"], c["attempt"]) for c in caps], [(0, 1), (0, 2)])
        m = self.manifest(d)
        self.assertIn({"engine": "openai", "prompt_id": "p_09", "repeat_index": 1, "reason": "budget_cap"},
                      m["skipped_slots"])
        self.assertEqual(m["budget"], {"cap_usd": "0.0225", "spent_estimate_usd": "0.0225"})
        self.assertEqual(caps[0]["cost_estimate_usd"], est)
        self.assert_clean(d)

    def test_user_abort(self):
        class Abort(FixtureTransport):
            def __call__(self, method, url, headers, body):
                if len(self.calls) == 1:
                    self.calls.append(url)
                    raise KeyboardInterrupt
                return FixtureTransport.__call__(self, method, url, headers, body)

        t = Abort({OAI: [(200, oai_body())]})
        with self.assertRaises(KeyboardInterrupt):
            self.collect(only="openai", repeats=3, transport=t)
        (d,) = [os.path.join(self.root, n) for n in os.listdir(self.root)]
        m = self.manifest(d)
        self.assertEqual([(s["repeat_index"], s["reason"]) for s in m["skipped_slots"] if s["engine"] == "openai"],
                         [(2, "user_abort")])
        self.assertEqual(len(self.captures(d)), 1)
        self.assert_clean(d)

    def test_echoed_key_refused(self):
        with self.assertRaises(Exception) as cm:
            self.collect({OAI: [(200, oai_body(text="key " + KEYS["openai"]))]}, only="openai")
        self.assertEqual(type(cm.exception).__name__, "SecretError")
        (d,) = [os.path.join(self.root, n) for n in os.listdir(self.root)]
        self.assertEqual(self.captures(d), [])


class TermsGate(CollectBase):
    """W5-02 parts A, C and D at the writer (T3)."""

    def test_part_a_unverified(self):
        d = self.collect({}, only="openai", overrides={"openai": {"terms_status": "unverified"}})
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(os.path.exists(os.path.join(d, "captures.jsonl")))
        m = self.manifest(d)
        self.assertIn({"engine": "openai", "prompt_id": "p_09", "repeat_index": 0, "reason": "terms_gate"},
                      m["skipped_slots"])
        self.assertIn("openai", [e["engine"] for e in m["engines_excluded"]])
        self.assertEqual(os.listdir(os.path.join(d, "raw")), [])
        self.assert_clean(d)

    def test_part_c_opt_in_not_selected(self):
        d = self.collect({OAI: [(200, oai_body())]}, only="openai")
        m = self.manifest(d)
        self.assertIn({"engine": "perplexity", "prompt_id": "p_09", "repeat_index": 0, "reason": "terms_gate"},
                      m["skipped_slots"])
        self.assertEqual([c["url"] for c in self.transport.calls], [OAI])  # part D: one call, one line
        self.assertEqual(len(self.captures(d)), 1)

    def test_send_guard_rechecks_snapshot(self):
        real = collect.build_plan

        def tampered(*a, **k):
            plan = real(*a, **k)
            for s in plan.snapshots:
                s["terms_status"] = "verified-restricted"
            return plan

        collect.build_plan = tampered
        try:
            d = self.collect({OAI: [(200, oai_body())]}, only="openai")
        finally:
            collect.build_plan = real
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.captures(d), [])
        self.assertIn({"engine": "openai", "prompt_id": "p_09", "repeat_index": 0, "reason": "terms_gate"},
                      self.manifest(d)["skipped_slots"])
        with self.assertRaises(TermsGateError):
            collect.guard({"engine": "openai", "terms_status": "unverified", "opt_in": False}, ())


class Urllib(unittest.TestCase):
    """UrllibTransport error mapping with a fake opener (no socket)."""

    def send(self, exc=None, url=OAI):
        def opener(req, timeout):
            self.req = req
            raise exc

        return UrllibTransport(opener=opener)("POST", url, {"Authorization": "Bearer x"}, b"{}")

    def test_mapping(self):
        err = urllib.error.HTTPError(OAI, 429, "Too Many", {}, io.BytesIO(b'{"e":1}'))
        self.assertEqual(self.send(err), (429, b'{"e":1}'))
        self.assertEqual(self.req.get_method(), "POST")
        for exc, ec in ((socket.timeout(), "timeout"), (urllib.error.URLError(socket.timeout()), "timeout"),
                        (urllib.error.URLError(ConnectionRefusedError()), "connection"),
                        (ConnectionResetError(), "connection")):
            with self.assertRaises(TransportError) as cm:
                self.send(exc)
            self.assertEqual(cm.exception.error_class, ec)
        with self.assertRaises(CollectError):
            self.send(None, url="http://api.openai.com/v1/responses")

    def test_error_class_is_known(self):
        self.assertIn("incomplete", records.ERROR_CLASSES)
        self.assertIn("tool_error", records.ERROR_CLASSES)
        with self.assertRaises(ValueError):
            TransportError("http_error")


class Cli(unittest.TestCase):
    """geo.cli without network: dry run, and --live refused without keys."""

    def run_cli(self, *extra, environ=None):
        import contextlib
        from geo import cli
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = cli.main(["collect", "--out", os.path.join(tmp, "runs"), "--cap-usd", "5",
                               "--mention-term", "BoardFlight"] + list(extra), environ=environ or {})
            return rc, out.getvalue(), err.getvalue(), os.listdir(tmp)

    def test_dry_run(self):
        rc, out, _, left = self.run_cli()
        self.assertEqual((rc, left), (0, []))
        self.assertEqual(json.loads(out)["mode"], "dry_run")

    def test_live_without_keys(self):
        rc, _, err, left = self.run_cli("--live")
        self.assertEqual((rc, left), (2, []))
        self.assertIn("ANTHROPIC_API_KEY", err)


if __name__ == "__main__":
    unittest.main()
