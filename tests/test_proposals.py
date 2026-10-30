"""LLM proposals (geo/proposals.py): stored beside the run, listed, never counted;
confirm turns one into a match rule in the user's facts file.

Answer texts and facts are SYNTHETIC.
"""

import contextlib
import copy
import io
import json
import os
import shutil
import tempfile
import unittest

from geo import cli, decide, proposals, render
from geo import report as report_mod
from geo.canonical import canonical_bytes
from geo.claims import claims_for_run, match_text
from geo.store import PROPOSALS_FILE
from geo.validate import codes, load_valid_run, validate_run
from tests import geo_fixtures as fx
from tests.test_decide import routes_pass

ACME = {
    "schema_version": "1.0.0",
    "site": {"name": "Acme Notes", "canonical_origin": "https://acmenotes.io", "hosts": ["acmenotes.io"]},
    "facts": [
        {"key": "site_status", "value": "live", "value_type": "enum"},
        {"key": "offer.has_api", "value": True, "value_type": "boolean",
         "match": {"positive": ["has an API"], "negative": ["has no API"]}},
        {"key": "plan.count", "value": 3, "value_type": "integer"},
    ],
}
ANSWER = "Acme Notes ships an export API for all users. It has 3 tiers. Acme Notes is free."
QUOTE = "Acme Notes ships an export API for all users."


class ProposalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        run = fx.Run(self.tmp, facts=ACME)
        self.cap = run.add_capture("anthropic", "p_01", 0, answer_text=ANSWER)
        self.failed = run.add_capture("openai", "p_01", 0, status="failed", error_class="timeout")
        for rec in claims_for_run(run.manifest, [self.cap], ACME, run.tick()):
            run.append(rec)
        run.add_page_checks(routes_pass())
        run.add_decision()
        self.run = run
        self.dir = run.dir
        self.created = run.tick()
        self.facts_path = os.path.join(self.tmp, "facts.json")
        with open(self.facts_path, "w") as f:
            json.dump(ACME, f)

    def doc(self, **over):
        p = {"capture_id": self.cap["id"], "quote": QUOTE, "fact_key": "offer.has_api", "asserted_value": True}
        p.update(over)
        return {"model": "claude (subscription, Claude Code)", "proposals": [p]}

    def report_text(self):
        index = load_valid_run(self.dir)
        rep = report_mod.build_report(index, report_mod.latest_decision_id(index))
        return render.render_text(rep, index)

    def propose(self, **over):
        return proposals.import_proposals(self.dir, self.doc(**over), self.created)


class Import(ProposalCase):
    def test_stored_beside_the_run_and_valid(self):
        [(rec, _, cmp)] = self.propose()
        self.assertEqual((rec["matcher"], rec["verdict"], rec["statement"]), ("llm", "needs_review", QUOTE))
        self.assertEqual(cmp, "matched (normalized)")
        self.assertEqual(validate_run(self.dir), [])
        index = load_valid_run(self.dir)
        self.assertEqual([r["id"] for r in index.proposals], [rec["id"]])
        self.assertNotIn(rec["id"], {r["id"] for r in index.records})

    def test_comparison_is_computed_by_code(self):
        [(_, _, cmp)] = self.propose(asserted_value=False)
        self.assertEqual(cmp, "contradicted (value_mismatch)")
        [(_, _, cmp)] = proposals.build_proposals(
            load_valid_run(self.dir), ACME, self.doc(fact_key=None, asserted_value=None), self.created)
        self.assertEqual(cmp, "no fact")

    def test_cannot_change_a_decision(self):
        before_index = load_valid_run(self.dir)
        before = self.report_text()
        self.propose(asserted_value=False)
        after_index = load_valid_run(self.dir)
        self.assertEqual(decide.decide(after_index, self.created), decide.decide(before_index, self.created))
        after = self.report_text()
        section = after.index("\n## LLM-proposed claims (not counted)")
        footer = after.index("\n---\n")
        self.assertEqual(after[:section] + after[footer:], before)
        self.assertIn(QUOTE, after[section:footer])

    def test_report_without_proposals_has_no_section(self):
        self.assertNotIn("LLM-proposed", self.report_text())

    def test_refusals(self):
        cases = [
            (dict(quote="Acme Notes is closed."), "not in the answer"),
            (dict(fact_key="offer.nope"), "not in the run's facts"),
            (dict(capture_id=self.failed["id"]), "not an ok capture"),
        ]
        for over, msg in cases:
            with self.assertRaisesRegex(proposals.ProposalError, msg):
                self.propose(**over)
        for bad in ({"proposals": []}, {"model": "x", "proposals": []},
                    {"model": "x", "proposals": [{"quote": QUOTE}]}):
            with self.assertRaises(proposals.ProposalError):
                proposals.import_proposals(self.dir, bad, self.created)
        self.assertFalse(os.path.exists(os.path.join(self.dir, PROPOSALS_FILE)))

    def test_same_proposal_twice_refused(self):
        self.propose()
        with self.assertRaisesRegex(proposals.ProposalError, "already in this run"):
            self.propose()

    def test_validator_rejects_tampering(self):
        [(rec, _, _)] = self.propose()
        path = os.path.join(self.dir, PROPOSALS_FILE)

        def rewrite(r):
            with open(path, "wb") as f:
                f.write(canonical_bytes(r) + b"\n")
            return codes(validate_run(self.dir))

        self.assertIn("E_SCHEMA", rewrite(dict(rec, matcher="rule")))
        self.assertIn("E_CLAIM_SPAN", rewrite(dict(rec, statement="Acme Notes ships nothing.")))
        self.assertIn("E_VERDICT_LLM", rewrite(dict(rec, verdict="matched", verdict_basis="normalized")))
        rule_claim = next(r for r in self.run.records if r["kind"] == "claim")
        self.assertIn("E_DUPLICATE_RECORD", rewrite(rule_claim))


