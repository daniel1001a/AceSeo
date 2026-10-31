"""Matcher v3: facts declared with a match block, on a site that is not BoardFlight.

Answer texts and facts are SYNTHETIC.
"""

import copy
import unittest

from geo import claims as C
from geo import facts as F

DOC = {
    "site": {"name": "Acme Notes", "hosts": ["acmenotes.io"]},
    "facts": [
        {"key": "site_status", "value": "live", "value_type": "enum"},
        {"key": "offer.has_api", "value": True, "value_type": "boolean",
         "match": {"subject_terms": ["API"], "positive": ["has an API", "offers an API", "public API"],
                   "negative": ["has no API", "does not offer an API", "no public API"]}},
        {"key": "plan.count", "value": 3, "value_type": "integer",
         "match": {"unit_terms": ["plans", "pricing plans"]}},
        {"key": "license", "value": "mit", "value_type": "enum", "enum_values": ["mit", "gpl"],
         "match": {"values": {"mit": ["MIT license", "MIT-licensed"], "gpl": ["GPL", "GNU General Public"]}}},
    ],
}


def one(text, doc=DOC):
    [sp] = C.match_text(text, doc)
    return sp.fact_key, sp.verdict, sp.verdict_basis


class DeclaredFacts(unittest.TestCase):
    def test_same_name_domain_elsewhere_downgrades_brand_only_claim(self):
        for text in ("Acme Notes has a public API. See acmenotes.app.",
                     "Website: acmenotes.app\nAcme Notes has a public API."):
            [sp] = C.match_text(text, DOC)
            self.assertEqual((sp.fact_key, sp.verdict), (None, "needs_review"))
            self.assertEqual(text[sp.span_start:sp.span_end], "Acme Notes has a public API.")

    def test_same_name_citation_downgrades_brand_only_claim(self):
        for text in ("Acme Notes has a public API.", "Acme Notes has no API."):
            [sp] = C.match_text(text, DOC, source_urls=["https://acmenotes.app/privacy"])
            self.assertEqual((sp.fact_key, sp.verdict), (None, "needs_review"))

    def test_explicit_host_can_disambiguate_but_pronoun_cannot(self):
        urls = ["https://acmenotes.app/"]
        [sp] = C.match_text("acmenotes.io has a public API.", DOC, source_urls=urls)
        self.assertEqual((sp.fact_key, sp.verdict), ("offer.has_api", "matched"))
        [sp] = C.match_text("acmenotes.io and acmenotes.app have a public API.", DOC)
        self.assertEqual((sp.fact_key, sp.verdict), (None, "needs_review"))
        [sp] = C.match_text("It has a public API.", DOC, context_text="Acme Notes has a public API.")
        self.assertEqual((sp.fact_key, sp.verdict), (None, "needs_review"))

    def test_citation_path_or_unrelated_host_does_not_confuse_entity(self):
        for url in ("https://docs.example/acmenotes.app", "https://acmenotes.io/", "https://example.org/"):
            [sp] = C.match_text("Acme Notes has a public API.", DOC, source_urls=[url])
            self.assertEqual((sp.fact_key, sp.verdict), ("offer.has_api", "matched"))

    def test_not_live_adjective_does_not_hit_site_status(self):
        doc = copy.deepcopy(DOC)
        doc["facts"].append({
            "key": "data.uses_live_queue_data", "value": False, "value_type": "boolean",
            "match": {"positive": [], "negative": ["not live measurements", "not live data"]},
        })
        for noun in ("measurements", "data"):
            text = "Acme Notes security wait times are estimates, not live %s." % noun
            self.assertEqual(one(text, doc), ("data.uses_live_queue_data", "matched", "normalized"))
            self.assertEqual(C.match_text(text, DOC), [])

    def test_not_live_predicate_still_contradicts(self):
        for text in ("The Acme Notes site is not live.", "Acme Notes is not live",
                     "Acme Notes is not live yet.", "Acme Notes is not live anymore.",
                     "Acme Notes is not live now."):
            self.assertEqual(one(text), ("site_status", "contradicted", "value_mismatch"), text)

    def test_boolean(self):
        self.assertEqual(one("Acme Notes has a public API."), ("offer.has_api", "matched", "normalized"))
        self.assertEqual(one("Acme Notes has no API."), ("offer.has_api", "contradicted", "value_mismatch"))
        self.assertEqual(one("Acme Notes does not offer an API for exports."),
                         ("offer.has_api", "contradicted", "value_mismatch"))

    def test_boolean_both_sides_is_undecided(self):
        self.assertEqual(one("Acme Notes has an API but no public API docs."), (None, "needs_review", "undecided"))

    def test_integer(self):
        self.assertEqual(one("Acme Notes offers 3 pricing plans."), ("plan.count", "matched", "exact"))
        self.assertEqual(one("Acme Notes has 4 paid plans."), ("plan.count", "contradicted", "value_mismatch"))
        for text in ("Acme Notes has about 3 plans.", "Acme Notes has 3+ plans.",
                     "Acme Notes has 3 or 4 plans."):
            self.assertEqual(one(text), (None, "needs_review", "undecided"), text)

    def test_integer_without_number_and_subject_is_no_claim(self):
        self.assertEqual(C.match_text("Acme Notes compares plans.", DOC), [])

    def test_enum(self):
        self.assertEqual(one("Acme Notes is MIT-licensed."), ("license", "matched", "normalized"))
        self.assertEqual(one("Acme Notes is released under the GPL."), ("license", "contradicted", "value_mismatch"))
        self.assertEqual(one("Acme Notes is MIT licensed, not GPL."), (None, "needs_review", "undecided"))

    def test_hyphen_and_space_are_equivalent(self):
        self.assertEqual(one("Acme Notes uses the MIT   license."), ("license", "matched", "normalized"))

    def test_phrases_are_literal(self):
        doc = copy.deepcopy(DOC)
        doc["facts"][1]["match"] = {"positive": ["a.i"], "negative": []}
        self.assertEqual(C.match_text("Acme Notes uses aXi.", doc), [])

    def test_prior_value_is_outdated(self):
        doc = copy.deepcopy(DOC)
        doc["facts"][2]["prior_values"] = [{"value": 2}]
        self.assertEqual(one("Acme Notes has 2 plans.", doc), ("plan.count", "outdated", "prior_value"))

    def test_no_match_block_is_not_matched(self):
        doc = copy.deepcopy(DOC)
        del doc["facts"][2]["match"]
        self.assertEqual(C.match_text("Acme Notes has 4 plans.", doc), [])
        self.assertNotIn("plan.count", C.matched_keys(doc))

    def test_matched_keys(self):
        self.assertEqual(C.matched_keys(DOC), (
            "jsonld.organization.same_as", "license", "llms.offer.is_free", "offer.has_api", "plan.count",
            "site_status"))

    def test_declared_block_replaces_builtin(self):
        doc = copy.deepcopy(DOC)
        doc["facts"].append({"key": "llms.offer.is_free", "value": True, "value_type": "boolean",
                             "match": {"positive": ["gratis"], "negative": []}})
        self.assertEqual(C.match_text("Acme Notes is free to use.", doc), [])
        self.assertEqual(one("Acme Notes is gratis.", doc), ("llms.offer.is_free", "matched", "normalized"))


