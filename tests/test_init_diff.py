"""aceseo init (drafts from public pages) and aceseo diff (two runs).

init is served the RECORDED BoardFlight home page and llms.txt behind SYNTHETIC
status lines by FixtureFetcher; nothing touches the network. Runs for diff are
SYNTHETIC captures over the same fixtures as tests.test_decide.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from geo import cli, diff
from geo import init as init_mod
from geo.claims import claims_for_run
from geo.facts import runtime_problems
from geo.pagechecks import FetchError, FixtureFetcher
from geo.validate import load_valid_run
from step0.request_builder import load_prompts
from tests import geo_fixtures as fx
from tests.test_decide import routes_noindex, routes_pass
from tests.test_pagechecks import HTML, ok, recorded

HOME = "https://www.boardflight.com/"
LLMS = "https://www.boardflight.com/llms.txt"


def init_routes(**over):
    routes = {HOME: ok(recorded("home.html"), HTML),
              LLMS: ok(recorded("llms.txt"), [["content-type", "text/plain"]])}
    routes.update(over)
    return routes


class Init(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_draft_from_recorded_pages(self):
        facts, prompts, notes = init_mod.draft(HOME, FixtureFetcher(init_routes()))
        self.assertEqual(facts["site"]["name"], "BoardFlight")
        self.assertEqual(facts["site"]["canonical_origin"], "https://www.boardflight.com")
        self.assertEqual(facts["site"]["hosts"], ["www.boardflight.com", "boardflight.com"])
        by_key = {f["key"]: f for f in facts["facts"]}
        self.assertEqual(by_key["site_status"]["value"], "live")
        self.assertEqual(runtime_problems(facts), [])
        texts = [p["text"] for p in load_prompts(prompts)]
        self.assertEqual(len(texts), len(init_mod.PROMPT_TEMPLATES))
        self.assertIn("Is www.boardflight.com a legitimate and active website?", texts)
        self.assertTrue(any(n.startswith("llms.txt found: BoardFlight turns") for n in notes), notes)

    def test_name_fallbacks(self):
        self.assertEqual(init_mod.read_home('<meta property="og:site_name" content="Acme Notes">', "a.io")[:2],
                         ("Acme Notes", "og:site_name"))
        self.assertEqual(init_mod.read_home("<title>Acme Notes | Home</title>", "a.io")[:2], ("Acme Notes", "<title>"))
        self.assertEqual(init_mod.read_home("", "a.io")[:2], ("a.io", "hostname"))
        ld = ('<script type="application/ld+json">{"@graph":[{"@type":"Organization","name":"Acme",'
              '"sameAs":["https://github.com/acme","not a url"]}]}</script><title>Other</title>')
        self.assertEqual(init_mod.read_home(ld, "a.io"),
                         ("Acme", "JSON-LD Organization name", ["https://github.com/acme"]))

    def test_error_status_and_missing_llms(self):
        routes = init_routes(**{HOME: ok(b"<title>Down</title>", HTML)})
        routes[HOME] = dict(routes[HOME], status=503)
        del routes[LLMS]
        facts, _, notes = init_mod.draft(HOME, FixtureFetcher(routes))
        self.assertEqual(facts["facts"], [{"key": "site_status", "value": "error", "value_type": "enum"}])
        self.assertIn("no llms.txt (HTTP 404 at %s)" % LLMS, notes)

    def test_refusals(self):
        with self.assertRaisesRegex(init_mod.InitError, "absolute http"):
            init_mod.draft("boardflight.com", FixtureFetcher({}))
        with self.assertRaisesRegex(init_mod.InitError, "could not fetch .*timeout"):
            init_mod.draft(HOME, FixtureFetcher({HOME: FetchError("timeout")}))

    def test_cli_writes_only_missing_files(self):
        out_dir = os.path.join(self.tmp, "site")
        os.makedirs(out_dir)
        kept = os.path.join(out_dir, "prompts.json")
        with open(kept, "w") as f:
            f.write("mine\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["init", HOME, "--dir", out_dir], fetcher=FixtureFetcher(init_routes())), 0)
        self.assertIn("kept existing %s" % kept, out.getvalue())
        with open(kept) as f:
            self.assertEqual(f.read(), "mine\n")
        with open(os.path.join(out_dir, "facts.json")) as f:
            self.assertEqual(json.load(f)["site"]["name"], "BoardFlight")


def make_run(root, hosts, routes, answer="BoardFlight covers 33 US airports.", facts=None):
    run = fx.Run(root, facts=facts)
    caps = [run.add_capture(engine, pid, r, hosts=hosts, answer_text=answer)
            for engine in sorted(run.snapshots) for pid in sorted(run.prompts) for r in range(run.manifest["repeats"])]
    for rec in claims_for_run(run.manifest, caps, run.facts_doc, run.tick()):
        run.append(rec)
    run.add_page_checks(routes)
    run.add_decision()
    return load_valid_run(run.dir)


class Diff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.a = make_run(os.path.join(self.tmp, "a"), ["www.boardflight.com"], routes_pass())

    def test_same_run_has_no_changes(self):
        text = diff.diff_text(self.a, self.a)
        self.assertEqual(text.count("- no change"), 3)
        self.assertNotIn(" -> ", text.split("outcome:")[1].split("\n", 1)[1])

    def test_changes_are_listed_and_stable(self):
        b = make_run(os.path.join(self.tmp, "b"), ["example.org"], routes_noindex(),
                     answer="BoardFlight covers 40 US airports.")
        text = diff.diff_text(self.a, b)
        self.assertEqual(text, diff.diff_text(self.a, b))
        self.assertIn("outcome: no_action (rule R4) -> seo_first (rule R1)", text)
        self.assertIn("- citation_rate.engine engine=anthropic: 30/30 -> 0/30", text)
        self.assertIn("- llms.coverage.airport_count: matched 60 -> contradicted 60", text)
        self.assertRegex(text, r"- noindex https://www\.boardflight\.com/airport/jfk: pass -> fail")

    def test_input_change_refused_unless_allowed(self):
        with open(fx.FACTS_PATH) as f:
            facts = json.load(f)
        facts["site"]["note"] = "changed"
        b = make_run(os.path.join(self.tmp, "b"), ["www.boardflight.com"], routes_pass(), facts=facts)
        with self.assertRaisesRegex(diff.DiffError, "different facts files"):
            diff.diff_text(self.a, b)
        self.assertIn("WARNING: the facts file changed", diff.diff_text(self.a, b, allow_input_change=True))

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["diff", self._dir(self.a), self._dir(self.a)]), 0)
        self.assertTrue(out.getvalue().startswith("# aceseo diff\n"))

    def _dir(self, index):
        return os.path.join(self.tmp, "a", index.manifest["run_id"])


if __name__ == "__main__":
    unittest.main()
