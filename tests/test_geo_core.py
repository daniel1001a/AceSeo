"""Step 1 tests: ids, validator, terms gate, Number rule, renderer (W5-01, 02B, 04, 05, 06)."""

import copy
import os
import tempfile
import unittest
from decimal import Decimal

from geo import config, cost, ids, number, render, terms
from geo.canonical import canonical_bytes, sha256_hex
from geo.number import Number, NumberError
from geo.render import Block, EvidenceRef, Report, RenderError, Text
from geo.runindex import RunIndex
from geo.validate import ValidationError, codes, load_valid_run, validate_run

from tests import geo_fixtures as fx
from tests.test_pagechecks import JFK_KEY, bf_routes

ROBOTS_OPEN = b"User-agent: *\nDisallow: /api/\n"

W501_BASE = {
    "kind": "capture", "run_id": "run_20261019T210000Z_a1b2c3", "engine": "openai", "model": "gpt-5-mini",
    "tool_version": "test-fixture-1", "prompt_id": "p_09",
    "prompt_sha256": "af69ff9af7bde329e4aeb4827d0cebe6ec3ec37a997b4d9e9d21134d56b63545",
    "repeat_index": 0, "attempt": 1,
}


def smuggle(cls, **fields):
    """Build a frozen value object without running its constructor checks.

    Simulates a caller that bypassed construction; the renderer must re-check.
    """
    obj = object.__new__(cls)
    for k, v in fields.items():
        object.__setattr__(obj, k, v)
    return obj


class TmpRunCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()


class W501Ids(TmpRunCase):
    def test_golden_ids(self):
        self.assertEqual(ids.make_id(W501_BASE, "openai"), "cap_openai_fd2c4e200174c266")
        self.assertEqual(ids.make_id(dict(W501_BASE), "openai"), ids.make_id(W501_BASE, "openai"))
        self.assertEqual(ids.make_id(dict(W501_BASE, repeat_index=1), "openai"), "cap_openai_be5a6b9cda16f190")
        self.assertEqual(ids.make_id(dict(W501_BASE, run_id="run_20261019T210001Z_a1b2c3"), "openai"),
                         "cap_openai_13adb7f1dc266d22")
        for i in ("cap_openai_fd2c4e200174c266", "cap_openai_be5a6b9cda16f190", "cap_openai_13adb7f1dc266d22"):
            self.assertTrue(ids.is_record_id(i))

    def test_prompt_sha_matches_p09(self):
        p09 = fx.prompt_doc()["prompts"][8]
        self.assertEqual(p09["prompt_id"], "p_09")
        self.assertEqual(p09["prompt_sha256"], W501_BASE["prompt_sha256"])

    def test_valid_run_validates_clean(self):
        run = fx.Run(self.root)
        run.add_capture("openai", "p_09", 0, hosts=("www.boardflight.com",))
        run.add_capture("anthropic", "p_09", 0)
        self.assertEqual(validate_run(run.dir, secrets=(fx.SECRET,)), [])

    def test_mutated_id_is_only_id_mismatch(self):
        run = fx.Run(self.root)
        rec = run.add_capture("openai", "p_09", 0)
        bad = dict(rec, id=rec["id"][:-1] + ("0" if rec["id"][-1] != "0" else "1"))
        run.rewrite_records("captures.jsonl", [bad])
        self.assertEqual(codes(validate_run(run.dir)), ["E_ID_MISMATCH"])

    def test_duplicate_line(self):
        run = fx.Run(self.root)
        rec = run.add_capture("openai", "p_09", 0)
        run.rewrite_records("captures.jsonl", [rec, rec])
        self.assertIn("E_DUPLICATE_RECORD", codes(validate_run(run.dir)))

    def test_run_id_format_and_dir(self):
        run = fx.Run(self.root)
        self.assertTrue(ids.RUN_ID.fullmatch(run.manifest["run_id"]))
        self.assertTrue(run.manifest["run_id"].startswith("run_20261019T210000Z_"))
        with self.assertRaises(FileExistsError):
            fx.Run(self.root)  # same plan and started_at: never appended to

    def test_url_norm(self):
        self.assertEqual(ids.url_norm_v1("HTTPS://WWW.BoardFlight.com:443/Airport/JFK?a=1#x"),
                         "https://www.boardflight.com/Airport/JFK?a=1")
        self.assertEqual(ids.url_norm_v1("http://boardflight.com:8080/"), "http://boardflight.com:8080/")
        with self.assertRaises(ids.IdError):
            ids.url_norm_v1("ftp://boardflight.com/")


