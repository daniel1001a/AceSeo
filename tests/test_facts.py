"""W5-08 facts_json_validation plus the Step 4 loader (PLAN 5.6.1)."""

import copy
import json
import unittest

from geo import facts as F
from geo.canonical import canonical_bytes

NOW = "2026-10-19T21:00:00Z"


def sample():
    with open(F.SAMPLE_PATH, "rb") as fh:
        return F.parse_facts(fh.read())


def fact(doc, key):
    return next(f for f in doc["facts"] if f["key"] == key)


def snap(doc, sid):
    return next(s for s in doc["source_snapshots"] if s["id"] == sid)


class W5_08(unittest.TestCase):
    def rules(self, doc, allow_sample=True, **kw):
        return F.rules_of(F.validate_facts(doc, NOW, allow_sample=allow_sample, **kw))

    def setUp(self):
        self.v0 = F.sort_facts(sample())

    def test_v0_sorted_sample_is_valid(self):
        self.assertEqual(F.validate_facts(self.v0, NOW, allow_sample=True), [])

    def test_v1_sample_refused_without_allow_sample(self):
        self.assertEqual(self.rules(self.v0, allow_sample=False), [15])

    def test_v2_content_hash_one_digit(self):
        f = fact(self.v0, "site_status")
        h = f["content_hash"]
        f["content_hash"] = h[:-1] + ("0" if h[-1] != "0" else "1")
        self.assertEqual(self.rules(self.v0), [7])

    def test_v3_locator_on_other_domain(self):
        fact(self.v0, "llms.coverage.airport_count")["source"]["locator"] = "https://boardflight.app/llms.txt"
        self.assertEqual(self.rules(self.v0), [12])

    def test_v4_site_status_not_in_enum(self):
        fact(self.v0, "site_status")["value"] = "inactive"
        self.assertEqual(self.rules(self.v0), [6])

    def test_v5_bool_is_not_integer(self):
        fact(self.v0, "llms.coverage.airport_count")["value"] = True
        self.assertEqual(self.rules(self.v0), [3])

    def test_v6_unsorted(self):
        # The committed sample is already sorted (PLAN fixed W5 Q1), so the
        # negative case uses the reversed order.
        self.v0["facts"].reverse()
        self.assertEqual(self.rules(self.v0), [4])

    def test_v7_duplicate_member(self):
        text = json.dumps(self.v0)
        text = text.replace('"key": "site_status"', '"key": "site_status", "key": "site_status"', 1)
        self.assertEqual(self.rules(text), [1])

    def test_v8_unknown_top_level_field(self):
        self.v0["extra"] = 1
        self.assertEqual(self.rules(self.v0), [2])

    def test_v9_status_404_while_live(self):
        snap(self.v0, "snap-home-200")["status_code"] = 404
        self.assertEqual(self.rules(self.v0), [10])

    def test_v10_generated_before_derived(self):
        self.v0["generated_at"] = "2026-10-19T20:49:00Z"
        self.assertEqual(self.rules(self.v0), [9])

    def test_v11_generator_removed(self):
        del self.v0["generator"]
        self.assertEqual(self.rules(self.v0), [3])


class Rules(unittest.TestCase):
    def setUp(self):
        self.doc = F.sort_facts(sample())

    def rules(self, doc=None, **kw):
        return F.rules_of(F.validate_facts(self.doc if doc is None else doc, NOW, allow_sample=True, **kw))

    def test_missing_fact_fields_rejected(self):
        for field in F.FACT_REQ:
            doc = copy.deepcopy(self.doc)
            del fact(doc, "llms.coverage.airport_count")[field]
            self.assertIn(3, self.rules(doc), field)

    def test_missing_source_fields_rejected(self):
        for field in F.SOURCE_REQ:
            doc = copy.deepcopy(self.doc)
            del fact(doc, "llms.coverage.airport_count")["source"][field]
            self.assertIn(3, self.rules(doc), field)

    def test_unknown_fact_field_rejected(self):
        fact(self.doc, "site_status")["note"] = "x"
        self.assertEqual(self.rules(), [2])

    def test_unknown_generator_rejected(self):
        self.doc["generator"]["name"] = "hand"
        self.assertEqual(self.rules(), [3])

    def test_null_and_empty_values_rejected(self):
        fact(self.doc, "site.canonical_host")["value"] = None
        self.assertEqual(self.rules(), [3])
        fact(self.doc, "site.canonical_host")["value"] = ""
        self.assertEqual(self.rules(), [5])

    def test_unresolved_snapshot(self):
        fact(self.doc, "site_status")["source"]["snapshot_id"] = "snap-nope"
        self.assertEqual(self.rules(), [7])

    def test_bad_hash_format(self):
        fact(self.doc, "jsonld.airport.jfk.iata_code")["source"]["fragment_hash"] = "sha256:ABC"
        self.assertEqual(self.rules(), [8])

    def test_invalid_date(self):
        fact(self.doc, "jsonld.airport.jfk.page_date_modified")["value"] = "2026-02-30"
        self.assertEqual(self.rules(), [5])

    def test_future_timestamp(self):
        self.doc["generated_at"] = "2026-10-19T21:06:00Z"
        self.assertEqual(self.rules(), [9])

    def test_secret_looking_key(self):
        doc = copy.deepcopy(self.doc)
        f = copy.deepcopy(fact(doc, "site.canonical_host"))
        f["key"] = "site.api_key"
        doc["facts"] = sorted(doc["facts"] + [f], key=lambda x: x["key"])
        self.assertEqual(self.rules(doc), [4])

    def test_file_path_with_env_rejected(self):
        doc = F.build_boardflight()
        snap(doc, F.PRIOR_SNAPSHOT["id"])["path"] = "config/.env.local"
        self.assertEqual(self.rules(doc), [11])

    def test_bad_derivation_rejected(self):
        fact(self.doc, "site_status")["derivation"] = "site_status"
        self.assertEqual(self.rules(), [13])

    def test_excerpt_checked_against_body(self):
        bodies = F.load_recorded_bodies(self.doc)
        fact(self.doc, "llms.coverage.airport_count")["source"]["excerpt"] = "Covers 34 US airports."
        rules = self.rules(bodies=bodies)
        self.assertIn(14, rules)

    def test_body_hash_recheck(self):
        bodies = {"snap-llms-txt": b"not the body"}
        self.assertIn(8, self.rules(bodies=bodies))

    def test_site_status_needs_http_snapshot(self):
        doc = F.build_boardflight()
        f = fact(doc, "site_status")
        prior = snap(doc, F.PRIOR_SNAPSHOT["id"])
        f["source"]["snapshot_id"] = prior["id"]
        f["content_hash"] = prior["content_hash"]
        del f["source"]["http"]
        rules = self.rules(doc)
        self.assertIn(10, rules)
        self.assertIn(7, rules)


