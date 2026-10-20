"""W5-03 claim_refs_and_verdict_downgrade, the rule matcher and PLAN 6.2 fixture 1.

Answer texts are SYNTHETIC. Facts are the BoardFlight sample (W5-03) or the
Step 4 loader output (for the three follow-up facts and the prior value).
"""

import json
import os
import tempfile
import unittest

from geo import claims as C
from geo import facts as F
from geo import ids
from geo.validate import codes, load_valid_run, validate_run
from tests import geo_fixtures as fx

C_OK_TEXT = "BoardFlight covers 40 US airports."
INACTIVE = os.path.join(fx.FIXTURES, "claims", "inactive-domain.json")


def sample_facts():
    with open(F.SAMPLE_PATH, "rb") as fh:
        return F.parse_facts(fh.read())


class ClaimRun(unittest.TestCase):
    facts = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run = fx.Run(self._tmp.name, facts=self.facts)
        self.c_ok = self.run.add_capture("openai", "p_09", 0, answer_text=C_OK_TEXT)
        self.c_failed = self.run.add_capture("anthropic", "p_09", 0, status="failed", error_class="timeout")

    def tearDown(self):
        self._tmp.cleanup()

    def claim(self, capture=None, **kw):
        cap = capture or self.c_ok
        text = cap["answer_text"]
        args = dict(span_start=0, span_end=len(text), statement=text, fact_key="llms.coverage.airport_count",
                    fact_value_snapshot=33, verdict="contradicted", verdict_basis="value_mismatch",
                    created_at=self.run.tick())
        if cap["status"] != "ok":
            args.update(span_end=1, statement="B")
        args.update(kw)
        rec = C.claim_record(self.run.manifest, cap, **args)
        self.run.append(rec)
        return rec

    def codes(self):
        return codes(validate_run(self.run.dir))


class W5_03(ClaimRun):
    def test_valid_claim(self):
        self.claim()
        self.assertEqual(validate_run(self.run.dir, secrets=(fx.SECRET,)), [])

    def test_case1_failed_capture(self):
        self.claim(self.c_failed)
        self.assertEqual(self.codes(), ["E_REF_CAPTURE"])

    def test_case1_unknown_capture(self):
        ghost = dict(self.c_ok, id="cap_openai_0000000000000000")
        self.claim(ghost)
        self.assertEqual(self.codes(), ["E_REF_CAPTURE"])

    def test_case2_fact_key_typo(self):
        self.claim(fact_key="llms.coverage.airport_count_typo")
        self.assertEqual(self.codes(), ["E_REF_FACT"])

    def test_case3_statement_differs_from_span(self):
        self.claim(statement="BoardFlight covers 41 US airports.")
        self.assertEqual(self.codes(), ["E_CLAIM_SPAN"])

    def test_case3_span_outside_answer(self):
        self.claim(span_end=len(C_OK_TEXT) + 1)
        self.assertEqual(self.codes(), ["E_CLAIM_SPAN"])

    def test_case4_matched_undecided(self):
        self.claim(verdict="matched", verdict_basis="undecided")
        self.assertEqual(self.codes(), ["E_VERDICT"])

    def test_case5_llm_contradicted(self):
        self.claim(matcher="llm")
        self.assertEqual(self.codes(), ["E_VERDICT_LLM"])

    def test_llm_needs_review_allowed(self):
        self.claim(matcher="llm", verdict="needs_review", verdict_basis="undecided", fact_key=None,
                   fact_value_snapshot=None)
        self.assertEqual(self.codes(), [])

    def test_case6_rule_matcher_contradicted_then_matched(self):
        facts = self.run.facts_doc
        self.assertEqual(C.match_text(C_OK_TEXT, facts),
                         [C.Spec(0, len(C_OK_TEXT), "airport_count", "llms.coverage.airport_count",
                                 "contradicted", "value_mismatch")])
        [sp] = C.match_text("BoardFlight covers 33 US airports.", facts)
        self.assertEqual((sp.verdict, sp.verdict_basis), ("matched", "exact"))

    def test_case6_claims_from_capture_validate(self):
        recs = C.claims_for_capture(self.run.manifest, self.c_ok, self.run.facts_doc, self.run.tick())
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["statement"], C_OK_TEXT)
        self.assertEqual(recs[0]["fact_ref"], ids.fct_ref(self.run.manifest["facts_sha256"],
                                                          "llms.coverage.airport_count"))
        self.assertTrue(recs[0]["id"].startswith("clm_openai_"))
        for r in recs:
            self.run.append(r)
        self.assertEqual(validate_run(self.run.dir), [])
        index = load_valid_run(self.run.dir)
        self.assertEqual(index.lookup(recs[0]["id"]).kind, "claim")

    def test_case7_dozens_is_needs_review(self):
        [sp] = C.match_text("BoardFlight covers dozens of US airports.", self.run.facts_doc)
        self.assertEqual((sp.verdict, sp.verdict_basis, sp.fact_key), ("needs_review", "undecided", None))

    def test_no_claims_for_failed_capture(self):
        self.assertEqual(C.claims_for_capture(self.run.manifest, self.c_failed, self.run.facts_doc,
                                              self.run.tick()), [])