class ValidatorIntegrity(TmpRunCase):
    def test_raw_byte_flip(self):
        run = fx.Run(self.root)
        rec = run.add_capture("openai", "p_09", 0)
        path = os.path.join(run.dir, rec["raw_path"])
        with open(path, "rb") as f:
            data = bytearray(f.read())
        data[0] ^= 1
        with open(path, "wb") as f:
            f.write(bytes(data))
        self.assertEqual(codes(validate_run(run.dir)), ["E_RAW_HASH"])

    def test_input_file_edit(self):
        run = fx.Run(self.root)
        with open(os.path.join(run.dir, "inputs", "facts.json"), "ab") as f:
            f.write(b" ")
        self.assertIn("E_RAW_HASH", codes(validate_run(run.dir)))

    def test_secret_is_refused_and_detected(self):
        run = fx.Run(self.root)
        from geo.store import SecretError
        with self.assertRaises(SecretError):
            run.writer.put_raw(fx.SECRET.encode(), "txt")
        with self.assertRaises(SecretError):
            run.writer.put_raw(b'{"headers": {"Authorization": "x"}}', "json", request=True)
        with open(os.path.join(run.dir, "raw", "planted.txt"), "wb") as f:
            f.write(fx.SECRET.encode())
        self.assertIn("E_SECRET", codes(validate_run(run.dir, secrets=(fx.SECRET,))))

    def test_status_rules(self):
        run = fx.Run(self.root)
        rec = run.add_capture("openai", "p_09", 0, status="failed", error_class="timeout")
        self.assertIsNone(rec["raw_sha256"])
        self.assertEqual(validate_run(run.dir), [])
        bad = dict(rec, error_class="http_error")
        bad = _refinish(bad)
        run.rewrite_records("captures.jsonl", [bad])
        self.assertEqual(codes(validate_run(run.dir)), ["E_STATUS"])

    def test_cost_from_usage_recomputes(self):
        run = fx.Run(self.root)
        usage = {"input_tokens": 1000, "output_tokens": 500, "cached_input_tokens": 0, "search_calls": 1}
        rec = run.add_capture("openai", "p_09", 0, usage=usage)
        self.assertEqual(rec["cost_from_usage_usd"], "0.01125")
        self.assertEqual(validate_run(run.dir), [])
        run.rewrite_records("captures.jsonl", [dict(rec, cost_from_usage_usd="0.02")])
        self.assertEqual(codes(validate_run(run.dir)), ["E_COST"])

    def test_snapshot_edit(self):
        run = fx.Run(self.root)
        rec = run.add_capture("openai", "p_09", 0)
        snap = dict(rec["engine_snapshot"], model="gpt-5")
        bad = _refinish(dict(rec, engine_snapshot=snap))
        run.rewrite_records("captures.jsonl", [bad])
        self.assertEqual(codes(validate_run(run.dir)), ["E_ENGINE_SNAPSHOT"])

    def test_slot_attempt_after_ok(self):
        run = fx.Run(self.root)
        run.add_capture("openai", "p_09", 0, attempt=1)
        run.add_capture("openai", "p_09", 0, attempt=2)
        self.assertEqual(codes(validate_run(run.dir)), ["E_SLOT"])

    def test_engine_set(self):
        run = fx.Run(self.root)
        self.assertEqual(validate_run(run.dir, configured_engines=("anthropic", "openai", "perplexity", "xai")), [])
        self.assertEqual(codes(validate_run(run.dir, configured_engines=("anthropic", "openai", "gemini"))),
                         ["E_ENGINE_SET"])

    def test_load_valid_run_raises(self):
        run = fx.Run(self.root)
        rec = run.add_capture("openai", "p_09", 0)
        run.rewrite_records("captures.jsonl", [dict(rec, status="bogus")])
        with self.assertRaises(ValidationError):
            load_valid_run(run.dir)