class Confirm(ProposalCase):
    def test_boolean_phrase_becomes_a_rule(self):
        [(rec, _, _)] = self.propose()
        self.assertEqual([s for s in match_text(QUOTE, ACME) if s.fact_key], [])
        spec, doc = proposals.confirm_proposal(self.dir, rec["id"], self.facts_path, "ships an export API", "true")
        self.assertEqual((spec.fact_key, spec.verdict), ("offer.has_api", "matched"))
        with open(self.facts_path) as f:
            saved = json.load(f)
        self.assertEqual(saved, doc)
        fact = next(x for x in saved["facts"] if x["key"] == "offer.has_api")
        self.assertEqual(fact["match"]["positive"], ["has an API", "ships an export API"])
        self.assertEqual(validate_run(self.dir), [])

    def test_rule_that_would_not_decide_is_refused(self):
        # "It has 3 tiers." does not name the site, so no rule can decide it.
        [(rec, _, _)] = self.propose(quote="It has 3 tiers.", fact_key="plan.count", asserted_value=3)
        with self.assertRaisesRegex(proposals.ProposalError, "still does not decide"):
            proposals.confirm_proposal(self.dir, rec["id"], self.facts_path, "tiers")
        with open(self.facts_path) as f:
            self.assertEqual(json.load(f), ACME)

    def test_integer_phrase_becomes_a_unit_term(self):
        doc = copy.deepcopy(ACME)
        doc["facts"][1]["match"]["positive"].append("Acme Notes has 3 tiers")
        self.assertEqual(proposals._promote(doc["facts"][2], "tiers", None), {"unit_terms": ["tiers"]})
        with self.assertRaisesRegex(proposals.ProposalError, "takes no --value"):
            proposals._promote(doc["facts"][2], "tiers", "3")

    def test_refusals(self):
        [(rec, _, _)] = self.propose()
        rule_claim = next(r for r in self.run.records if r["kind"] == "claim")
        cases = [
            ((rule_claim["id"], "Acme Notes", "true"), "not an LLM proposal"),
            ((rec["id"], "export CSV", "true"), "part of the statement"),
            ((rec["id"], "ships an export API", None), "--value true"),
        ]
        for (cid, phrase, value), msg in cases:
            with self.assertRaisesRegex(proposals.ProposalError, msg):
                proposals.confirm_proposal(self.dir, cid, self.facts_path, phrase, value)
        with open(self.facts_path) as f:
            self.assertEqual(json.load(f), ACME)

    def test_cli(self):
        src = os.path.join(self.tmp, "proposals.json")
        with open(src, "w") as f:
            json.dump(self.doc(), f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["propose-claims", self.dir, "--from", src], clock=lambda: self.created), 0)
        claim_id = out.getvalue().split()[0]
        self.assertIn("against the fact: matched (normalized)", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["ledger", self.dir]), 0)
        self.assertIn("%s llm proposal, not counted (fact offer.has_api)" % claim_id, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["confirm", self.dir, claim_id, "--facts", self.facts_path,
                                       "--phrase", "ships an export API", "--value", "true"]), 0)
        self.assertIn("matched (normalized)", out.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["propose-claims", self.dir, "--from", src], clock=lambda: self.created), 2)
        self.assertIn("refused: ", err.getvalue())


if __name__ == "__main__":
    unittest.main()
