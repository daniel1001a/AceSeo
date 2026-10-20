"""Builders for SYNTHETIC runs used by the geo tests.

Captures are built post-adapter (W5 ground rules): answer text, citations and raw
bodies here are SYNTHETIC and never presented as provider output. Engine
snapshots, prices and prompts come from step0/data; facts from
design/boardflight.facts.sample.json.
"""

import copy
import os

from geo import config, cost, decide, number, records
from geo.canonical import canonical_bytes, strict_load_path
from geo.store import RunWriter, input_hashes
from step0 import request_builder

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "step0", "data")
FACTS_PATH = os.path.join(ROOT, "design", "boardflight.facts.sample.json")
FIXTURES = os.path.join(HERE, "fixtures")

T0 = "2026-10-19T21:00:00.000000Z"
KEY_PAGES = ("https://www.boardflight.com/", "https://www.boardflight.com/airport/jfk",
             "https://www.boardflight.com/llms.txt")
MENTION_TERMS = ("BoardFlight", "boardflight.com")
SECRET = "sk-test-FAKE-0000-must-never-be-written"


def load(name):
    return strict_load_path(os.path.join(DATA, name))


def ts(seconds):
    """T0 plus seconds, as a W4 ts."""
    h, rest = divmod(21 * 3600 + seconds, 3600)
    m, s = divmod(rest, 60)
    return "2026-10-19T%02d:%02d:%02d.000000Z" % (h, m, s)


def prompt_doc():
    prompts = request_builder.load_prompts(load("prompts.json"))
    return config.prompt_inputs([{"prompt_id": p["prompt_id"], "text": p["text"]} for p in prompts])


def engines_doc(overrides=None):
    doc = copy.deepcopy(load("engines.json"))
    for e in doc["engines"]:
        e.update((overrides or {}).get(e["engine"], {}))
    return doc


def engine_entry(doc, name):
    return next(e for e in doc["engines"] if e["engine"] == name)


class Run:
    """A run directory under construction. Call add_capture, then close."""

    def __init__(self, root, *, repeats=3, opt_in=(), overrides=None, force_engines=(),
                 configured=None, max_attempts=2, transport="fixture", secrets=(SECRET,),
                 key_content=(), facts=None, thresholds=None):
        self.engines_doc = engines_doc(overrides)
        self.prices = load("prices.json")
        snaps, excluded, sources = config.split_engines(self.engines_doc, self.prices, opt_in)
        for name in force_engines:  # engines that bypass the gate, for validator tests
            s, srcs = config.engine_snapshot(engine_entry(self.engines_doc, name), self.prices)
            snaps = [x for x in snaps if x["engine"] != name] + [s]
            excluded = [x for x in excluded if x["engine"] != name]
            sources = sorted({x["src_ref"]: x for x in sources + srcs}.values(), key=lambda x: x["src_ref"])
        self.snapshots = {s["engine"]: s for s in snaps}
        self.prompts = {p["prompt_id"]: p for p in prompt_doc()["prompts"]}
        self.inputs = {
            "prompts": canonical_bytes(prompt_doc()),
            "facts": canonical_bytes(strict_load_path(FACTS_PATH) if facts is None else facts),
            "sources": canonical_bytes({"sources": sources}),
        }
        self.manifest = records.new_manifest(
            started_at=T0, engines=sorted(snaps, key=lambda s: s["engine"]), engines_excluded=excluded,
            opt_in_selected=opt_in, input_hashes=input_hashes(self.inputs), repeats=repeats,
            max_attempts=max_attempts, key_pages=KEY_PAGES, key_content=list(key_content), mention_terms=MENTION_TERMS,
            thresholds=number.threshold_values() if thresholds is None else thresholds, planned_slots=0, cap_usd="5", transport=transport)
        self.facts_doc = strict_load_path(FACTS_PATH) if facts is None else facts
        self.writer = RunWriter(root, self.manifest, self.inputs, secrets=secrets)
        self.dir = self.writer.run_dir
        self.records = []
        self.clock = 1

    def tick(self):
        self.clock += 1
        return ts(self.clock)

    def estimate(self, engine):
        snap = self.snapshots[engine]
        shape = engine_entry(self.engines_doc, engine)["request_shape"]
        d, _ = cost.cost_estimate(snap["price_snapshot"], shape.get("max_searches_per_call"),
                                  self.prices["token_assumptions"])
        return cost.dec_str(d)

    def add_capture(self, engine, prompt_id, repeat_index, attempt=1, status="ok", error_class=None,
                    hosts=(), answer_text=None, usage=None, http_status=None):
        snap = self.snapshots[engine]
        prompt = self.prompts[prompt_id]
        body = {"model": snap["model"], "input": prompt["text"], "synthetic": True}
        req_sha, _ = self.writer.put_raw(canonical_bytes(body), "json", request=True)
        if answer_text is None:
            answer_text = "SYNTHETIC answer for %s %s." % (prompt_id, "BoardFlight") if status == "ok" else ""
        citations = [{"url": "https://%s/" % h, "title": None, "cited_text": None, "position": i,
                      "provider_field": "synthetic"} for i, h in enumerate(hosts)]
        raw_sha = raw_path = None
        if not (status == "failed" and error_class in records.NULL_RAW_ERROR_CLASSES):
            raw = canonical_bytes({"synthetic": True, "status": status, "answer": answer_text,
                                   "slot": [engine, prompt_id, repeat_index, attempt]})
            raw_sha, raw_path = self.writer.put_raw(raw, "json")
        started = self.tick()
        rec = records.capture(
            self.manifest, snap, prompt, repeat_index, attempt, started_at=started,
            completed_at=self.tick(), status=status, request_sha256=req_sha, raw_sha256=raw_sha,
            raw_path=raw_path, answer_text=answer_text, citations=citations,
            cost_estimate_usd=self.estimate(engine), error_class=error_class, http_status=http_status,
            usage=usage)
        self.append(rec)
        return rec

    def add_decision(self, index=None, **overrides):
        """Append decide.decide() for the validated run (or index); overrides edit fields, then re-id."""
        from geo.validate import load_valid_run
        rec = decide.decide(index or load_valid_run(self.dir), self.tick())
        if overrides:
            rec.update(overrides)
            rec = records._finish({k: v for k, v in rec.items() if k not in ("id", "identity_sha256")}, rec["scope"])
        self.append(rec)
        return rec

    def add_page_checks(self, routes, urls=None):
        """Run the page-check registry over FixtureFetcher(routes); no network."""
        from geo.pagechecks import FixtureFetcher, PageCheckRunner
        recs = PageCheckRunner(self.writer, FixtureFetcher(routes), self.tick).run(urls)
        self.records.extend(recs)
        return recs

    def append(self, rec):
        self.writer.append(rec)
        self.records.append(rec)

    def rewrite_records(self, name, recs):
        """Replace a records file wholesale (used to simulate hand edits)."""
        with open(os.path.join(self.dir, name), "wb") as f:
            for r in recs:
                f.write(canonical_bytes(r) + b"\n")
