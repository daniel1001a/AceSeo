"""The committed SYNTHETIC example (examples/synthetic) matches a fresh rebuild,
and the minimal input templates (examples/minimal) load and plan."""

import contextlib
import io
import os
import tempfile
import unittest

from geo import cli
from geo import facts as F
from geo.canonical import strict_load_path
from geo.claims import match_text
from geo.validate import validate_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "synthetic")
MINIMAL = os.path.join(ROOT, "examples", "minimal")


def _load_make_example():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_example", os.path.join(ROOT, "examples", "make_example.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(top):
    out = {}
    for d, _, names in os.walk(top):
        for n in names:
            p = os.path.join(d, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, top)] = f.read()
    return out


class SyntheticExample(unittest.TestCase):
    def test_committed_copy_matches_rebuild(self):
        mod = _load_make_example()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "synthetic")
            res = mod.build(out)
            self.assertEqual(validate_run(res.run_dir), [])
            self.assertEqual(_tree(os.path.join(out, "runs")), _tree(os.path.join(EXAMPLE, "runs")))
            with open(os.path.join(out, "report.md"), "rb") as a, open(os.path.join(EXAMPLE, "report.md"), "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_refuses_existing_out(self):
        with self.assertRaises(FileExistsError):
            _load_make_example().build(EXAMPLE)


class MinimalInputs(unittest.TestCase):
    def test_facts_pass_runtime_check(self):
        doc = strict_load_path(os.path.join(MINIMAL, "facts.json"))
        self.assertEqual(F.runtime_problems(doc), [])
        self.assertTrue({f["key"] for f in doc["facts"]} <= set(F.MATCHED_KEYS))

    def test_matcher_reads_minimal_facts(self):
        doc = strict_load_path(os.path.join(MINIMAL, "facts.json"))
        specs = match_text("Example Co is free to use. example.com is no longer operating.", doc)
        self.assertEqual([(s.fact_key, s.verdict) for s in specs],
                         [("llms.offer.is_free", "matched"), ("site_status", "contradicted")])

    def test_dry_run_with_minimal_inputs(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(["collect", "--prompts", os.path.join(MINIMAL, "prompts.json"),
                           "--facts", os.path.join(MINIMAL, "facts.json"), "--cap-usd", "1",
                           "--mention-term", "Example Co"], environ={})
        self.assertEqual(rc, 0)
        self.assertIn("3 prompts x 3 repeats x 2 engines", out.getvalue())


class RuntimeFactsCheck(unittest.TestCase):
    def test_problems(self):
        self.assertEqual(F.runtime_problems([]), ["the facts file must be a JSON object"])
        p = F.runtime_problems({"site": {"name": "X"}, "facts": [{"key": "a"}, {"key": "b", "value": 1},
                                                               {"key": "b", "value": 2}]})
        self.assertEqual(len(p), 3)
        self.assertIn("site.hosts", p[0])
        self.assertIn("facts[0]", p[1])
        self.assertIn("duplicate fact keys: b", p[2])

    def test_sample_passes(self):
        self.assertEqual(F.runtime_problems(strict_load_path(F.SAMPLE_PATH)), [])

    def test_cli_refuses_bad_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "facts.json")
            with open(bad, "w") as f:
                f.write('{"site": {"name": "X", "hosts": ["x.com"]}, "facts": {}}')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = cli.main(["collect", "--prompts", os.path.join(MINIMAL, "prompts.json"), "--facts", bad, "--cap-usd", "1", "--mention-term", "X"], environ={})
            self.assertEqual(rc, 2)
            self.assertIn("facts must be a list", err.getvalue())


if __name__ == "__main__":
    unittest.main()
