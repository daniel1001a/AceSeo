"""Step 7: report builder and the offline end-to-end dry run.

Provider bodies are SYNTHETIC (tests.test_adapters). Page-check bodies are the
RECORDED BoardFlight pages behind SYNTHETIC status lines, served by
FixtureFetcher. Keys are fake. Nothing touches the network.
"""

import contextlib
import copy
import io
import dataclasses
import os
import re
import tempfile
import unittest

from geo import cli, number, pipeline, render
from geo import report as R
from geo.collect import FixtureTransport, UrllibTransport
from geo.render import RenderError
from geo.validate import load_valid_run, validate_run
from tests import geo_fixtures as fx
from tests.test_adapters import ANT, FACTS, KEYS, OAI, Clock, ant_body, oai_body, prompts
from tests.test_decide import C_TEXT, routes_noindex, routes_pass
from tests.test_pagechecks import JFK_KEY

PROMPTS = ("p_01", "p_02")
REPEATS = 3
SLOTS = len(PROMPTS) * REPEATS


def responses(text=None, searches=1):
    kw = {"searches": searches}
    if text is not None:
        kw["text"] = text
    return {OAI: [(200, oai_body(**kw))] * SLOTS, ANT: [(200, ant_body(**kw))] * SLOTS}


class PipelineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.n = 0

    def tearDown(self):
        self._tmp.cleanup()

    def run_pipeline(self, routes, resp, out_path=None, transport=None, fetcher=None):
        self.n += 1
        return pipeline.run_offline(
            fx.engines_doc({}), fx.load("prices.json"), prompts(PROMPTS), FACTS,
            root=os.path.join(self._tmp.name, "runs%d" % self.n), repeats=REPEATS, cap_usd="5",
            key_pages=fx.KEY_PAGES, mention_terms=fx.MENTION_TERMS, key_content=(JFK_KEY,),
            transport=transport or FixtureTransport(resp), fetcher=fetcher or pipeline.FixtureFetcher(routes),
            api_keys=KEYS, clock=Clock(), out_path=out_path)

    def decision(self, res):
        index = load_valid_run(res.run_dir, tuple(KEYS.values()))
        return index, index.lookup(res.decision_id).record


class EndToEnd(PipelineCase):
    def test_seo_first(self):
        res = self.run_pipeline(routes_noindex(), responses())
        self.assertEqual(validate_run(res.run_dir, secrets=tuple(KEYS.values())), [])
        _, dec = self.decision(res)
        self.assertEqual((dec["outcome"], dec["fired_rule_id"]), ("seo_first", "R1"))
        self.assertIn("## Failing blocking checks", res.text)
        self.assertIn("SEO first.", res.text)
        self.assertIn(res.decision_id, res.text)

    def test_geo_fix_facts(self):
        res = self.run_pipeline(routes_pass(), responses(C_TEXT))
        index, dec = self.decision(res)
        self.assertEqual(dec["outcome"], "geo_fix_facts")
        self.assertIn("## Contradicted or outdated claims", res.text)
        for c in index.of_kind("claim"):
            self.assertIn(c["id"], res.text)

    def test_geo_content(self):
        res = self.run_pipeline(routes_pass(), responses(searches=0))
        _, dec = self.decision(res)
        self.assertEqual(dec["outcome"], "geo_content")
        self.assertIn("hypothesis to test", res.text)

    def test_no_action(self):
        res = self.run_pipeline(routes_pass(), responses())
        _, dec = self.decision(res)
        self.assertEqual(dec["outcome"], "no_action")

    def test_footer_and_not_checked(self):
        res = self.run_pipeline(routes_pass(), responses())
        self.assertIn(render.FOOTER, res.text)
        self.assertIn("## Excluded and skipped", res.text)
        self.assertIn("## Not checked", res.text)
        for item, text in render.NOT_CHECKED_BASELINE:
            self.assertIn("- %s: %s" % (item, text), res.text)

    def test_every_number_shows_n_and_ids(self):
        res = self.run_pipeline(routes_pass(), responses())
        _, dec = self.decision(res)
        self.assertTrue(dec["numbers"])
        for d in dec["numbers"]:
            self.assertTrue(d["evidence_ids"])
            self.assertIsInstance(d["n"], int)
        meas = res.text.split("## Measurements", 1)[1].split("\n## ", 1)[0]
        lines = [ln for ln in meas.splitlines() if ln.startswith("- ")]
        self.assertEqual(len(lines), len(dec["numbers"]))
        for ln in lines:
            self.assertRegex(ln, r"\(n=\d+\)|^- \d+/\d+ ")
            self.assertRegex(ln, r"evidence: (cap|pc)_[a-z-]+_[0-9a-f]{16}")

    def test_deterministic(self):
        a = self.run_pipeline(routes_pass(), responses(C_TEXT))
        b = self.run_pipeline(routes_pass(), responses(C_TEXT))
        self.assertEqual(a.text, b.text)
        self.assertEqual(a.decision_id, b.decision_id)

    def test_out_path(self):
        out = os.path.join(self._tmp.name, "report.md")
        res = self.run_pipeline(routes_pass(), responses(), out_path=out)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), res.text)

    def test_no_secret_written(self):
        out = os.path.join(self._tmp.name, "report.md")
        res = self.run_pipeline(routes_pass(), responses(), out_path=out)
        paths = [out] + [os.path.join(d, n) for d, _, names in os.walk(res.run_dir) for n in names]
        for p in paths:
            with open(p, "rb") as f:
                data = f.read()
            for k in KEYS.values():
                self.assertNotIn(k.encode(), data, p)

    def test_prose_has_no_digits_outside_numbers_and_ids(self):
        res = self.run_pipeline(routes_noindex(), responses(C_TEXT))
        body = res.text.split("## Recommendation", 1)[1].split("## Measurements", 1)[0]
        body = re.sub(r"\b(cap|pc|clm|dec)_[a-z0-9_-]+_[0-9a-f]{16}\b|\b(fct|src)_[0-9a-f]{16}\b", "", body)
        body = re.sub(r"https?://\S+", "", body)
        self.assertIsNone(re.search(r"\d", body), body)