class FieldRules(ClaimRun):
    def test_facts_sha_differs(self):
        self.claim(facts_sha256="0" * 64)
        self.assertEqual(self.codes(), ["E_REF_FACT"])

    def test_fact_ref_does_not_recompute(self):
        self.claim(fact_ref="fct_0000000000000000")
        self.assertEqual(self.codes(), ["E_REF_FACT"])

    def test_value_snapshot_differs(self):
        self.claim(fact_value_snapshot=34)
        self.assertEqual(self.codes(), ["E_REF_FACT"])

    def test_value_snapshot_type_strict(self):
        self.claim(fact_value_snapshot="33")
        self.assertEqual(self.codes(), ["E_REF_FACT"])

    def test_decided_verdict_needs_fact_key(self):
        self.claim(fact_key=None, fact_value_snapshot=None)
        self.assertEqual(self.codes(), ["E_REF_FACT"])

    def test_unknown_verdict(self):
        self.claim(verdict="wrong_entity", verdict_basis="undecided")
        self.assertEqual(self.codes(), ["E_VERDICT"])

    def test_bad_matcher(self):
        self.claim(matcher="regex")
        self.assertEqual(self.codes(), ["E_SCHEMA"])

    def test_missing_field(self):
        rec = self.claim()
        del rec["matcher_version"]
        self.run.rewrite_records("claims.jsonl", [rec])
        self.assertIn("E_SCHEMA", self.codes())