def _refinish(rec):
    """Recompute derived id fields after a deliberate edit, so only the edit is tested."""
    identity = ids.record_identity(rec)
    rec = dict(rec, identity_sha256=ids.identity_sha256(identity), id=ids.make_id(identity, rec["engine"]))
    rec["series_key"] = ids.series_key(identity)
    return rec


class W502TermsGate(TmpRunCase):
    def test_gate_function(self):
        self.assertEqual(terms.gate({"engine": "x", "terms_status": "unverified", "opt_in": False}, ()),
                         (False, "terms_unverified"))
        self.assertEqual(terms.gate({"engine": "x", "terms_status": "verified-restricted", "opt_in": False}, ()),
                         (False, "terms_restricted"))
        self.assertEqual(terms.gate({"engine": "x", "terms_status": "Verified-Allowed", "opt_in": False}, ()),
                         (False, "terms_unverified"))
        self.assertEqual(terms.gate({"engine": "p", "terms_status": "verified-allowed", "opt_in": True}, ()),
                         (False, "opt_in_not_selected"))
        self.assertEqual(terms.gate({"engine": "p", "terms_status": "verified-allowed", "opt_in": True}, ("p",)),
                         (True, None))

    def test_split_engines_excludes(self):
        snaps, excluded, _ = config.split_engines(fx.engines_doc(), fx.load("prices.json"), ())
        self.assertEqual([s["engine"] for s in snaps], ["anthropic", "openai"])
        self.assertEqual({e["engine"]: e["reason"] for e in excluded},
                         {"perplexity": "opt_in_not_selected", "xai": "terms_unverified"})

    def test_part_b_restricted_capture_rejected(self):
        run = fx.Run(self.root, overrides={"openai": {"terms_status": "verified-restricted"}},
                     force_engines=("openai",))
        run.add_capture("openai", "p_09", 0)
        self.assertEqual(codes(validate_run(run.dir)), ["E_TERMS_GATE"])

    def test_terms_retrieved_after_capture(self):
        run = fx.Run(self.root, overrides={"openai": {"terms_retrieved": "2026-10-20"}})
        run.add_capture("openai", "p_09", 0)
        self.assertEqual(codes(validate_run(run.dir)), ["E_TERMS_GATE"])


class W510Cost(unittest.TestCase):
    def test_estimates(self):
        doc, prices = fx.engines_doc(), fx.w5_10_prices()
        expected = {"openai": "0.01125", "anthropic": "0.01035", "perplexity": "0.004"}
        for name, value in expected.items():
            e = fx.engine_entry(doc, name)
            snap, _ = config.engine_snapshot(e, prices)
            d, detail = cost.cost_estimate(snap["price_snapshot"], e["request_shape"]["max_searches_per_call"],
                                           prices["token_assumptions"])
            self.assertEqual(cost.dec_str(d), value)
            self.assertEqual(detail["label"], "Estimated")
            self.assertEqual(detail["searches"], 1)
        # Upper bound: anthropic max_uses=3 (documented cap); openai and perplexity assume 1, Estimated.
        e = fx.engine_entry(doc, "anthropic")
        snap, _ = config.engine_snapshot(e, prices)
        _, detail = cost.cost_estimate(snap["price_snapshot"], 3, prices["token_assumptions"])
        self.assertEqual((detail["upper_usd"], detail["upper_basis"]), ("0.03035", cost.SEARCH_BASIS_DOCUMENTED))
        e = fx.engine_entry(doc, "openai")
        snap, _ = config.engine_snapshot(e, prices)
        _, detail = cost.cost_estimate(snap["price_snapshot"], None, prices["token_assumptions"])
        self.assertEqual((detail["upper_usd"], detail["upper_basis"]), ("0.01125", cost.SEARCH_BASIS_ASSUMED))
        self.assertEqual(cost.planned_searches(None), (1, cost.SEARCH_BASIS_ASSUMED))
        self.assertEqual(cost.planned_searches(3), (3, cost.SEARCH_BASIS_DOCUMENTED))

    def test_upper_never_below_expected_searches(self):
        # Shipped assumptions (first live run): 2 searches per call, above openai's assumed cap of 1.
        doc, prices = fx.engines_doc(), fx.load("prices.json")
        snap, _ = config.engine_snapshot(fx.engine_entry(doc, "openai"), prices)
        d, detail = cost.cost_estimate(snap["price_snapshot"], None, prices["token_assumptions"])
        self.assertEqual((detail["upper_searches"], detail["upper_basis"]), (2, cost.SEARCH_BASIS_EXPECTED))
        self.assertEqual(detail["upper_usd"], cost.dec_str(d))


