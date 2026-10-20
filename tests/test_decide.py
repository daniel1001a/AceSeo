"""W5-07 decision_cascade_r1_before_r0, the R2 to R4 firing paths, and V21, V23, V24.

Captures and answer texts are SYNTHETIC. Page-check bodies are the RECORDED
BoardFlight pages behind SYNTHETIC status lines (tests.test_pagechecks), served
by FixtureFetcher: nothing touches the network. Thresholds are the placeholder
registry (number.THRESHOLDS, PROGRESS Step 6).
"""

import tempfile
import unittest
from decimal import Decimal

from geo import claims as C
from geo import decide, number
from geo.decide import DecisionError
from geo.pagechecks import FetchError
from geo.validate import codes, load_valid_run, validate_run
from tests import geo_fixtures as fx
from tests.test_pagechecks import HTML, JFK, JFK_KEY, WWW, bf_routes, ok, recorded

ROBOTS_OPEN = b"User-agent: *\nDisallow: /api/\n"
C_TEXT = "BoardFlight covers 40 US airports."
SITE = ("www.boardflight.com",)


def routes_pass():
    return bf_routes(robots=ROBOTS_OPEN)


def routes_noindex(**over):
    return bf_routes(robots=ROBOTS_OPEN, **dict(
        {JFK: ok(recorded("airport_jfk.html"), HTML + [["x-robots-tag", "noindex"]])}, **over))


def routes_timeout():
    return bf_routes(robots=ROBOTS_OPEN, **{JFK: FetchError("timeout")})


def results(dec):
    return [(e["rule_id"], e["result"]) for e in dec["evaluations"]]


class DecideCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run = fx.Run(self._tmp.name, key_content=(JFK_KEY,))

    def tearDown(self):
        self._tmp.cleanup()

    def captures(self, engines=("anthropic", "openai"), prompts=("p_01", "p_02"), repeats=3, texts=None, start=0,
                 **kw):
        out = []
        for e in engines:
            for p in prompts:
                for i in range(start, repeats):
                    text = (texts or {}).get((e, p, i))
                    out.append(self.run.add_capture(e, p, i, answer_text=text, **kw))
        return out

    def add_claims(self, caps):
        for rec in C.claims_for_run(self.run.manifest, caps, self.run.facts_doc, self.run.tick()):
            self.run.append(rec)

    def decide(self):
        dec = self.run.add_decision()
        self.assertEqual(validate_run(self.run.dir, secrets=(fx.SECRET,)), [])
        return dec

    def assertOutcome(self, dec, outcome, fired, hypothesis):
        self.assertEqual((dec["outcome"], dec["fired_rule_id"], dec["hypothesis"]), (outcome, fired, hypothesis))
        self.assertEqual([e["rule_id"] for e in dec["evaluations"]], list(decide.ORDER))
        self.assertIn("A7", dec["assumption_refs"])
        self.assertEqual(dec["thresholds_snapshot"], number.threshold_values())


class W5_07(DecideCase):
    def test_a_seo_failure_wins_with_thin_captures(self):
        self.run.add_page_checks(routes_noindex())
        caps = self.captures(engines=("openai",), repeats=2, texts={("openai", "p_01", 0): C_TEXT})
        self.add_claims(caps)
        dec = self.decide()
        self.assertOutcome(dec, "seo_first", "R1", True)
        self.assertEqual(dec["assumption_refs"], ["A6", "A7"])
        self.assertEqual(results(dec), [("R1", "fired"), ("R0", "not_evaluated"), ("R2", "not_evaluated"),
                                        ("R3", "not_evaluated"), ("R4", "not_evaluated")])
        [bf] = [n for n in dec["numbers"] if n["statistic_id"] == "blocking_fail.key_pages"]
        self.assertEqual(bf["value"], len(bf["hit_ids"]))
        self.assertTrue(bf["hit_ids"] and all(i.startswith("pc_noindex_") for i in bf["hit_ids"]))

    def test_a0_seo_failure_with_zero_captures(self):
        self.run.add_page_checks(routes_noindex())
        dec = self.decide()
        self.assertOutcome(dec, "seo_first", "R1", True)
        self.assertNotEqual(dec["fired_rule_id"], "R0")

    def test_b_thin_captures_with_passing_pages(self):
        self.run.add_page_checks(routes_pass())
        self.captures(repeats=2)
        dec = self.decide()
        self.assertOutcome(dec, "insufficient_evidence", "R0", False)
        self.assertEqual(results(dec)[:2], [("R1", "not_fired"), ("R0", "fired")])
        self.assertEqual(dec["evaluations"][1]["reason_code"], "engines_below_minimum")
        self.assertIn(("insufficient", "below_min_n"),
                      {(i["item"], i["reason_code"]) for i in dec["not_checked"]})

    def test_c_uncheckable_key_page_stops_the_cascade(self):
        self.run.add_page_checks(routes_timeout())
        self.captures()
        dec = self.decide()
        self.assertOutcome(dec, "insufficient_evidence", "R0", False)
        r1, r0 = dec["evaluations"][:2]
        self.assertEqual((r1["result"], r1["reason_code"]), ("unknown", "page_checks_incomplete"))
        self.assertEqual((r0["result"], r0["reason_code"]), ("fired", "page_checks_incomplete"))
        self.assertEqual(results(dec)[2:], [("R2", "not_evaluated"), ("R3", "not_evaluated"),
                                            ("R4", "not_evaluated")])
        self.assertIn("page_check_not_checkable", {i["item"] for i in dec["not_checked"]})

    def test_fail_beats_not_checkable(self):
        self.run.add_page_checks(routes_noindex(**{WWW + "/llms.txt": FetchError("timeout")}))
        dec = self.decide()
        self.assertOutcome(dec, "seo_first", "R1", True)


