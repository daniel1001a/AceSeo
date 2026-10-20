"""The live pipeline, the live page fetcher, fixture export and manual import.

No socket is opened: UrllibTransport and UrllibFetcher get fake openers, and
page checks use FixtureFetcher. Provider bodies are SYNTHETIC
(tests.test_adapters). Manual answers are SYNTHETIC text. Keys are fake.
"""

import contextlib
import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error

from geo import cli, decide, fetch, fixtures_export, manual, pipeline
from geo.canonical import canonical_bytes, strict_load_path
from geo.collect import FixtureTransport, UrllibTransport
from geo.pagechecks import FetchError
from geo.validate import codes, load_valid_run, validate_run
from tests import geo_fixtures as fx
from tests.test_adapters import ANT, FACTS, KEYS, OAI, Clock, ant_body, oai_body, prompts
from tests.test_decide import routes_pass

PROMPTS = ("p_01", "p_02")


class FakeResp(io.BytesIO):
    def __init__(self, status, body, headers=()):
        super().__init__(body)
        self.status = status
        self.headers = _Msg(headers)


class _Msg(list):
    def items(self):
        return list(self)


def provider_opener(bodies):
    """bodies: {url: [bytes, ...]} served with status 200, in order."""
    queues = {u: list(q) for u, q in bodies.items()}

    def opener(req, timeout):
        return FakeResp(200, queues[req.full_url].pop(0))
    return opener


def live_run(root, progress=None, repeats=1):
    n = len(PROMPTS) * repeats
    transport = UrllibTransport(opener=provider_opener({OAI: [oai_body()] * n, ANT: [ant_body()] * n}))
    return pipeline.run_live(
        fx.engines_doc({}), fx.load("prices.json"), prompts(PROMPTS), FACTS, root=root, repeats=repeats,
        cap_usd="5", key_pages=fx.KEY_PAGES, mention_terms=fx.MENTION_TERMS, transport=transport,
        fetcher=pipeline.FixtureFetcher(routes_pass()), api_keys=KEYS, clock=Clock(), sleep=lambda s: None,
        progress=progress)


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()