def _window(recs):
    t = sorted(r["completed_at"] for r in recs)
    return (t[0], t[-1])


def _scope(engine="openai", prompt_id="p_09"):
    return {"engine": engine, "prompt_id": prompt_id}


class W505NumberRule(TmpRunCase):
    def setUp(self):
        super().setUp()
        self.run = fx.Run(self.root)
        self.ok = [self.run.add_capture("openai", "p_09", i, hosts=("www.boardflight.com",) if i < 2 else ())
                   for i in range(3)]
        self.index = load_valid_run(self.run.dir)
        self.ids = sorted(r["id"] for r in self.ok)
        self.hits = sorted(r["id"] for r in self.ok[:2])
        self.window = _window(self.ok)

    def _num(self, **over):
        f = dict(statistic_id="citation_rate.engine_prompt", kind="rate", value=2, n=3, min_n=3,
                 evidence_ids=tuple(self.ids), label="Measured", window=self.window, hit_ids=tuple(self.hits),
                 excluded=(), basis_labels=(), scope=_scope())
        f.update(over)
        return f

    def cases(self):
        ghost = ids.make_id(dict(W501_BASE, run_id=self.run.manifest["run_id"], attempt=2), "openai")
        return {
            "E_EVIDENCE_EMPTY": self._num(evidence_ids=(), hit_ids=(), value=0, n=0),
            "E_N_MISMATCH": self._num(n=2),
            "E_N_BELOW_MIN": self._num(n=2, evidence_ids=tuple(self.ids[:2]),
                                       hit_ids=tuple(h for h in self.hits if h in self.ids[:2]),
                                       value=len([h for h in self.hits if h in self.ids[:2]]),
                                       window=_window([r for r in self.ok if r["id"] in self.ids[:2]])),
            "E_EVIDENCE_UNRESOLVED": self._num(evidence_ids=tuple(sorted(self.ids[:2] + [ghost])),
                                               hit_ids=tuple(h for h in self.hits if h in self.ids[:2]),
                                               value=len([h for h in self.hits if h in self.ids[:2]])),
            "E_MIN_N_OVERRIDE": self._num(min_n=1),
        }

    def test_each_case_fails_construction_with_its_code(self):
        for code, fields in self.cases().items():
            if code == "E_EVIDENCE_UNRESOLVED":
                continue  # resolution needs the run; construction alone succeeds
            with self.assertRaises(NumberError) as cm:
                Number(**fields)
            self.assertEqual(cm.exception.codes, [code], code)

    def test_each_case_renders_with_exactly_its_code(self):
        for code, fields in self.cases().items():
            rep = Report(Text("Report"), (Block(Text("Rate"), (smuggle(Number, **fields),)),))
            with self.assertRaises(RenderError) as cm:
                render.render_text(rep, self.index)
            self.assertEqual(cm.exception.codes, [code], code)

    def test_together_collects_all_and_writes_nothing(self):
        frags = tuple(smuggle(Number, **f) for f in self.cases().values())
        rep = Report(Text("Report"), (Block(Text("Rates"), frags),))
        out = os.path.join(self.root, "report.md")
        with self.assertRaises(RenderError) as cm:
            render.render(rep, self.index, out)
        self.assertEqual(cm.exception.codes, sorted(self.cases()))
        self.assertFalse(os.path.exists(out))
        self.assertEqual([n for n in os.listdir(self.root) if not n.startswith("run_")], [])

    def test_n6_positive_control(self):
        num = number.build("citation_rate.engine_prompt", "rate", 2, self.ids, self.hits, (), self.window,
                           scope=_scope())
        self.assertIsInstance(num, Number)
        out = os.path.join(self.root, "report.md")
        render.render(Report(Text("Report"), (Block(Text("Rate"), (num,)),)), self.index, out)
        with open(out, encoding="utf-8") as f:
            self.assertIn("2/3 [Measured]", f.read())
        with self.assertRaises(FileExistsError):
            render.render(Report(Text("Report"), ()), self.index, out)

    def test_build_below_min_gives_insufficient(self):
        ins = number.build("citation_rate.engine_prompt", "rate", 1, self.ids[:2], self.hits[:1], (),
                           self.window, scope=_scope())
        self.assertIsInstance(ins, number.Insufficient)
        text = render.render_text(Report(Text("Report"), (Block(Text("Rate"), (ins,)),)), self.index)
        self.assertIn("insufficient evidence (n=2, minimum 3)", text)
        self.assertIn("- insufficient: citation_rate.engine_prompt", text)

    def test_not_checked_groups_repeated_insufficient(self):
        ins = [number.build("citation_rate.engine_prompt", "rate", 1, self.ids[:2], self.hits[:1], (),
                            self.window, scope=_scope()) for _ in range(3)]
        text = render.render_text(Report(Text("Report"), (Block(Text("Rate"), tuple(ins)),)), self.index)
        not_checked = text.split("## Not checked", 1)[1]
        self.assertEqual(not_checked.count("- insufficient: citation_rate.engine_prompt"), 1)
        self.assertIn("(n=2, minimum 3) x3, listed under Measurements", not_checked)