class LaterRules(DecideCase):
    def setUp(self):
        super().setUp()
        self.run.add_page_checks(routes_pass())

    def test_r3_low_citation_in_two_vendors(self):
        self.captures()
        dec = self.decide()
        self.assertOutcome(dec, "geo_content", "R3", True)
        self.assertEqual(dec["assumption_refs"], ["A7"])
        engine = [n for n in dec["numbers"] if n["statistic_id"] == "citation_rate.engine"]
        self.assertEqual([(n["scope"]["engine"], n["value"], n["n"]) for n in engine],
                         [("anthropic", 0, 6), ("openai", 0, 6)])
        self.assertEqual([b["group_key"] for b in dec["confidence_basis"]],
                         ["site:www.boardflight.com", "vendor:anthropic", "vendor:openai"])

    def test_r4_when_both_vendors_cite_the_site(self):
        self.captures(hosts=SITE)
        dec = self.decide()
        self.assertOutcome(dec, "no_action", "R4", False)
        self.assertEqual(dec["evaluations"][3]["reason_code"], "citation_not_low")

    def test_r3_needs_every_vendor_low(self):
        self.captures(engines=("openai",), hosts=SITE)
        self.captures(engines=("anthropic",))
        dec = self.decide()
        self.assertOutcome(dec, "no_action", "R4", False)

    def test_r2_reproduced_contradiction(self):
        texts = {("openai", "p_01", 0): C_TEXT, ("anthropic", "p_02", 1): C_TEXT}
        caps = self.captures(texts=texts)
        self.add_claims(caps)
        dec = self.decide()
        self.assertOutcome(dec, "geo_fix_facts", "R2", False)
        r2 = dec["evaluations"][2]
        self.assertEqual(r2["reason_code"], "contradiction_reproduced")
        self.assertEqual(len([i for i in r2["input_ids"] if i.startswith("clm_")]), 2)
        self.assertEqual(len([i for i in r2["input_ids"] if i.startswith("cap_")]), 2)

    def test_single_contradiction_is_not_reproduced(self):
        caps = self.captures(texts={("openai", "p_01", 0): C_TEXT})
        self.add_claims(caps)
        dec = self.decide()
        self.assertEqual(dec["evaluations"][2]["result"], "not_fired")
        self.assertEqual(dec["fired_rule_id"], "R3")

    def test_one_vendor_sufficient_is_r0(self):
        self.captures(engines=("openai",))
        dec = self.decide()
        self.assertOutcome(dec, "insufficient_evidence", "R0", False)

    def test_failed_attempt_is_excluded_not_counted(self):
        bad = self.run.add_capture("openai", "p_01", 0, status="failed", error_class="timeout")
        self.run.add_capture("openai", "p_01", 0, attempt=2)
        self.captures(engines=("openai",), prompts=("p_02",))
        self.captures(engines=("openai",), prompts=("p_01",), repeats=3, start=1)
        self.captures(engines=("anthropic",))
        dec = self.decide()
        [n] = [n for n in dec["numbers"] if n["statistic_id"] == "citation_rate.engine_prompt"
               and n["scope"] == {"engine": "openai", "prompt_id": "p_01"}]
        self.assertEqual(n["excluded"], [[bad["id"], "failed"]])
        self.assertNotIn(bad["id"], n["evidence_ids"])

    def test_deterministic(self):
        self.captures()
        index = load_valid_run(self.run.dir)
        self.assertEqual(decide.decide(index, fx.ts(900)), decide.decide(index, fx.ts(900)))

    def test_numbers_round_trip(self):
        self.captures()
        dec = decide.decide(load_valid_run(self.run.dir), fx.ts(900))
        for d in dec["numbers"]:
            self.assertEqual(number.to_dict(number.from_dict(d)), d)
        cap = next(i for i in dec["input_ids"] if i.startswith("cap_"))
        money = number.build("cost_total.run", "money", Decimal("0.0125"), [cap], window=(fx.T0, fx.T0),
                             basis_labels=("Measured",))
        self.assertEqual(number.from_dict(number.to_dict(money)), money)


