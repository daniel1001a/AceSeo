"""Run validator (W4 4). Returns every error; any error means the run cannot render.

Implemented now: V1 to V21, V23 to V25 (page checks via the check registry,
decisions via decide.decision_problems) and V27. V22 (source runs) needs analyze runs, which do not exist yet: any evidence
id outside this run is reported as unresolved (V21). Seal (V26) is deferred
(PLAN 5.4.1): a run renders only when this validator returns no errors.
"""

import os
import re
import unicodedata
from collections import namedtuple
from decimal import Decimal

from . import SCHEMA_VERSION, cost, ids, number, terms
from .canonical import StrictJSONError, canonical_bytes, sha256_hex, strict_loads
from .claims import MATCHERS, NO_FACT_VERDICTS, VERDICT_BASES
from .config import with_config_sha
from .decide import DECISION_FIELDS, RULE_SET_VERSION, decision_problems
from .records import (ATTACHMENT_ROLES, CAPTURE_STATUSES, ERROR_CLASSES, MANUAL, NULL_RAW_ERROR_CLASSES,
                      SKIP_REASONS, TRANSPORTS)
from .render import BASELINE_ITEMS
from .runindex import RunIndex
from .store import FORBIDDEN_HEADER_NAMES, INPUT_FILES, RAW_EXTS, RECORD_FILES

Issue = namedtuple("Issue", "code where message")

PROMPT_ID = re.compile(r"p_[a-z0-9_]{1,40}")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

COMMON_FIELDS = ("kind", "schema_version", "id", "identity_sha256", "run_id", "created_at", "tool_build")
CAPTURE_FIELDS = COMMON_FIELDS + (
    "engine", "engine_snapshot", "prompt_id", "prompt_text", "prompt_sha256", "repeat_index", "attempt",
    "started_at", "completed_at", "status", "error_class", "http_status", "request_sha256", "raw_sha256",
    "raw_path", "answer_text", "citations", "usage", "cost_estimate_usd", "cost_from_usage_usd",
    "cost_billed_usd", "cost_billed_field", "search_observed", "access", "attachments", "series_key")
PAGE_CHECK_FIELDS = COMMON_FIELDS + (
    "check_name", "check_version", "url_norm", "url_role", "agent_profile", "params", "fetched_at",
    "final_url", "http_status", "redirect_chain", "response_headers", "raw_sha256", "raw_path",
    "derived_from_raw", "result", "not_checkable_reason", "blocking_on_fail", "detail", "series_key")
SNAPSHOT_FIELDS = ("engine", "model", "model_vendor", "tool_version", "terms_status", "terms_url",
                   "terms_last_updated", "terms_retrieved", "opt_in", "price_snapshot", "config_sha256")
CITATION_FIELDS = ("url", "title", "cited_text", "position", "provider_field")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "search_calls")
MANIFEST_FIELDS = (
    "run_id", "schema_version", "tool_build", "run_kind", "source_run_ids", "started_at", "sealed_at",
    "engines", "engines_excluded", "opt_in_selected", "prompts_sha256", "facts_sha256", "sources_sha256",
    "repeats", "max_attempts", "key_pages", "key_content", "mention_terms", "thresholds", "planned_slots",
    "skipped_slots", "budget", "transport")
CLAIM_FIELDS = COMMON_FIELDS + (
    "capture_id", "span_start", "span_end", "statement", "fact_key", "fact_ref", "facts_sha256",
    "fact_value_snapshot", "verdict", "verdict_basis", "matcher", "matcher_version")
PAGE_RESULTS = ("pass", "fail", "not_checkable")


class ValidationError(Exception):
    def __init__(self, issues):
        self.issues = list(issues)
        self.codes = sorted({i.code for i in self.issues})
        super().__init__("; ".join("%s %s: %s" % i for i in self.issues[:20]))


def codes(issues):
    return sorted({i.code for i in issues})


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _ts(v):
    return isinstance(v, str) and ids.TS.fullmatch(v) is not None


def _sha(v):
    return isinstance(v, str) and ids.SHA256.fullmatch(v) is not None


def _same_value(a, b):
    """Type-strict equality (True is not 1). Lists hold strings (W3 string_list)."""
    if isinstance(a, list) or isinstance(b, list):
        return (isinstance(a, list) and isinstance(b, list) and len(a) == len(b)
                and all(isinstance(x, str) and _same_value(x, y) for x, y in zip(a, b)))
    return isinstance(a, (str, int, bool)) and type(a) is type(b) and a == b


def _https(v):
    return isinstance(v, str) and v.startswith("https://") and len(v) > len("https://")


def _http_url(v):
    return isinstance(v, str) and (v.startswith("http://") or v.startswith("https://")) and "://" != v[-3:]