class W504FailedExcludedAndExposed(TmpRunCase):
    def test_rates_and_section(self):
        run = fx.Run(self.root, repeats=6)
        ok = [run.add_capture("openai", "p_09", i, hosts=("www.boardflight.com",) if i < 2 else ("example.org",))
              for i in range(4)]
        failed = run.add_capture("openai", "p_09", 4, status="failed", error_class="timeout")
        refused = run.add_capture("openai", "p_09", 5, status="refused")
        index = load_valid_run(run.dir)
        excluded = ((failed["id"], "failed"), (refused["id"], "refused"))
        cit = number.build("citation_rate.engine_prompt", "rate", 2, [r["id"] for r in ok],
                           [r["id"] for r in ok[:2]], excluded, _window(ok), scope=_scope())
        self.assertEqual((cit.value, cit.n), (2, 4))
        all6 = ok + [failed, refused]
        # failure_rate: evidence is every attempt, hits are the non-ok ones.
        fail = number.build("failure_rate.engine", "rate", 2, [r["id"] for r in all6],
                            [failed["id"], refused["id"]], (), _window(all6), scope={"engine": "openai"})
        self.assertEqual((fail.value, fail.n), (2, 6))
        rep = Report(Text("Citations"), (Block(Text("Citation rate"), (cit,)),
                                         Block(Text("Failure rate"), (fail,))))
        text = render.render_text(rep, index)
        self.assertIn("2/4", text)
        self.assertIn("2/6", text)
        self.assertIn(failed["id"], text)
        self.assertIn(refused["id"], text)
        section = text.split("## Excluded and skipped", 1)[1].split("## Not checked", 1)[0]
        self.assertIn(failed["id"], section)
        self.assertIn(refused["id"], section)
        self.assertIn("timeout", section)
        # A rate that omits the excluded attempts is refused.
        bare = number.build("citation_rate.engine_prompt", "rate", 2, [r["id"] for r in ok],
                            [r["id"] for r in ok[:2]], (), _window(ok), scope=_scope())
        with self.assertRaises(RenderError) as cm:
            render.render_text(Report(Text("Citations"), (Block(Text("Rate"), (bare,)),)), index)
        self.assertEqual(cm.exception.codes, ["E_EXCLUDED_MISSING"])
        # A failure rate computed on survivors only is refused.
        part = number.build("failure_rate.engine", "rate", 1, [r["id"] for r in ok] + [failed["id"]],
                            [failed["id"]], (), _window(ok + [failed]), scope={"engine": "openai"})
        with self.assertRaises(RenderError) as cm:
            render.render_text(Report(Text("Failures"), (Block(Text("Failure rate"), (part,)),)), index)
        self.assertEqual(cm.exception.codes, ["E_EXCLUDED_MISSING"])