class MatchSchema(unittest.TestCase):
    def problems(self, match, vt, enum_values=None):
        return F.match_problems(match, vt, enum_values)

    def test_valid_blocks(self):
        for f in DOC["facts"][1:]:
            self.assertEqual(self.problems(f["match"], f["value_type"], f.get("enum_values")), [], f["key"])
        self.assertEqual(F.runtime_problems(DOC), [])

    def test_refusals(self):
        cases = [
            ({"positive": ["x"]}, "string", "only for boolean"),
            ({"positive": ["x"]}, "boolean", "needs 'negative'"),
            ({"positive": ["x"], "negative": ["X"]}, "boolean", "both positive and negative"),
            ({"positive": [], "negative": []}, "boolean", "both empty"),
            ({"unit_terms": ["--"]}, "integer", "needs a letter or digit"),
            ({"unit_terms": "plans"}, "integer", "list of strings"),
            ({"unit_terms": ["plans"], "regex": "x"}, "integer", "unknown match field"),
            ({"values": {"bsd": ["BSD"]}}, "enum", "not in enum_values"),
        ]
        for match, vt, want in cases:
            got = self.problems(match, vt, ["mit"])
            self.assertTrue(any(want in m for m in got), (match, got))

    def test_runtime_problems_reports_match(self):
        doc = copy.deepcopy(DOC)
        doc["facts"][2]["match"] = {"unit_terms": []}
        self.assertEqual(F.runtime_problems(doc), ["facts[plan.count].match: unit_terms is empty"])


if __name__ == "__main__":
    unittest.main()