class RunLive(Tmp):
    def test_full_pipeline_with_live_transport(self):
        events = []
        res = live_run(os.path.join(self.tmp, "runs"), progress=events.append)
        index = load_valid_run(res.run_dir, tuple(KEYS.values()))
        self.assertEqual(index.manifest["transport"], "live")
        self.assertEqual(len(index.of_kind("capture")), 4)
        self.assertTrue(index.of_kind("page_check"))
        self.assertTrue(index.of_kind("claim"))
        self.assertTrue(index.lookup(res.decision_id))
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds[0], "page_checks")
        self.assertEqual(kinds[-2:], ["claims", "decision"])
        caps = [e for e in events if e["event"] == "capture"]
        self.assertEqual([e["done"] for e in caps], [1, 2, 3, 4])
        self.assertTrue(all(e["total"] == 4 for e in caps))

    def test_refuses_fixture_transport(self):
        with self.assertRaises(pipeline.PipelineError):
            pipeline.run_live(fx.engines_doc({}), fx.load("prices.json"), prompts(PROMPTS), FACTS,
                              root=self.tmp, repeats=1, cap_usd="5", key_pages=(), mention_terms=fx.MENTION_TERMS,
                              transport=FixtureTransport({}), fetcher=None, api_keys=KEYS, clock=Clock())

    def test_offline_refuses_live_transport(self):
        with self.assertRaises(pipeline.PipelineError):
            pipeline.run_offline(fx.engines_doc({}), fx.load("prices.json"), prompts(PROMPTS), FACTS,
                                 root=self.tmp, repeats=1, cap_usd="5", key_pages=(),
                                 mention_terms=fx.MENTION_TERMS, transport=UrllibTransport(),
                                 fetcher=pipeline.FixtureFetcher({}), api_keys=KEYS, clock=Clock())

    def test_progress_printer(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cli.print_progress({"event": "capture", "done": 1, "total": 2, "engine": "openai", "prompt_id": "p_01",
                                "repeat_index": 0, "attempt": 1, "status": "failed", "error_class": "timeout",
                                "spent_estimate_usd": "0.01"})
        self.assertEqual(err.getvalue(), "[1/2] openai p_01 r0 attempt 1: failed (timeout) (spent, Estimated: $0.01)\n")


class Export(Tmp):
    def test_export_and_replay(self):
        res = live_run(os.path.join(self.tmp, "runs"))
        dest = os.path.join(self.tmp, "live")
        entries = fixtures_export.export_fixtures(res.run_dir, dest, secrets=tuple(KEYS.values()))
        self.assertEqual(len(entries), 4)
        doc = strict_load_path(os.path.join(dest, "index.json"))
        self.assertEqual(doc["run_id"], os.path.basename(res.run_dir))
        for e in doc["fixtures"]:
            with open(os.path.join(dest, e["file"]), "rb") as f:
                body = f.read()
            self.assertNotIn(b'"resp_1"', body)
            self.assertNotIn(b'"msg_1"', body)
            self.assertNotIn(fx.SECRET.encode(), body)
            out = fixtures_export.ADAPTERS[e["engine"]].parse(e["http_status"], body)
            self.assertEqual(fixtures_export.expected(out), e["expected"])
            self.assertEqual(e["expected"]["status"], "ok")
        with self.assertRaises(fixtures_export.ExportError):
            fixtures_export.export_fixtures(res.run_dir, dest)

    def test_refuses_fixture_run(self):
        res = pipeline.run_offline(
            fx.engines_doc({}), fx.load("prices.json"), prompts(("p_01",)), FACTS, root=self.tmp, repeats=1,
            cap_usd="5", key_pages=fx.KEY_PAGES, mention_terms=fx.MENTION_TERMS,
            transport=FixtureTransport({OAI: [(200, oai_body())], ANT: [(200, ant_body())]}),
            fetcher=pipeline.FixtureFetcher(routes_pass()), api_keys=KEYS, clock=Clock())
        with self.assertRaises(fixtures_export.ExportError):
            fixtures_export.export_fixtures(res.run_dir, os.path.join(self.tmp, "live"))

    def test_redact_nested(self):
        self.assertEqual(fixtures_export.redact({"id": "x", "a": [{"id": "y", "user": None, "k": 1}]}),
                         {"id": "redacted", "a": [{"id": "redacted", "user": None, "k": 1}]})


class Fetcher(unittest.TestCase):
    def fetcher(self, routes):
        self.calls = []

        def open_fn(req, timeout):
            self.calls.append((req.full_url, req.get_header("User-agent")))
            r = routes[req.full_url]
            if isinstance(r, BaseException):
                raise r
            status, headers, body = r
            if 300 <= status:
                raise urllib.error.HTTPError(req.full_url, status, "x", _Msg(headers), io.BytesIO(body))
            return FakeResp(status, body, headers)
        return fetch.UrllibFetcher(open_fn=open_fn)

    def test_redirect_chain_and_headers(self):
        f = self.fetcher({"http://a.test/": (301, [("Location", "https://a.test/")], b""),
                          "https://a.test/": (200, [("Content-Type", "text/html")], b"<html></html>")})
        resp = f("http://a.test/", "geo-evidence-test")
        self.assertEqual(resp.final_url, "https://a.test/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers, [["content-type", "text/html"]])
        self.assertEqual(resp.redirect_chain, [{"url": "http://a.test/", "status": 301}])
        self.assertEqual(self.calls[0][1], "geo-evidence-test")

    def test_relative_location_and_404(self):
        f = self.fetcher({"https://a.test/x": (302, [("Location", "/y")], b""),
                          "https://a.test/y": (404, [], b"gone")})
        resp = f("https://a.test/x", "ua")
        self.assertEqual((resp.final_url, resp.status, resp.body), ("https://a.test/y", 404, b"gone"))

    def test_redirect_loop_stops(self):
        f = self.fetcher({"https://a.test/": (302, [("Location", "https://a.test/")], b"")})
        resp = f("https://a.test/", "ua")
        self.assertEqual(len(resp.redirect_chain), fetch.MAX_REDIRECTS + 1)
        self.assertEqual(resp.status, 302)

    def test_truncation_is_visible(self):
        big = b"a" * (fetch.MAX_BODY_BYTES + 10)
        resp = self.fetcher({"https://a.test/": (200, [], big)})("https://a.test/", "ua")
        self.assertEqual(len(resp.body), fetch.MAX_BODY_BYTES)
        self.assertIn([fetch.TRUNCATED_HEADER, str(fetch.MAX_BODY_BYTES)], resp.headers)

    def test_error_mapping(self):
        for exc, cls in ((socket.timeout(), "timeout"), (urllib.error.URLError(socket.timeout()), "timeout"),
                         (urllib.error.URLError(ConnectionRefusedError()), "connection"),
                         (ConnectionResetError(), "connection")):
            with self.assertRaises(FetchError) as cm:
                self.fetcher({"https://a.test/": exc})("https://a.test/", "ua")
            self.assertEqual(str(cm.exception.args[0]), cls)
        with self.assertRaises(FetchError):
            self.fetcher({})("ftp://a.test/", "ua")


ANSWER = "BoardFlight covers 40 US airports. It shows TSA wait times."
OBSERVED = "2026-10-20T08:00:00.000000Z"
CREATED = "2026-10-20T09:00:00.000000Z"


class Manual(Tmp):
    def imp(self, **kw):
        args = dict(text_bytes=ANSWER.encode(), surface="google-aio", query="how many airports does boardflight cover",
                    facts_bytes=FACTS, mention_terms=fx.MENTION_TERMS, observed_at=OBSERVED, created_at=CREATED,
                    screenshot_bytes=b"\x89PNG synthetic", source_urls=["https://www.boardflight.com/"],
                    secrets=(fx.SECRET,))
        args.update(kw)
        return manual.import_manual(os.path.join(self.tmp, "runs"), **args)

    def test_import_validates_and_matches_claims(self):
        run_dir = self.imp()
        index = load_valid_run(run_dir)
        self.assertEqual((index.manifest["run_kind"], index.manifest["transport"]), ("manual", "manual"))
        (cap,) = index.of_kind("capture")
        self.assertEqual((cap["access"], cap["status"], cap["engine"]), ("manual", "ok", "google-aio"))
        self.assertEqual(cap["engine_snapshot"]["terms_status"], "manual")
        self.assertEqual(cap["citations"][0]["provider_field"], "manual")
        self.assertEqual(cap["attachments"][0]["role"], "screenshot")
        with open(os.path.join(run_dir, cap["raw_path"]), "rb") as f:
            self.assertEqual(f.read(), ANSWER.encode())
        claims = index.of_kind("claim")
        self.assertIn("contradicted", [c["verdict"] for c in claims])
        self.assertTrue(all(c["capture_id"] == cap["id"] for c in claims))
        self.assertEqual(index.of_kind("decision"), [])

    def test_decide_refuses_manual_run(self):
        index = load_valid_run(self.imp())
        with self.assertRaises(decide.DecisionError) as cm:
            decide.decide(index, CREATED)
        self.assertEqual(cm.exception.code, "E_RUN_KIND")

    def test_refusals(self):
        bad = (dict(observed_at="2026-10-21T00:00:00.000000Z"), dict(text_bytes=b"  \n"),
               dict(text_bytes=b"\xff\xfe"), dict(surface="Google AIO"), dict(source_urls=["not a url"]),
               dict(query=" "), dict(mention_terms=()), dict(observed_at="2026-10-20"))
        for kw in bad:
            with self.assertRaises(manual.ManualError, msg=repr(kw)):
                self.imp(**kw)

    def test_validator_catches_tampering(self):
        run_dir = self.imp(screenshot_bytes=None)
        path = os.path.join(run_dir, "captures.jsonl")
        with open(path, "rb") as f:
            rec = json.loads(f.read())
        rec["access"] = "api"
        with open(path, "wb") as f:
            f.write(canonical_bytes(rec) + b"\n")
        self.assertIn("E_SCHEMA", codes(validate_run(run_dir)))

    def test_raw_must_equal_answer(self):
        run_dir = self.imp(screenshot_bytes=None)
        index = load_valid_run(run_dir)
        (cap,) = index.of_kind("capture")
        raw = os.path.join(run_dir, cap["raw_path"])
        os.chmod(raw, 0o644)
        with open(raw, "wb") as f:
            f.write(b"something else")
        self.assertTrue(validate_run(run_dir))


class ManualCli(Tmp):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(args), environ={}, clock=lambda: CREATED)
        return rc, out.getvalue(), err.getvalue()

    def test_import_ledger_report(self):
        ans = os.path.join(self.tmp, "aio.txt")
        with open(ans, "w", encoding="utf-8") as f:
            f.write(ANSWER)
        rc, out, err = self.cli("import-manual", ans, "--surface", "google-aio", "--query", "boardflight airports",
                                "--observed-at", "2026-10-20T08:00:00Z", "--mention-term", "BoardFlight",
                                "--cite", "https://www.boardflight.com/", "--out", os.path.join(self.tmp, "runs"))
        self.assertEqual(rc, 0, err)
        run_dir = out.strip()
        rc, out, _ = self.cli("ledger", run_dir)
        self.assertEqual(rc, 0)
        self.assertIn("access manual", out)
        self.assertIn("contradicted", out)
        self.assertIn("never counted in a rate or a decision", out)
        rc, out, err = self.cli("report", run_dir)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("geo ledger", err)

    def test_missing_answer_file(self):
        rc, _, err = self.cli("import-manual", os.path.join(self.tmp, "nope.txt"), "--surface", "google-aio",
                              "--query", "q", "--observed-at", OBSERVED, "--mention-term", "BoardFlight",
                              "--out", os.path.join(self.tmp, "runs"))
        self.assertEqual(rc, 2)
        self.assertIn("refused", err)

    def test_ledger_of_live_run(self):
        res = live_run(os.path.join(self.tmp, "runs"))
        rc, out, _ = self.cli("ledger", res.run_dir)
        self.assertEqual(rc, 0)
        self.assertIn("access api", out)
        self.assertIn("4 capture(s)", out)


if __name__ == "__main__":
    unittest.main()