class Refusals(DecideCase):
    def test_threshold_mismatch_refused(self):
        run = fx.Run(self._tmp.name + "/t", key_content=(JFK_KEY,), thresholds={"N_MIN_REPEATS": 3})
        run.add_page_checks(routes_pass())
        with self.assertRaises(DecisionError) as cm:
            decide.decide(load_valid_run(run.dir), run.tick())
        self.assertEqual(cm.exception.code, "E_THRESHOLDS")

    def test_no_page_checks_refused(self):
        self.captures()
        with self.assertRaises(DecisionError) as cm:
            decide.decide(load_valid_run(self.run.dir), self.run.tick())
        self.assertEqual(cm.exception.code, "E_NO_PAGE_CHECKS")


class Validator(DecideCase):
    def setUp(self):
        super().setUp()
        self.run.add_page_checks(routes_pass())
        self.captures()
        self.good = decide.decide(load_valid_run(self.run.dir), fx.ts(900))

    def bad(self, **overrides):
        self.run.add_decision(**overrides)
        return codes(validate_run(self.run.dir))

    def test_good_validates(self):
        self.run.add_decision()
        self.assertEqual(validate_run(self.run.dir), [])

    def test_outcome_mismatch(self):
        self.assertEqual(self.bad(outcome="no_action"), ["E_DECISION"])

    def test_fired_rule_mismatch(self):
        self.assertEqual(self.bad(fired_rule_id="R4"), ["E_DECISION"])

    def test_evaluation_order(self):
        self.assertEqual(self.bad(evaluations=list(reversed(self.good["evaluations"]))), ["E_DECISION"])

    def test_hypothesis(self):
        self.assertEqual(self.bad(hypothesis=False), ["E_DECISION"])

    def test_missing_a7(self):
        self.assertEqual(self.bad(assumption_refs=["A6"]), ["E_DECISION"])

    def test_missing_a6_when_r1_fired(self):
        tmp = fx.Run(self._tmp.name + "/r1", key_content=(JFK_KEY,))
        tmp.add_page_checks(routes_noindex())
        tmp.add_decision(assumption_refs=["A7"])
        self.assertEqual(codes(validate_run(tmp.dir)), ["E_DECISION"])

    def test_rule_set_version(self):
        self.assertEqual(self.bad(rule_set_version="test-1"), ["E_DECISION"])

    def test_thresholds_snapshot(self):
        snap = dict(self.good["thresholds_snapshot"], T_LOW_PERCENT=50)
        self.assertEqual(self.bad(thresholds_snapshot=snap), ["E_DECISION"])

    def test_not_checked_lacks_baseline(self):
        items = [i for i in self.good["not_checked"] if i["item"] != "consumer_ui_answers"]
        self.assertEqual(self.bad(not_checked=items), ["E_NOT_CHECKED"])

    def test_not_checked_empty(self):
        self.assertEqual(self.bad(not_checked=[]), ["E_NOT_CHECKED"])

    def test_unresolved_id(self):
        basis = self.good["confidence_basis"] + [{"group_key": "x", "evidence_ids": ["cap_openai_0000000000000000"]}]
        self.assertEqual(self.bad(confidence_basis=basis), ["E_REF_UNRESOLVED"])

    def test_unresolved_input_id(self):
        evals = [dict(e) for e in self.good["evaluations"]]
        evals[3]["input_ids"] = sorted(evals[3]["input_ids"] + ["cap_openai_0000000000000000"])
        union = sorted({i for e in evals for i in e["input_ids"]})
        self.assertEqual(self.bad(evaluations=evals, input_ids=union), ["E_REF_UNRESOLVED"])

    def test_stored_number_missing_n(self):
        nums = [dict(n) for n in self.good["numbers"]]
        del nums[0]["n"]
        self.assertEqual(self.bad(numbers=nums), ["E_SCHEMA"])

    def test_stored_number_missing_ids(self):
        nums = [dict(n) for n in self.good["numbers"]]
        nums[0]["evidence_ids"] = []
        self.assertEqual(self.bad(numbers=nums), ["E_SCHEMA"])

    def test_why_cites_outside_input_ids(self):
        why = self.good["why"] + [{"template_id": "R3.citation_low_in_vendors", "evidence_ids": ["pc_x_0"]}]
        self.assertIn("E_DECISION", self.bad(why=why))


if __name__ == "__main__":
    unittest.main()