class W506Renderer(TmpRunCase):
    def setUp(self):
        super().setUp()
        self.run = fx.Run(self.root, key_content=(JFK_KEY,))
        self.ok = [self.run.add_capture("openai", "p_09", i) for i in range(3)]

    def decision_run(self):
        self.run.add_page_checks(bf_routes(robots=ROBOTS_OPEN))
        return self.run.add_decision()

    def test_a_measured_with_src_id(self):
        src = ids.src_ref("https://developers.openai.com/api/docs/pricing", "2026-10-19", "x")
        with self.assertRaises(NumberError) as cm:
            number.build("citation_rate.engine_prompt", "rate", 0, [src, src[:-1] + "0", src[:-1] + "1"], (),
                         (), (fx.T0, fx.T0), scope=_scope())
        self.assertEqual(cm.exception.codes, ["E_LABEL_MIXED"])

    def test_b_estimated_without_basis(self):
        with self.assertRaises(NumberError) as cm:
            number.build("cost_total.run", "money", Decimal("0.01"), [self.ok[0]["id"]], (), (),
                         (fx.T0, fx.T0))
        self.assertEqual(cm.exception.codes, ["E_LABEL_MIXED"])

    def test_c_stray_digit(self):
        index = load_valid_run(self.run.dir)
        with self.assertRaises(RenderError) as cm:
            render.render_text(Report(Text("Report"), (Block(Text("Engines"), (Text("3 of 5 engines"),)),)), index)
        self.assertEqual(cm.exception.codes, ["E_STRAY_DIGIT"])
        with self.assertRaises(RenderError) as cm:  # non-ASCII digits too
            render.render_text(Report(Text("Report"), (Block(Text("Engines"), (Text("٣ engines"),)),)), index)
        self.assertEqual(cm.exception.codes, ["E_STRAY_DIGIT"])

    def test_d_bare_int(self):
        index = load_valid_run(self.run.dir)
        with self.assertRaises(RenderError) as cm:
            render.render_text(Report(Text("Report"), (Block(Text("Engines"), (3,)),)), index)
        self.assertEqual(cm.exception.codes, ["E_TYPE"])

    def test_e_footer_and_baseline_by_code(self):
        dec = self.decision_run()
        index = load_valid_run(self.run.dir)
        rep = Report(Text("Report"), (Block(Text("Evidence"), (Text("See "), EvidenceRef(self.ok[0]["id"]))),),
                     decision_ids=(dec["id"],))
        text = render.render_text(rep, index)
        self.assertIn(render.FOOTER, text)
        for item, sentence in render.NOT_CHECKED_BASELINE:
            self.assertIn(item, text)
            self.assertIn(sentence, text)
        self.assertIn("engine perplexity excluded: opt_in_not_selected", text)

    def test_f_empty_not_checked(self):
        # The validator refuses this decision (V24, E_NOT_CHECKED); the renderer refuses it too.
        self.run.add_page_checks(bf_routes(robots=ROBOTS_OPEN))
        dec = self.run.add_decision(not_checked=[])
        self.assertEqual(codes(validate_run(self.run.dir)), ["E_NOT_CHECKED"])
        index = RunIndex(self.run.manifest, self.run.records)
        rep = Report(Text("Report"), (), decision_ids=(dec["id"],))
        with self.assertRaises(RenderError) as cm:
            render.render_text(rep, index)
        self.assertEqual(cm.exception.codes, ["E_NOT_CHECKED_MISSING"])

    def test_unresolved_evidence_ref(self):
        index = load_valid_run(self.run.dir)
        ghost = self.ok[0]["id"][:-1] + ("0" if self.ok[0]["id"][-1] != "0" else "1")
        with self.assertRaises(RenderError) as cm:
            render.render_text(Report(Text("Report"), (Block(Text("Ref"), (EvidenceRef(ghost),)),)), index)
        self.assertEqual(cm.exception.codes, ["E_EVIDENCE_UNRESOLVED"])

    def test_aux_refs_resolve(self):
        index = load_valid_run(self.run.dir)
        fsha = self.run.manifest["facts_sha256"]
        self.assertIsNotNone(index.lookup(ids.fct_ref(fsha, "llms.coverage.airport_count")))
        price_ref = self.run.snapshots["openai"]["price_snapshot"][0]["source_ref"]
        self.assertIsNotNone(index.lookup(price_ref))


if __name__ == "__main__":
    unittest.main()