class Refusals(PipelineCase):
    def test_live_transport_refused(self):
        with self.assertRaises(pipeline.PipelineError):
            self.run_pipeline(routes_pass(), None, transport=UrllibTransport())
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, "runs1")))

    def test_non_fixture_fetcher_refused(self):
        with self.assertRaises(pipeline.PipelineError):
            self.run_pipeline(routes_pass(), responses(), fetcher=lambda url, ua: None)


class MissingNOrIds(PipelineCase):
    def setUp(self):
        super().setUp()
        self.res = self.run_pipeline(routes_pass(), responses())
        self.index, self.dec = self.decision(self.res)

    def tampered(self, field, value):
        dec = copy.deepcopy(self.dec)
        if value is None:
            del dec["numbers"][0][field]
        else:
            dec["numbers"][0][field] = value
        return dec

    def test_stored_number_without_n_refused(self):
        with self.assertRaises(R.ReportError) as cm:
            R.stored_numbers(self.tampered("n", None))
        self.assertEqual(cm.exception.code, "E_SCHEMA")

    def test_stored_number_with_empty_ids_refused(self):
        with self.assertRaises(R.ReportError):
            R.stored_numbers(self.tampered("evidence_ids", []))

    def test_stored_number_with_non_int_n_refused(self):
        with self.assertRaises(R.ReportError):
            R.stored_numbers(self.tampered("n", "six"))

    def test_numbers_list_missing_refused(self):
        dec = copy.deepcopy(self.dec)
        del dec["numbers"]
        with self.assertRaises(R.ReportError):
            R.stored_numbers(dec)

    def test_report_number_with_unknown_id_fails_render(self):
        good = R.build_report(self.index, self.res.decision_id)
        num = next(f for b in good.blocks for f in b.fragments if isinstance(f, number.Number))
        bad = dataclasses.replace(num, evidence_ids=("cap_openai_0000000000000000",) + tuple(num.evidence_ids[1:]))
        blocks = tuple(render.Block(b.heading, tuple(bad if f is num else f for f in b.fragments))
                       for b in good.blocks)
        with self.assertRaises(RenderError):
            render.render_text(render.Report(good.title, blocks, decision_ids=good.decision_ids), self.index)

    def test_unknown_decision_refused(self):
        with self.assertRaises(R.ReportError):
            R.build_report(self.index, "dec_site_0000000000000000")

    def test_latest_decision_id(self):
        self.assertEqual(R.latest_decision_id(self.index), self.res.decision_id)


class ReportCli(PipelineCase):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(["report"] + list(args))
        return rc, out.getvalue(), err.getvalue()

    def test_report_to_stdout_matches_pipeline(self):
        res = self.run_pipeline(routes_pass(), responses())
        self.assertEqual(self.cli(res.run_dir), (0, res.text, ""))

    def test_report_to_file_refuses_overwrite(self):
        res = self.run_pipeline(routes_pass(), responses())
        out = os.path.join(self._tmp.name, "r.md")
        self.assertEqual(self.cli(res.run_dir, "--out", out)[0], 0)
        rc, _, err = self.cli(res.run_dir, "--out", out)
        self.assertEqual(rc, 2)
        self.assertIn("exists", err)

    def test_invalid_run_refused(self):
        res = self.run_pipeline(routes_pass(), responses())
        with open(os.path.join(res.run_dir, "decisions.jsonl"), "ab") as f:
            f.write(b"{}\n")
        rc, out, err = self.cli(res.run_dir)
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("does not validate", err)

    def test_run_without_decision_refused(self):
        res = self.run_pipeline(routes_pass(), responses())
        os.unlink(os.path.join(res.run_dir, "decisions.jsonl"))
        rc, _, err = self.cli(res.run_dir)
        self.assertEqual(rc, 2)
        self.assertIn("E_NO_DECISION", err)


if __name__ == "__main__":
    unittest.main()