class _Run:
    def __init__(self, run_dir, secrets, configured_engines, page_registry):
        self.dir = run_dir
        self.secrets = [s.encode("utf-8") for s in secrets if s]
        self.configured = configured_engines
        self.page_registry = page_registry
        self.issues = []
        self.manifest = None
        self.prompts = {}
        self.facts_doc = None
        self.sources = []
        self.records = []

    def err(self, code, where, msg):
        self.issues.append(Issue(code, where, msg))

    # --- files -------------------------------------------------------------

    def _read(self, rel):
        with open(os.path.join(self.dir, rel), "rb") as f:
            return f.read()

    def _safe_rel(self, rel):
        return (isinstance(rel, str) and not os.path.isabs(rel) and ".." not in rel.split("/")
                and "\\" not in rel)

    def _check_file(self, where, rel, sha, exts=RAW_EXTS):
        if not self._safe_rel(rel):
            self.err("E_RAW_HASH", where, "unsafe path %r" % (rel,))
            return None
        stem, _, ext = rel.rpartition(".")
        if stem != "raw/" + str(sha) or ext not in exts:
            self.err("E_RAW_HASH", where, "path %s is not raw/<sha256>.<ext>" % rel)
            return None
        try:
            data = self._read(rel)
        except OSError:
            self.err("E_RAW_HASH", where, "file %s is missing" % rel)
            return None
        if sha256_hex(data) != sha:
            self.err("E_RAW_HASH", where, "sha256 of %s does not match" % rel)
            return None
        return data

    # --- manifest and inputs ----------------------------------------------

    def load_manifest(self):
        try:
            m = strict_loads(self._read("manifest.json"))
        except (OSError, StrictJSONError, UnicodeDecodeError, ValueError) as e:
            self.err("E_JSON", "manifest.json", str(e))
            return False
        if not isinstance(m, dict):
            self.err("E_SCHEMA", "manifest.json", "not an object")
            return False
        self.manifest = m
        missing = [f for f in MANIFEST_FIELDS if f not in m]
        unknown = [f for f in m if f not in MANIFEST_FIELDS]
        if missing or unknown:
            self.err("E_SCHEMA", "manifest.json", "missing %s, unknown %s" % (missing, unknown))
            return False
        w = "manifest.json"
        if m["schema_version"] != SCHEMA_VERSION:
            self.err("E_SCHEMA_VERSION", w, "schema_version %r" % (m["schema_version"],))
        if not (isinstance(m["run_id"], str) and ids.RUN_ID.fullmatch(m["run_id"])):
            self.err("E_SCHEMA", w, "bad run_id")
        elif m["run_id"] != os.path.basename(os.path.normpath(self.dir)):
            self.err("E_SCHEMA", w, "run_id does not equal the run directory name")
        if m["run_kind"] not in ("collect", "analyze", MANUAL):
            self.err("E_SCHEMA", w, "bad run_kind")
        if m["run_kind"] in ("collect", MANUAL) and m["source_run_ids"]:
            self.err("E_SCHEMA", w, "collect and manual runs have no source_run_ids")
        if m["transport"] != MANUAL if m["run_kind"] == MANUAL else m["transport"] not in TRANSPORTS:
            self.err("E_SCHEMA", w, "bad transport for run_kind %r" % (m["run_kind"],))
        if not _ts(m["started_at"]) or (m["sealed_at"] is not None and not _ts(m["sealed_at"])):
            self.err("E_TIME", w, "bad started_at or sealed_at")
        for f in ("repeats", "max_attempts", "planned_slots"):
            if not _int(m[f]) or m[f] < (0 if f == "planned_slots" else 1):
                self.err("E_SCHEMA", w, "bad %s" % f)
        if not isinstance(m["mention_terms"], list) or not m["mention_terms"]:
            self.err("E_SCHEMA", w, "mention_terms must be a non-empty list")
        for u in m["key_pages"] if isinstance(m["key_pages"], list) else [None]:
            try:
                if ids.url_norm_v1(u) != u:
                    self.err("E_SCHEMA", w, "key page %s is not in url_norm_v1 form" % u)
            except (ids.IdError, TypeError, AttributeError, ValueError):
                self.err("E_SCHEMA", w, "bad key page %r" % (u,))
        for s in m["skipped_slots"] if isinstance(m["skipped_slots"], list) else [None]:
            if (not isinstance(s, dict) or set(s) != {"engine", "prompt_id", "repeat_index", "reason"}
                    or s["reason"] not in SKIP_REASONS):
                self.err("E_SCHEMA", w, "bad skipped slot %r" % (s,))
        b = m["budget"]
        if (not isinstance(b, dict) or set(b) != {"cap_usd", "spent_estimate_usd"}
                or not all(cost.is_dec(b[k]) for k in b)):
            self.err("E_COST", w, "budget must hold dec strings cap_usd and spent_estimate_usd")
        elif Decimal(b["spent_estimate_usd"]) > Decimal(b["cap_usd"]):
            self.err("E_COST", w, "spent estimate exceeds the cap")
        self._check_engine_set(m)
        for key, name in INPUT_FILES.items():
            rel = "inputs/" + name
            try:
                data = self._read(rel)
            except OSError:
                self.err("E_RAW_HASH", rel, "input file missing")
                continue
            if sha256_hex(data) != m[key]:
                self.err("E_RAW_HASH", rel, "sha256 does not equal manifest %s" % key)
                continue
            try:
                doc = strict_loads(data)
            except (StrictJSONError, UnicodeDecodeError, ValueError) as e:
                self.err("E_JSON", rel, str(e))
                continue
            if name == "prompts.json":
                self._load_prompts(doc, rel)
            elif name == "facts.json":
                self.facts_doc = doc
            else:
                self.sources = doc.get("sources", []) if isinstance(doc, dict) else []
        return True

    def _check_engine_set(self, m):
        w = "manifest.json"
        engines = m["engines"] if isinstance(m["engines"], list) else []
        excluded = m["engines_excluded"] if isinstance(m["engines_excluded"], list) else []
        names_in = [e.get("engine") for e in engines if isinstance(e, dict)]
        names_out = [e.get("engine") for e in excluded if isinstance(e, dict)]
        both = names_in + names_out
        if len(both) != len(set(both)):
            self.err("E_ENGINE_SET", w, "an engine appears more than once in engines and engines_excluded")
        if self.configured is not None:
            missing = sorted(set(self.configured) - set(both))
            extra = sorted(set(both) - set(self.configured))
            if missing or extra:
                self.err("E_ENGINE_SET", w, "configured engines missing %s, unknown %s" % (missing, extra))
        for e in excluded:
            if not isinstance(e, dict) or set(e) != {"engine", "terms_status", "reason"}:
                self.err("E_SCHEMA", w, "bad engines_excluded entry %r" % (e,))

    def _load_prompts(self, doc, rel):
        for p in doc.get("prompts", []) if isinstance(doc, dict) else []:
            pid = p.get("prompt_id")
            text = p.get("text")
            if not (isinstance(pid, str) and PROMPT_ID.fullmatch(pid)) or not isinstance(text, str):
                self.err("E_PROMPT", rel, "bad prompt entry %r" % (pid,))
                continue
            if pid in self.prompts:
                self.err("E_PROMPT", rel, "prompt_id %s listed twice" % pid)
            if p.get("prompt_sha256") != sha256_hex(text.encode("utf-8")):
                self.err("E_PROMPT", rel, "prompt_sha256 of %s does not match its text" % pid)
            self.prompts[pid] = text

    # --- records -------------------------------------------------------------

    def load_records(self):
        for kind, name in sorted(RECORD_FILES.items()):
            try:
                data = self._read(name)
            except FileNotFoundError:
                continue
            lines = data.split(b"\n")
            if lines and lines[-1] == b"":
                lines.pop()
            else:
                self.err("E_JSON", name, "file does not end with a newline (torn last line)")
            for n, line in enumerate(lines, 1):
                where = "%s:%d" % (name, n)
                try:
                    rec = strict_loads(line)
                except (StrictJSONError, UnicodeDecodeError, ValueError) as e:
                    self.err("E_JSON", where, str(e))
                    continue
                if not isinstance(rec, dict) or rec.get("kind") != kind:
                    self.err("E_SCHEMA", where, "kind does not match %s" % name)
                    continue
                if canonical_bytes(rec) != line:
                    self.err("E_JSON", where, "line is not canonical JSON")
                self.records.append((where, rec))

    def check_common(self, where, rec, fields):
        m = self.manifest
        missing = [f for f in fields if f not in rec]
        unknown = [f for f in rec if f not in fields]
        if missing or unknown:
            self.err("E_SCHEMA", where, "missing %s, unknown %s" % (missing, unknown))
            return False
        if rec["schema_version"] != SCHEMA_VERSION:
            self.err("E_SCHEMA_VERSION", where, "schema_version %r" % (rec["schema_version"],))
        if rec["run_id"] != m["run_id"]:
            self.err("E_SCHEMA", where, "run_id does not equal the manifest")
        if rec["tool_build"] != m["tool_build"]:
            self.err("E_SCHEMA", where, "tool_build does not equal the manifest")
        if not _ts(rec["created_at"]):
            self.err("E_TIME", where, "created_at is not a ts")
        elif _ts(m["started_at"]) and rec["created_at"] < m["started_at"]:
            self.err("E_TIME", where, "created_at is before the run started")
        elif m["sealed_at"] is not None and rec["created_at"] > m["sealed_at"]:
            self.err("E_TIME", where, "created_at is after the run was sealed")
        return True

    def check_ids(self):
        engines = {r["id"]: r.get("engine") for _, r in self.records if r.get("kind") == "capture"}
        seen = {}
        for where, rec in self.records:
            claim_engine = engines.get(rec.get("capture_id")) if rec.get("kind") == "claim" else None
            for p in ids.id_problems(rec, claim_engine):
                self.err("E_ID_MISMATCH", where, p)
            rid = rec.get("id")
            if rid in seen:
                if seen[rid] == rec.get("identity_sha256"):
                    self.err("E_DUPLICATE_RECORD", where, "%s written twice" % rid)
                else:
                    self.err("E_ID_COLLISION", where, "%s has two identities" % rid)
            else:
                seen[rid] = rec.get("identity_sha256")
            if rec.get("kind") in ("capture", "page_check"):
                try:
                    key = ids.series_key(ids.record_identity(rec))
                except ids.IdError:
                    key = None
                if rec.get("series_key") != key:
                    self.err("E_SCHEMA", where, "series_key does not recompute")

    def check_capture(self, where, rec):
        if not self.check_common(where, rec, CAPTURE_FIELDS):
            return
        m = self.manifest
        snap = rec["engine_snapshot"]
        manifest_snap = {e.get("engine"): e for e in m["engines"] if isinstance(e, dict)}.get(rec["engine"])
        if not isinstance(snap, dict) or set(snap) != set(SNAPSHOT_FIELDS):
            self.err("E_ENGINE_SNAPSHOT", where, "engine_snapshot fields differ from W4 3.3")
            return
        if snap["engine"] != rec["engine"]:
            self.err("E_ENGINE_SNAPSHOT", where, "snapshot engine differs from the record")
        if manifest_snap is None or canonical_bytes(manifest_snap) != canonical_bytes(snap):
            self.err("E_ENGINE_SNAPSHOT", where, "engine_snapshot differs from the manifest entry")
        if with_config_sha(snap)["config_sha256"] != snap["config_sha256"]:
            self.err("E_ENGINE_SNAPSHOT", where, "config_sha256 does not recompute")
        if not snap["model"] or not snap["tool_version"] or not ids.is_slug(snap["model_vendor"]):
            self.err("E_ENGINE_SNAPSHOT", where, "model, model_vendor or tool_version invalid")
        manual = m["run_kind"] == MANUAL
        if rec["access"] != (MANUAL if manual else "api"):
            self.err("E_SCHEMA", where, "access must be %s in a %s run" % (MANUAL if manual else "api", m["run_kind"]))
        if manual:
            self._check_manual_capture(where, rec)
        elif rec["attachments"] != []:
            self.err("E_SCHEMA", where, "attachments are for manual captures only")
        self._check_capture_common(where, rec, snap, manual)

    def _check_manual_capture(self, where, rec):
        """A manual capture was typed or pasted by a person: no request, no terms gate, no cost."""
        snap = rec["engine_snapshot"]
        if (snap["terms_status"] != MANUAL or snap["opt_in"] is not False or snap["price_snapshot"] != []
                or any(snap[k] is not None for k in ("terms_url", "terms_last_updated", "terms_retrieved"))):
            self.err("E_ENGINE_SNAPSHOT", where, "manual snapshot must have terms_status manual and no terms or prices")
        if rec["status"] != "ok":
            self.err("E_STATUS", where, "manual captures are ok")
        for f in ("request_sha256", "http_status", "usage", "search_observed", "cost_from_usage_usd",
                  "cost_billed_usd", "cost_billed_field"):
            if rec[f] is not None:
                self.err("E_SCHEMA", where, "%s must be null for a manual capture" % f)
        if rec["cost_estimate_usd"] != "0":
            self.err("E_COST", where, "a manual capture costs nothing")
        if isinstance(rec["raw_path"], str) and isinstance(rec["answer_text"], str):
            body = self._check_file(where, rec["raw_path"], rec["raw_sha256"])
            if body is not None and body != rec["answer_text"].encode("utf-8"):
                self.err("E_RAW_HASH", where, "manual answer_text differs from its raw text file")
        atts = rec["attachments"]
        if not isinstance(atts, list):
            self.err("E_SCHEMA", where, "attachments must be a list")
            return
        for a in atts:
            if (not isinstance(a, dict) or set(a) != {"role", "raw_sha256", "raw_path"}
                    or a["role"] not in ATTACHMENT_ROLES):
                self.err("E_SCHEMA", where, "bad attachment %r" % (a,))
                continue
            self._check_file(where, a["raw_path"], a["raw_sha256"])

    def _check_capture_common(self, where, rec, snap, manual):
        m = self.manifest
        if not manual:
            self._check_terms_and_prices(where, rec, snap)

        # V9 prompt
        pid, text = rec["prompt_id"], rec["prompt_text"]
        if not (isinstance(pid, str) and PROMPT_ID.fullmatch(pid)) or not isinstance(text, str):
            self.err("E_PROMPT", where, "bad prompt_id or prompt_text")
        else:
            if unicodedata.normalize("NFC", text) != text:
                self.err("E_PROMPT", where, "prompt_text is not NFC")
            if rec["prompt_sha256"] != sha256_hex(text.encode("utf-8")):
                self.err("E_PROMPT", where, "prompt_sha256 does not match prompt_text")
            if self.prompts.get(pid) != text:
                self.err("E_PROMPT", where, "prompt %s differs from inputs/prompts.json" % pid)

        # V6 time
        if not (_ts(rec["started_at"]) and _ts(rec["completed_at"])):
            self.err("E_TIME", where, "started_at or completed_at is not a ts")
        elif rec["completed_at"] < rec["started_at"]:
            self.err("E_TIME", where, "completed_at is before started_at")
        elif _ts(m["started_at"]) and rec["started_at"] < m["started_at"]:
            self.err("E_TIME", where, "started_at is before the run started")

        # V13 status
        status, ec = rec["status"], rec["error_class"]
        if status not in CAPTURE_STATUSES:
            self.err("E_SCHEMA", where, "bad status %r" % (status,))
        if not isinstance(rec["answer_text"], str):
            self.err("E_SCHEMA", where, "answer_text must be a string")
        if status == "failed":
            if ec not in ERROR_CLASSES:
                self.err("E_STATUS", where, "failed capture needs a valid error_class")
        elif ec is not None:
            self.err("E_STATUS", where, "error_class is only for failed captures")
        if status == "ok" and (not rec["answer_text"] or rec["raw_sha256"] is None):
            self.err("E_STATUS", where, "ok capture needs answer_text and a raw body")
        if rec["raw_sha256"] is None or rec["raw_path"] is None:
            if not (status == "failed" and ec in NULL_RAW_ERROR_CLASSES):
                self.err("E_STATUS", where, "raw body may be null only for failed timeout or connection")
            if (rec["raw_sha256"] is None) != (rec["raw_path"] is None):
                self.err("E_RAW_HASH", where, "raw_sha256 and raw_path must both be null or both set")
        else:
            self._check_file(where, rec["raw_path"], rec["raw_sha256"])
        hs = rec["http_status"]
        if hs is not None and not (_int(hs) and 100 <= hs <= 599):
            self.err("E_SCHEMA", where, "http_status out of range")
        if rec["search_observed"] is not None and not (_int(rec["search_observed"]) and rec["search_observed"] >= 0):
            self.err("E_SCHEMA", where, "search_observed must be a non-negative int or null")

        if not manual:
            self._check_request(where, rec, snap)

        # V14 citations
        self._check_citations(where, rec)

        # V15 cost
        if not manual:
            self._check_cost(where, rec, snap)

    def _check_terms_and_prices(self, where, rec, snap):
        if not _https(snap["terms_url"]):
            self.err("E_ENGINE_SNAPSHOT", where, "terms_url must be https")
        self._check_price_snapshot(where, snap["price_snapshot"])
        # V12 terms gate, independent of how the record got here.
        allowed, reason = terms.gate(snap, self.manifest["opt_in_selected"])
        if not allowed:
            self.err("E_TERMS_GATE", where, "engine %s: %s" % (rec["engine"], reason))
        dates = (snap["terms_retrieved"], snap["terms_last_updated"])
        if not all(isinstance(d, str) and DATE.fullmatch(d) for d in dates):
            self.err("E_TERMS_GATE", where, "terms_retrieved and terms_last_updated must be dates")
        elif _ts(rec["completed_at"]) and snap["terms_retrieved"] > rec["completed_at"][:10]:
            self.err("E_TERMS_GATE", where, "terms_retrieved is after the capture date")

    def _check_request(self, where, rec, snap):
        # V7 request body
        req = self._check_file(where, "raw/%s.json" % rec["request_sha256"], rec["request_sha256"], ("json",)) \
            if _sha(rec["request_sha256"]) else None
        if not _sha(rec["request_sha256"]):
            self.err("E_RAW_HASH", where, "request_sha256 is not a sha256")
        if req is not None:
            low = req.lower()
            if any(b'"' + n + b'"' in low for n in FORBIDDEN_HEADER_NAMES):
                self.err("E_SECRET", where, "request body contains a forbidden header name")
            try:
                body = strict_loads(req)
            except (StrictJSONError, UnicodeDecodeError, ValueError):
                body = None
            if not isinstance(body, dict) or body.get("model") != snap["model"]:
                self.err("E_ENGINE_SNAPSHOT", where, "model differs from the stored request body")

    def _check_citations(self, where, rec):
        cits = rec["citations"]
        if not isinstance(cits, list):
            self.err("E_CITATION", where, "citations must be a list")
        else:
            positions = []
            for c in cits:
                if not isinstance(c, dict) or set(c) != set(CITATION_FIELDS):
                    self.err("E_CITATION", where, "citation fields differ from W4 3.3")
                    continue
                if not _http_url(c["url"]):
                    self.err("E_CITATION", where, "citation url %r is not http(s)" % (c["url"],))
                positions.append(c["position"])
            if positions and (not all(_int(p) for p in positions) or sorted(positions) != list(range(len(positions)))):
                self.err("E_CITATION", where, "citation positions must be unique ints from 0")

    def _check_cost(self, where, rec, snap):
        usage = rec["usage"]
        if usage is not None and (not isinstance(usage, dict) or set(usage) != set(USAGE_FIELDS) or any(
                v is not None and not (_int(v) and v >= 0) for v in usage.values())):
            self.err("E_SCHEMA", where, "usage fields differ from W4 3.3")
            usage = None
        if not cost.is_dec(rec["cost_estimate_usd"]):
            self.err("E_COST", where, "cost_estimate_usd is not a dec string")
        for f in ("cost_from_usage_usd", "cost_billed_usd"):
            if rec[f] is not None and not cost.is_dec(rec[f]):
                self.err("E_COST", where, "%s is not a dec string" % f)
        if (rec["cost_billed_usd"] is None) != (rec["cost_billed_field"] is None):
            self.err("E_COST", where, "cost_billed_usd and cost_billed_field go together")
        if rec["cost_from_usage_usd"] is not None or usage is not None:
            try:
                d = cost.cost_from_usage(snap["price_snapshot"], usage) if usage is not None else None
                expected = None if d is None else cost.dec_str(d)
            except (cost.CostError, KeyError, TypeError):
                expected = "invalid"
            if rec["cost_from_usage_usd"] != expected:
                self.err("E_COST", where, "cost_from_usage_usd does not recompute (expected %s)" % expected)

    def _check_price_snapshot(self, where, rows):
        refs = {s.get("src_ref") for s in self.sources if isinstance(s, dict)}
        if not isinstance(rows, list) or not rows:
            self.err("E_ENGINE_SNAPSHOT", where, "price_snapshot must be a non-empty list")
            return
        for r in rows:
            if (not isinstance(r, dict) or set(r) != {"unit", "per", "price_usd", "condition", "source_ref"}
                    or r["unit"] not in cost.UNITS or r["per"] not in cost.PER or not cost.is_dec(r["price_usd"])):
                self.err("E_ENGINE_SNAPSHOT", where, "bad price_snapshot row %r" % (r,))
                continue
            if r["source_ref"] not in refs:
                self.err("E_ENGINE_SNAPSHOT", where, "price source_ref %s not in inputs/sources.json" % r["source_ref"])

    def check_slots(self):
        m = self.manifest
        slots = {}
        for where, rec in self.records:
            if rec.get("kind") != "capture" or not _int(rec.get("repeat_index")) or not _int(rec.get("attempt")):
                if rec.get("kind") == "capture":
                    self.err("E_SLOT", where, "repeat_index and attempt must be ints")
                continue
            if not 0 <= rec["repeat_index"] < m["repeats"]:
                self.err("E_SLOT", where, "repeat_index out of range")
            if not 1 <= rec["attempt"] <= m["max_attempts"]:
                self.err("E_SLOT", where, "attempt out of range")
            slots.setdefault((rec.get("engine"), rec.get("prompt_id"), rec["repeat_index"]), []).append(rec)
        for key, recs in sorted(slots.items(), key=lambda kv: str(kv[0])):
            recs = sorted(recs, key=lambda r: r["attempt"])
            attempts = [r["attempt"] for r in recs]
            if attempts != list(range(1, len(attempts) + 1)):
                self.err("E_SLOT", "slot %s" % (key,), "attempts %s are not contiguous from 1" % attempts)
            oks = [r for r in recs if r.get("status") == "ok"]
            if len(oks) > 1:
                self.err("E_SLOT", "slot %s" % (key,), "more than one ok attempt")
            if oks and recs[-1] is not oks[0]:
                self.err("E_SLOT", "slot %s" % (key,), "attempt after an ok")

    def check_page_check(self, where, rec):
        if not self.check_common(where, rec, PAGE_CHECK_FIELDS):
            return
        m = self.manifest
        entry = (self.page_registry or {}).get((rec["check_name"], rec["check_version"]))
        if entry is None:
            self.err("E_PAGE_CHECK", where, "check %s v%s is not in the registry" % (rec["check_name"], rec["check_version"]))
        else:
            if rec["blocking_on_fail"] is not entry.blocking_on_fail:
                self.err("E_PAGE_CHECK", where, "blocking_on_fail differs from the registry")
            if rec["agent_profile"] not in entry.agent_profiles:
                self.err("E_PAGE_CHECK", where, "agent_profile %s not in the registry" % rec["agent_profile"])
        try:
            if ids.url_norm_v1(rec["url_norm"]) != rec["url_norm"]:
                self.err("E_SCHEMA", where, "url_norm is not in url_norm_v1 form")
        except (ids.IdError, TypeError, AttributeError, ValueError):
            self.err("E_SCHEMA", where, "bad url_norm")
        expected_role = "key" if rec["url_norm"] in m["key_pages"] else "other"
        if rec["url_role"] != expected_role:
            self.err("E_PAGE_CHECK", where, "url_role must be %s" % expected_role)
        if not _ts(rec["fetched_at"]):
            self.err("E_TIME", where, "fetched_at is not a ts")
        elif _ts(m["started_at"]) and rec["fetched_at"] < m["started_at"]:
            self.err("E_TIME", where, "fetched_at is before the run started")
        if rec["result"] not in PAGE_RESULTS:
            self.err("E_SCHEMA", where, "bad result")
        if (rec["result"] == "not_checkable") != bool(rec["not_checkable_reason"]):
            self.err("E_SCHEMA", where, "not_checkable_reason is required iff result is not_checkable")
        for f in ("params", "detail"):
            if not isinstance(rec[f], dict):
                self.err("E_SCHEMA", where, "%s must be an object" % f)
        if not isinstance(rec["redirect_chain"], list) or any(
                not isinstance(h, dict) or set(h) != {"url", "status"} for h in rec["redirect_chain"]):
            self.err("E_SCHEMA", where, "redirect_chain entries are {url, status}")
        if not isinstance(rec["response_headers"], list) or any(
                not isinstance(h, list) or len(h) != 2 or not all(isinstance(x, str) for x in h)
                for h in rec["response_headers"]):
            self.err("E_SCHEMA", where, "response_headers are [name, value] pairs")
        if not isinstance(rec["derived_from_raw"], bool) or not isinstance(rec["blocking_on_fail"], bool):
            self.err("E_SCHEMA", where, "derived_from_raw and blocking_on_fail are bools")
        if rec["raw_sha256"] is None or rec["raw_path"] is None:
            if (rec["raw_sha256"] is None) != (rec["raw_path"] is None):
                self.err("E_RAW_HASH", where, "raw_sha256 and raw_path must both be null or both set")
            if rec["result"] != "not_checkable" or rec["not_checkable_reason"] not in NULL_RAW_ERROR_CLASSES:
                self.err("E_STATUS", where, "raw may be null only for not_checkable timeout or connection")
        else:
            self._check_file(where, rec["raw_path"], rec["raw_sha256"])

    def _facts(self):
        doc = self.facts_doc
        if not isinstance(doc, dict) or not isinstance(doc.get("facts"), list):
            return {}
        return {f["key"]: f for f in doc["facts"] if isinstance(f, dict) and isinstance(f.get("key"), str)}

    def check_claim(self, where, rec, captures, facts):
        if not self.check_common(where, rec, CLAIM_FIELDS):
            return
        cap = captures.get(rec["capture_id"])
        if cap is None or cap.get("status") != "ok":
            self.err("E_REF_CAPTURE", where, "capture_id %r does not resolve to an ok capture" % (rec["capture_id"],))
            cap = None
        s, e, stmt = rec["span_start"], rec["span_end"], rec["statement"]
        if not (_int(s) and _int(e) and isinstance(stmt, str)):
            self.err("E_SCHEMA", where, "span_start, span_end must be ints and statement a string")
        elif cap is not None:
            text = cap.get("answer_text") or ""
            if not 0 <= s < e <= len(text):
                self.err("E_CLAIM_SPAN", where, "span %d..%d is outside the answer" % (s, e))
            elif text[s:e] != stmt:
                self.err("E_CLAIM_SPAN", where, "statement differs from the capture span")
        self._check_claim_fact(where, rec, facts)
        verdict = rec["verdict"]
        if verdict not in VERDICT_BASES or rec["verdict_basis"] not in VERDICT_BASES[verdict]:
            self.err("E_VERDICT", where, "verdict %r with basis %r" % (verdict, rec["verdict_basis"]))
        if rec["matcher"] not in MATCHERS or not _int(rec["matcher_version"]):
            self.err("E_SCHEMA", where, "bad matcher or matcher_version")
        elif rec["matcher"] == "llm" and verdict != "needs_review":
            self.err("E_VERDICT_LLM", where, "llm claims may only be needs_review")

    def _check_claim_fact(self, where, rec, facts):
        if rec["facts_sha256"] != self.manifest["facts_sha256"]:
            self.err("E_REF_FACT", where, "facts_sha256 differs from the manifest")
            return
        key = rec["fact_key"]
        if key is None:
            if rec["verdict"] not in NO_FACT_VERDICTS:
                self.err("E_REF_FACT", where, "fact_key is required for verdict %r" % (rec["verdict"],))
            elif rec["fact_ref"] is not None or rec["fact_value_snapshot"] is not None:
                self.err("E_REF_FACT", where, "fact_ref and fact_value_snapshot need a fact_key")
            return
        fact = facts.get(key) if isinstance(key, str) else None
        if fact is None:
            self.err("E_REF_FACT", where, "fact_key %r is not in the facts snapshot" % (key,))
            return
        if rec["fact_ref"] != ids.fct_ref(self.manifest["facts_sha256"], key):
            self.err("E_REF_FACT", where, "fact_ref does not recompute")
        if not _same_value(rec["fact_value_snapshot"], fact.get("value")):
            self.err("E_REF_FACT", where, "fact_value_snapshot differs from the facts snapshot")

    def check_decision(self, where, rec, known):
        if not self.check_common(where, rec, DECISION_FIELDS):
            return
        if rec["rule_set_version"] != RULE_SET_VERSION or isinstance(rec["rule_set_version"], bool):
            self.err("E_DECISION", where, "rule_set_version %r is not %d" % (rec["rule_set_version"], RULE_SET_VERSION))
            return
        try:
            problems = decision_problems(rec, self.manifest)
        except (TypeError, KeyError, AttributeError) as e:
            problems = ["malformed decision (%s)" % type(e).__name__]
        for p in problems:
            self.err("E_DECISION", where, p)
        # V21: every id the decision cites resolves inside this run.
        cited = set(i for i in rec["input_ids"] if isinstance(i, (str, int))) if isinstance(rec["input_ids"], list) else set()
        for w in rec["why"] if isinstance(rec["why"], list) else []:
            if isinstance(w, dict) and isinstance(w.get("evidence_ids"), list):
                cited.update(w["evidence_ids"])
        for b in rec["confidence_basis"] if isinstance(rec["confidence_basis"], list) else []:
            if isinstance(b, dict) and isinstance(b.get("evidence_ids"), list):
                cited.update(b["evidence_ids"])
        nums = rec["numbers"] if isinstance(rec["numbers"], list) else None
        if nums is None:
            self.err("E_SCHEMA", where, "numbers is not a list")
        for i, d in enumerate(nums or []):
            try:
                n = number.from_dict(d)
            except number.NumberError as e:
                self.err("E_SCHEMA", where, "numbers[%d]: %s" % (i, e))
                continue
            cited.update(n.evidence_ids)
            cited.update(x[0] for x in n.excluded if isinstance(x, tuple) and x)
        for eid in sorted((i for i in cited if not isinstance(i, str) or i not in known), key=repr):
            self.err("E_REF_UNRESOLVED", where, "%r does not resolve in this run" % (eid,))
        # V24: not_checked is never empty and always carries the baseline.
        items = rec["not_checked"]
        if not isinstance(items, list) or not items or not all(
                isinstance(i, dict) and set(i) == {"item", "reason_code", "detail"} for i in items):
            self.err("E_NOT_CHECKED", where, "not_checked must be a non-empty list of {item, reason_code, detail}")
            return
        missing = [b for b in BASELINE_ITEMS if b not in {i["item"] for i in items}]
        if missing:
            self.err("E_NOT_CHECKED", where, "not_checked lacks %s" % missing)

    def check_secrets(self):
        if not self.secrets:
            return
        for base, _, files in os.walk(self.dir):
            for name in files:
                path = os.path.join(base, name)
                with open(path, "rb") as f:
                    data = f.read()
                if any(s in data for s in self.secrets):
                    self.err("E_SECRET", os.path.relpath(path, self.dir), "file contains a secret")

    def run(self):
        if not self.load_manifest():
            return self.issues
        self.load_records()
        if self.manifest["run_kind"] == "analyze" and any(
                r.get("kind") in ("capture", "page_check") for _, r in self.records):
            self.err("E_SCHEMA", "manifest.json", "analyze runs contain no captures or page_checks")
        if self.manifest["run_kind"] == MANUAL and any(
                r.get("kind") in ("page_check", "decision") for _, r in self.records):
            self.err("E_SCHEMA", "manifest.json", "manual runs contain no page_checks or decisions")
        if any(r.get("kind") == "page_check" for _, r in self.records) and not self.manifest["key_pages"]:
            self.err("E_SCHEMA", "manifest.json", "key_pages is empty but page checks exist")
        captures = {r.get("id"): r for _, r in self.records if r.get("kind") == "capture"}
        facts = self._facts()
        known = {r.get("id") for _, r in self.records} | set(self.aux())
        for where, rec in self.records:
            kind = rec["kind"]
            if kind == "capture":
                self.check_capture(where, rec)
            elif kind == "page_check":
                self.check_page_check(where, rec)
            elif kind == "claim":
                self.check_claim(where, rec, captures, facts)
            else:
                self.check_decision(where, rec, known)
        self.check_ids()
        self.check_slots()
        self.check_secrets()
        return self.issues

    def aux(self):
        out = {}
        for s in self.sources:
            if isinstance(s, dict) and s.get("src_ref"):
                out[s["src_ref"]] = {"timestamp": None, "url": s.get("url"), "retrieved": s.get("retrieved")}
        facts = self.facts_doc.get("facts", []) if isinstance(self.facts_doc, dict) else []
        for f in facts:
            if isinstance(f, dict) and isinstance(f.get("key"), str):
                out[ids.fct_ref(self.manifest["facts_sha256"], f["key"])] = {"timestamp": None, "key": f["key"]}
        return out


def _default_registry():
    try:
        from .pagechecks import REGISTRY
    except ImportError:
        return {}
    return REGISTRY


def validate_run(run_dir, secrets=(), configured_engines=None, page_registry=None):
    """Return a list of Issue(code, where, message). Empty means valid."""
    reg = _default_registry() if page_registry is None else page_registry
    return _Run(run_dir, secrets, configured_engines, reg).run()


def load_valid_run(run_dir, secrets=(), configured_engines=None, page_registry=None):
    """Return a RunIndex, or raise ValidationError. Rendering requires this (no seal yet)."""
    reg = _default_registry() if page_registry is None else page_registry
    r = _Run(run_dir, secrets, configured_engines, reg)
    issues = r.run()
    if issues:
        raise ValidationError(issues)
    return RunIndex(r.manifest, [rec for _, rec in r.records], r.aux())