class Loader(unittest.TestCase):
    def setUp(self):
        self.doc = F.build_boardflight()
        self.bodies = F.load_recorded_bodies(self.doc)

    def test_valid_with_bodies(self):
        self.assertEqual(F.validate_facts(self.doc, NOW, bodies=self.bodies, allow_sample=True), [])

    def test_still_a_sample(self):
        self.assertEqual(F.rules_of(F.validate_facts(self.doc, NOW, allow_sample=False)), [15])

    def test_eleven_facts_sorted(self):
        keys = [f["key"] for f in self.doc["facts"]]
        self.assertEqual(len(keys), 11)
        self.assertEqual(keys, sorted(keys))
        for k in ("llms.offer.is_free", "llms.data.uses_live_queue_data", "jsonld.organization.same_as"):
            self.assertIn(k, keys)

    def test_deterministic(self):
        self.assertEqual(canonical_bytes(self.doc), canonical_bytes(F.build_boardflight()))

    def test_follow_up_values_and_sources(self):
        free = fact(self.doc, "llms.offer.is_free")
        self.assertIs(free["value"], True)
        self.assertEqual(free["source"]["line"], 3)
        self.assertEqual(free["source"]["excerpt"], "Free, no account.")
        live = fact(self.doc, "llms.data.uses_live_queue_data")
        self.assertIs(live["value"], False)
        self.assertEqual((live["source"]["line"], live["source"]["excerpt"]), (5, "It uses no live queue data."))
        same = fact(self.doc, "jsonld.organization.same_as")
        self.assertEqual(same["value"], ["https://www.linkedin.com/company/boardflight-fly",
                                         "https://github.com/daniel1001a/boardflight-airport-wait-data"])
        self.assertEqual(same["source"]["snapshot_id"], "snap-airport-jfk")
        self.assertEqual(same["source"]["jsonld_index"], 0)
        for f in self.doc["facts"]:
            self.assertIn("snapshot_id", f["source"])
            self.assertTrue(f["source"].get("line") or f["source"].get("json_path") or f["source"].get("header")
                            or f["source"].get("http"), f["key"])

    def test_tsa_excerpt_is_verbatim(self):
        ex = fact(self.doc, "llms.tsa_check.passing_airports")["source"]["excerpt"]
        self.assertNotIn("...", ex)
        self.assertIn(ex, self.bodies["snap-llms-txt"].decode().split("\n")[6])

    def test_prior_value_has_code_verified_source(self):
        p = fact(self.doc, "jsonld.organization.same_as")["prior_values"]
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], [])
        self.assertEqual(p[0]["valid_until"], F.SAME_AS_VALID_UNTIL)
        s = snap(self.doc, p[0]["source"]["snapshot_id"])
        self.assertEqual(s["commit"], F.PRIOR_SNAPSHOT["commit"])

    def test_prior_value_without_source_rejected(self):
        del fact(self.doc, "jsonld.organization.same_as")["prior_values"][0]["source"]
        self.assertEqual(F.rules_of(F.validate_facts(self.doc, NOW, allow_sample=True)), [3])

    def test_prior_value_with_unresolved_source_rejected(self):
        fact(self.doc, "jsonld.organization.same_as")["prior_values"][0]["source"]["snapshot_id"] = "snap-x"
        self.assertEqual(F.rules_of(F.validate_facts(self.doc, NOW, allow_sample=True)), [7])

    def test_empty_current_list_rejected(self):
        fact(self.doc, "jsonld.organization.same_as")["value"] = []
        self.assertEqual(F.rules_of(F.validate_facts(self.doc, NOW, allow_sample=True)), [5])


if __name__ == "__main__":
    unittest.main()