class Matcher(unittest.TestCase):
    def setUp(self):
        self.facts = F.build_boardflight()

    def one(self, text):
        specs = C.match_text(text, self.facts)
        self.assertEqual(len(specs), 1, specs)
        sp = specs[0]
        self.assertEqual((sp.span_start, sp.span_end), (0, len(text)))
        return sp.fact_key, sp.verdict, sp.verdict_basis

    def test_inactive_domain_fixture_is_contradicted(self):
        with open(INACTIVE, encoding="utf-8") as fh:
            fixture = json.load(fh)
        self.assertFalse(fixture["counts_in_rates"])
        self.assertEqual(fixture["source"]["commit"], "cc93f59931c42695d6ea306905fd517426ae8a3e")
        exp = fixture["expected"]
        self.assertEqual(self.one(fixture["text"]), (exp["fact_key"], exp["verdict"], exp["verdict_basis"]))
        self.assertEqual(F.facts_by_key(self.facts)["site_status"]["value"], "live")

    def test_inactive_with_sample_facts_too(self):
        with open(INACTIVE, encoding="utf-8") as fh:
            text = json.load(fh)["text"]
        [sp] = C.match_text(text, sample_facts())
        self.assertEqual(sp.verdict, "contradicted")

    def test_site_status_variants(self):
        for text in ("BoardFlight is no longer operating.", "boardflight.com is parked.",
                     "BoardFlight is currently down.", "BoardFlight 目前已停止營運。", "BoardFlight 已停用。"):
            self.assertEqual(self.one(text), ("site_status", "contradicted", "value_mismatch"), text)
        self.assertEqual(self.one("BoardFlight is live."), ("site_status", "matched", "normalized"))

    def test_other_domain_is_needs_review(self):
        # W3 3.3: claims about boardflight.app are wrong_entity, never contradicted.
        for text in ("boardflight.app is an inactive domain.",
                     "BoardFlight (boardflight.app) is no longer operating."):
            self.assertEqual(self.one(text), (None, "needs_review", "undecided"), text)

    def test_no_site_mention_is_needs_review(self):
        self.assertEqual(self.one("The site is inactive."), (None, "needs_review", "undecided"))

    def test_conflicting_status_is_needs_review(self):
        self.assertEqual(self.one("BoardFlight was inactive but is live now."), (None, "needs_review", "undecided"))

    def test_hedged_count_is_needs_review(self):
        for text in ("BoardFlight covers about 33 US airports.", "BoardFlight covers over 30 US airports."):
            self.assertEqual(self.one(text), (None, "needs_review", "undecided"), text)
        self.assertEqual(self.one("BoardFlight covers 33 U.S. airports."),
                         ("llms.coverage.airport_count", "matched", "exact"))

    def test_is_free(self):
        self.assertEqual(self.one("BoardFlight is free to use."), ("llms.offer.is_free", "matched", "normalized"))
        self.assertEqual(self.one("BoardFlight requires a paid subscription."),
                         ("llms.offer.is_free", "contradicted", "value_mismatch"))

    def test_live_queue_data(self):
        key = "llms.data.uses_live_queue_data"
        self.assertEqual(self.one("BoardFlight shows real-time TSA wait times."), (key, "contradicted", "value_mismatch"))
        self.assertEqual(self.one("BoardFlight does not use live queue data."), (key, "matched", "normalized"))

    def test_same_as_prior_value_is_outdated(self):
        key = "jsonld.organization.same_as"
        self.assertEqual(self.one("BoardFlight has no social media profiles."), (key, "outdated", "prior_value"))
        self.assertEqual(self.one("BoardFlight has a LinkedIn page."), (key, "matched", "normalized"))

    def test_missing_fact_is_unsupported(self):
        # The W3 sample has no is_free fact; the Step 4 loader adds it.
        [sp] = C.match_text("BoardFlight is free to use.", sample_facts())
        self.assertEqual((sp.fact_key, sp.verdict, sp.verdict_basis), (None, "unsupported", "no_fact"))

    def test_no_fact_topic_is_unsupported(self):
        self.assertEqual(self.one("BoardFlight was founded in 2024."), (None, "unsupported", "no_fact"))

    def test_two_topics_in_one_sentence_is_needs_review(self):
        self.assertEqual(self.one("BoardFlight is free to use and covers 33 US airports."),
                         (None, "needs_review", "undecided"))

    def test_sentences_and_no_claims(self):
        text = "Airports vary. BoardFlight covers 33 US airports. See boardflight.com for more."
        specs = C.match_text(text, self.facts)
        self.assertEqual([text[s.span_start:s.span_end] for s in specs], ["BoardFlight covers 33 US airports."])
        self.assertEqual(C.match_text("", self.facts), [])

    def test_unicode_digits_are_not_numbers(self):
        self.assertEqual(self.one("BoardFlight covers ٣٣ US airports."), (None, "needs_review", "undecided"))


class LoaderFactsRun(ClaimRun):
    facts = F.build_boardflight()

    def test_outdated_and_list_snapshot_validate(self):
        cap = self.run.add_capture("openai", "p_04", 0, answer_text=(
            "BoardFlight has no social media profiles. BoardFlight is free to use. "
            "boardflight.app is inactive. BoardFlight was founded in 2024."))
        recs = C.claims_for_capture(self.run.manifest, cap, self.run.facts_doc, self.run.tick())
        self.assertEqual([r["verdict"] for r in recs], ["outdated", "matched", "needs_review", "unsupported"])
        self.assertIsInstance(recs[0]["fact_value_snapshot"], list)
        for r in recs:
            self.run.append(r)
        self.assertEqual(validate_run(self.run.dir), [])


if __name__ == "__main__":
    unittest.main()
