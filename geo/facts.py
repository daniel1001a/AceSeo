"""facts.json validation and the minimal BoardFlight loader (PLAN Step 4; W3 3, 4; PLAN 5.6.1).

validate_facts() returns a list of Issue(rule, where, message). `rule` is the W3
section 4 rule number (1..15); W3 defines rules, not error codes (W5 Q2). The
hand-written-file rejections in W3 4 that have no number of their own are filed
under the nearest rule: a missing or unknown generator is rule 3, a secret-looking
key is rule 4, a secret-looking value is rule 5.

Extension (PLAN 5.6.1): an optional per-fact `prior_values` list of
{value, valid_until, source}. The source is required and must resolve to a
snapshot like a fact source does. An empty list value inside prior_values means
"the field was absent"; a current fact value may never be empty.

build_boardflight() is not the real generator. It sorts the 8 hand-assembled
sample facts and adds the 3 approved follow-up facts, extracted by code from the
RECORDED bodies under tests/fixtures. Because it inherits hand-assembled facts it
keeps a sample_notice, so it validates only with allow_sample.
"""

import copy
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections import namedtuple
from urllib.parse import urlsplit

Issue = namedtuple("Issue", "rule where message")

SUPPORTED_MAJOR = 1
SAMPLE_GENERATOR = "w3-hand-assembled-sample"
LOADER_GENERATOR = "geo.facts.boardflight_loader"
GENERATORS = (SAMPLE_GENERATOR, LOADER_GENERATOR)

TOP_FIELDS = ("schema_version", "site", "generator", "generated_at", "source_snapshots", "facts")
SITE_REQ, SITE_OPT = ("name", "canonical_origin", "hosts"), ("note",)
GEN_REQ, GEN_OPT = ("name", "version"), ("sample_notice",)
SNAP_COMMON = ("id", "kind", "bytes", "content_hash")
SNAP_KIND = {
    "http": ("request_url", "final_url", "status_code", "redirect_chain", "response_headers", "fetched_at"),
    "file": ("repo", "commit", "path", "read_at"),
}
SNAP_TIME = {"http": "fetched_at", "file": "read_at"}
RESPONSE_HEADERS = ("content-type", "etag", "location", "last-modified")
FACT_REQ = ("key", "value", "value_type", "source", "derived_at", "derivation", "content_hash",
            "verification", "stability")
FACT_OPT = ("enum_values", "prior_values", "match")
SOURCE_REQ = ("kind", "locator", "snapshot_id")
SOURCE_OPT = ("line", "json_path", "jsonld_index", "header", "excerpt", "fragment_hash", "http")
SOURCE_HTTP = ("status_code", "final_url", "redirects", "fetched_at")
PRIOR_FIELDS = ("value", "valid_until", "source")
SOURCE_KINDS = {"file": "file", "url": "http", "jsonld": "http", "http": "http"}
VALUE_TYPES = ("string", "integer", "number", "boolean", "date", "datetime", "url", "enum",
               "string_list", "integer_list")
STABILITY = ("static", "changes_daily", "changes_per_deploy")
METHODS = ("refetch_and_extract", "reparse_jsonld", "http_probe", "rehash_file")
SITE_STATUS = ("live", "redirect_only", "error", "unreachable")

KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
DERIVATION_RE = re.compile(r"^[a-z0-9_.]+\.v[0-9]+$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SEMVER_RE = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SECRET_KEY_RE = re.compile(r"token|secret|password|api_key")
SECRET_VALUE_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_\-]{32,}$")
SECRET_PATH_RE = re.compile(r"(^|/)(\.env[^/]*|[^/]*(secret|credential|private[_-]?key|id_rsa)[^/]*|[^/]*\.pem|[^/]*\.key)$",
                            re.I)
EMPTY_SHA256 = "sha256:" + hashlib.sha256(b"").hexdigest()
MAX_REDIRECTS = 5
EXCERPT_MAX = 200
SKEW = dt.timedelta(minutes=5)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def parse_ts(s):
    if not isinstance(s, str):
        return None
    try:
        return dt.datetime.strptime(s, TS_FORMAT)
    except ValueError:
        return None


def _host(url):
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def site_status_of(status_code, redirects):
    """W3 3.2 mapping site_status.v1 for a completed HTTP fetch."""
    if 200 <= status_code <= 299 and redirects <= MAX_REDIRECTS:
        return "live"
    if 300 <= status_code <= 399:
        return "redirect_only"
    if 400 <= status_code <= 599:
        return "error"
    return None


def _reject_constant(text):
    raise ValueError("constant not allowed: %s" % text)


def _no_dup(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key: %s" % k)
        out[k] = v
    return out


def parse_facts(data):
    """bytes or str -> dict. Floats are allowed (value_type number); NaN, Infinity
    and duplicate members are not (rule 1)."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    doc = json.loads(data, parse_constant=_reject_constant, object_pairs_hook=_no_dup)
    if not isinstance(doc, dict):
        raise ValueError("top level is not an object")
    return doc


class _Checker:
    def __init__(self, doc, now, bodies, allow_sample):
        self.doc, self.bodies, self.allow_sample = doc, bodies or {}, allow_sample
        self.now = parse_ts(now) if isinstance(now, str) else now
        self.issues = []
        self.hosts = ()
        self.snaps = {}

    def add(self, rule, where, message):
        self.issues.append(Issue(rule, where, message))

    def fields(self, obj, where, required, optional=()):
        """Rule 2 for unknown members, rule 3 for missing ones. False if obj is not a dict."""
        if not isinstance(obj, dict):
            self.add(3, where, "must be an object")
            return False
        for k in sorted(set(obj) - set(required) - set(optional)):
            self.add(2, where, "unknown field %r" % k)
        for k in required:
            if k not in obj:
                self.add(3, where, "missing required field %r" % k)
        return True

    def ts(self, value, where):
        t = parse_ts(value)
        if t is None:
            self.add(9 if isinstance(value, str) else 3, where, "not a UTC second-precision timestamp ending in Z")
        elif self.now is not None and t > self.now + SKEW:
            self.add(9, where, "%s is in the future" % value)
        return t

    def hash_field(self, value, where):
        if not isinstance(value, str):
            self.add(3, where, "must be a string")
        elif not HASH_RE.match(value):
            self.add(8, where, "not sha256:<64 lowercase hex>")

    def run(self):
        d = self.doc
        for k in sorted(set(d) - set(TOP_FIELDS)):
            self.add(2, "$", "unknown top-level field %r" % k)
        for k in TOP_FIELDS:
            if k not in d:
                self.add(3, "$", "missing required field %r" % k)
        self.header(d)
        self.snapshots(d.get("source_snapshots"))
        gen_at = parse_ts(d.get("generated_at"))
        facts = d.get("facts")
        if facts is None:
            return
        if not isinstance(facts, list):
            self.add(3, "$.facts", "must be a list")
            return
        keys = []
        for i, f in enumerate(facts):
            k = self.fact(f, "$.facts[%d]" % i, gen_at)
            if k is not None:
                keys.append(k)
        if len(set(keys)) != len(keys):
            self.add(4, "$.facts", "duplicate keys")
        if keys != sorted(keys):
            self.add(4, "$.facts", "facts are not sorted by key")
        if gen_at is not None:
            for sid, s in self.snaps.items():
                t = parse_ts(s.get(SNAP_TIME.get(s.get("kind"), ""), None))
                if t is not None and t > gen_at:
                    self.add(9, "$.source_snapshots[%s]" % sid, "fetched or read after generated_at")

    def header(self, d):
        sv = d.get("schema_version")
        if "schema_version" in d:
            m = SEMVER_RE.match(sv) if isinstance(sv, str) else None
            if not isinstance(sv, str):
                self.add(3, "$.schema_version", "must be a string")
            elif not m or int(m.group(1)) != SUPPORTED_MAJOR:
                self.add(2, "$.schema_version", "unsupported schema_version %r" % sv)
        site = d.get("site")
        if "site" in d and self.fields(site, "$.site", SITE_REQ, SITE_OPT):
            hosts = site.get("hosts")
            if not isinstance(hosts, list) or not hosts or not all(isinstance(h, str) and h for h in hosts):
                self.add(3, "$.site.hosts", "must be a non-empty list of hostnames")
            else:
                self.hosts = tuple(hosts)
            origin = site.get("canonical_origin")
            parts = urlsplit(origin) if isinstance(origin, str) else None
            if parts is None or parts.scheme != "https" or parts.path not in ("", "/") or parts.query:
                self.add(3, "$.site.canonical_origin", "must be an https origin with no path")
            elif self.hosts and parts.hostname not in self.hosts:
                self.add(12, "$.site.canonical_origin", "host not in site.hosts")
        gen = d.get("generator")
        if "generator" in d and self.fields(gen, "$.generator", GEN_REQ, GEN_OPT):
            if gen.get("name") not in GENERATORS:
                self.add(3, "$.generator.name", "generator %r is not in the allowlist" % (gen.get("name"),))
            if not isinstance(gen.get("version"), str):
                self.add(3, "$.generator.version", "must be a string")
            if "sample_notice" in gen and not self.allow_sample:
                self.add(15, "$.generator.sample_notice", "file is a sample; refused without allow_sample")
        if "generated_at" in d:
            self.ts(d["generated_at"], "$.generated_at")

    def snapshots(self, snaps):
        if snaps is None:
            return
        if not isinstance(snaps, list):
            self.add(3, "$.source_snapshots", "must be a list")
            return
        for i, s in enumerate(snaps):
            where = "$.source_snapshots[%d]" % i
            kind = s.get("kind") if isinstance(s, dict) else None
            if kind not in SNAP_KIND:
                if isinstance(s, dict):
                    self.add(3, where, "kind must be http or file")
                    self.fields(s, where, SNAP_COMMON, sum(SNAP_KIND.values(), ()))
                else:
                    self.add(3, where, "must be an object")
                continue
            if not self.fields(s, where, SNAP_COMMON + SNAP_KIND[kind]):
                continue
            sid = s.get("id")
            if not isinstance(sid, str) or not sid:
                self.add(3, where, "id must be a non-empty string")
            elif sid in self.snaps:
                self.add(7, where, "duplicate snapshot id %r" % sid)
            else:
                self.snaps[sid] = s
            if not _is_int(s.get("bytes")) or s.get("bytes", 0) < 0:
                self.add(3, where + ".bytes", "must be a non-negative int")
            self.hash_field(s.get("content_hash"), where + ".content_hash")
            self.ts(s.get(SNAP_TIME[kind]), where + "." + SNAP_TIME[kind])
            if kind == "http":
                self.http_snapshot(s, where)
            else:
                self.file_snapshot(s, where)
            body = self.bodies.get(sid)
            if body is not None:
                if "sha256:" + hashlib.sha256(body).hexdigest() != s.get("content_hash"):
                    self.add(8, where, "content_hash does not match the local body")
                if len(body) != s.get("bytes"):
                    self.add(8, where, "bytes does not match the local body")

    def http_snapshot(self, s, where):
        code = s.get("status_code")
        if not _is_int(code):
            self.add(3, where + ".status_code", "must be an int")
        elif not 100 <= code <= 599:
            self.add(10, where + ".status_code", "out of range 100..599")
        elif not 300 <= code <= 399 and s.get("content_hash") == EMPTY_SHA256:
            self.add(10, where, "empty body for a non-redirect status")
        chain = s.get("redirect_chain")
        if not isinstance(chain, list) or not all(
                isinstance(h, dict) and set(h) == {"status_code", "location"} and _is_int(h["status_code"])
                and isinstance(h["location"], str) for h in chain):
            self.add(3, where + ".redirect_chain", "must be a list of {status_code, location}")
        hdrs = s.get("response_headers")
        if not isinstance(hdrs, dict) or not all(isinstance(v, str) for v in hdrs.values()):
            self.add(3, where + ".response_headers", "must be an object of strings")
        else:
            for k in sorted(set(hdrs) - set(RESPONSE_HEADERS)):
                self.add(2, where + ".response_headers", "header %r is not allowlisted" % k)
        for f in ("request_url", "final_url"):
            u = s.get(f)
            if not isinstance(u, str) or urlsplit(u).scheme not in ("https", "http") or not _host(u):
                self.add(3, where + "." + f, "must be an absolute URL")
        if self.hosts and isinstance(s.get("final_url"), str) and _host(s["final_url"]) not in self.hosts:
            self.add(10, where + ".final_url", "final URL host not in site.hosts")

    def file_snapshot(self, s, where):
        if not isinstance(s.get("commit"), str) or not COMMIT_RE.match(s["commit"]):
            self.add(11, where + ".commit", "must be a full 40-hex SHA")
        p = s.get("path")
        if not isinstance(p, str) or not p:
            self.add(3, where + ".path", "must be a non-empty string")
        elif p.startswith("/") or "\\" in p or ".." in p.split("/") or SECRET_PATH_RE.search(p):
            self.add(11, where + ".path", "path must be relative, without .., .env or key-like names")
        if not isinstance(s.get("repo"), str) or not s["repo"]:
            self.add(3, where + ".repo", "must be a non-empty string")

    def fact(self, f, where, gen_at):
        if not self.fields(f, where, FACT_REQ, FACT_OPT):
            return None
        key = f.get("key")
        if not isinstance(key, str):
            self.add(3, where + ".key", "must be a string")
            key = None
        else:
            where = "$.facts[%s]" % key
            if not KEY_RE.match(key):
                self.add(4, where, "key does not match the key regex")
            if SECRET_KEY_RE.search(key):
                self.add(4, where, "secret-looking key")
        vt = f.get("value_type")
        if "value_type" in f and vt not in VALUE_TYPES:
            self.add(3, where + ".value_type", "unknown value_type %r" % (vt,))
            vt = None
        if "value" in f and vt is not None:
            self.value(f["value"], vt, where + ".value", allow_empty=False)
        self.enum(f, vt, where)
        snap = self.source(f.get("source"), where + ".source", f.get("content_hash"))
        if "content_hash" in f:
            self.hash_field(f["content_hash"], where + ".content_hash")
        derived = self.ts(f.get("derived_at"), where + ".derived_at") if "derived_at" in f else None
        if derived is not None and snap is not None:
            st = parse_ts(snap.get(SNAP_TIME.get(snap.get("kind"), ""), None))
            if st is not None and derived < st:
                self.add(9, where + ".derived_at", "earlier than the snapshot fetch or read time")
        if derived is not None and gen_at is not None and derived > gen_at:
            self.add(9, where + ".derived_at", "later than generated_at")
        self.meta(f, where)
        if key == "site_status":
            self.site_status(f, snap, where)
        if "prior_values" in f:
            self.priors(f["prior_values"], vt, f.get("value"), derived, where + ".prior_values")
        if "match" in f and vt is not None:
            for msg in match_problems(f["match"], vt, f.get("enum_values")):
                self.add(3, where + ".match", msg)
        return key

    def value(self, v, vt, where, allow_empty):
        if v is None:
            self.add(3, where, "value is null")
            return
        if vt in ("string", "date", "datetime", "url", "enum"):
            if not isinstance(v, str):
                self.add(3, where, "%s value must be a string" % vt)
                return
            if not v:
                self.add(5, where, "empty string")
            elif vt == "date":
                try:
                    if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", v):
                        raise ValueError
                    dt.date.fromisoformat(v)
                except ValueError:
                    self.add(5, where, "not a real YYYY-MM-DD date")
            elif vt == "datetime" and parse_ts(v) is None:
                self.add(5, where, "datetime must be UTC ending in Z")
            elif vt == "url":
                if urlsplit(v).scheme != "https" or _host(v) not in self.hosts:
                    self.add(5, where, "url must be https with a host in site.hosts")
            self.secret_value(v, where)
        elif vt == "integer":
            if not _is_int(v):
                self.add(3, where, "integer value must be an int (bool is not int)")
        elif vt == "number":
            if not (_is_int(v) or isinstance(v, float)) or (isinstance(v, float) and not math.isfinite(v)):
                self.add(3, where, "number value must be a finite int or float")
        elif vt == "boolean":
            if not isinstance(v, bool):
                self.add(3, where, "boolean value must be true or false")
        elif vt in ("string_list", "integer_list"):
            if not isinstance(v, list):
                self.add(3, where, "%s value must be a list" % vt)
                return
            ok = (lambda x: isinstance(x, str) and x) if vt == "string_list" else _is_int
            if not v and not allow_empty:
                self.add(5, where, "list is empty")
            elif not all(ok(x) for x in v):
                self.add(5, where, "list items must all be %s" % ("non-empty strings" if vt == "string_list" else "ints"))
            elif vt == "string_list":
                for x in v:
                    self.secret_value(x, where)

    def secret_value(self, v, where):
        if SECRET_VALUE_RE.match(v):
            self.add(5, where, "secret-looking value")

    def enum(self, f, vt, where):
        ev = f.get("enum_values")
        if vt == "enum":
            if not isinstance(ev, list) or not ev or not all(isinstance(x, str) and x for x in ev):
                self.add(6, where + ".enum_values", "enum needs a non-empty list of strings")
            elif len(set(ev)) != len(ev):
                self.add(6, where + ".enum_values", "enum_values are not unique")
            elif isinstance(f.get("value"), str) and f["value"] not in ev:
                self.add(6, where + ".value", "value %r is not in enum_values" % f["value"])
        elif "enum_values" in f and vt is not None:
            self.add(6, where + ".enum_values", "enum_values given for a non-enum fact")

    def source(self, src, where, content_hash, prior=False):
        if not self.fields(src, where, SOURCE_REQ, SOURCE_OPT):
            return None
        kind = src.get("kind")
        if kind not in SOURCE_KINDS:
            self.add(3, where + ".kind", "unknown source kind %r" % (kind,))
        loc = src.get("locator")
        if not isinstance(loc, str) or not loc:
            self.add(3, where + ".locator", "must be a non-empty string")
        elif kind == "file":
            if loc.startswith("/") or ".." in loc.split("/") or SECRET_PATH_RE.search(loc):
                self.add(11, where + ".locator", "file locator must be a safe relative path")
        elif kind in SOURCE_KINDS:
            if urlsplit(loc).scheme != "https" or _host(loc) not in self.hosts:
                self.add(12, where + ".locator", "locator host %r is not in site.hosts" % (_host(loc),))
        for f, check in (("line", lambda x: _is_int(x) and x >= 1), ("jsonld_index", lambda x: _is_int(x) and x >= 0),
                         ("json_path", lambda x: x is None or isinstance(x, str)),
                         ("header", lambda x: isinstance(x, str) and x)):
            if f in src and not check(src[f]):
                self.add(3, where + "." + f, "bad type")
        if "fragment_hash" in src:
            self.hash_field(src["fragment_hash"], where + ".fragment_hash")
        snap = self.snaps.get(src.get("snapshot_id"))
        if snap is None:
            self.add(7, where + ".snapshot_id", "snapshot %r does not resolve" % (src.get("snapshot_id"),))
        else:
            if kind in SOURCE_KINDS and SOURCE_KINDS[kind] != snap.get("kind"):
                self.add(7, where + ".kind", "source kind %s does not fit a %s snapshot" % (kind, snap.get("kind")))
            if not prior and content_hash != snap.get("content_hash"):
                self.add(7, where, "fact content_hash differs from snapshot %s" % snap.get("id"))
        if "http" in src:
            self.source_http(src["http"], snap, where + ".http")
        if "excerpt" in src:
            self.excerpt(src, snap, where)
        return snap

    def source_http(self, h, snap, where):
        if not self.fields(h, where, SOURCE_HTTP):
            return
        if snap is None or snap.get("kind") != "http":
            return
        want = {"status_code": snap.get("status_code"), "final_url": snap.get("final_url"),
                "redirects": len(snap.get("redirect_chain") or []), "fetched_at": snap.get("fetched_at")}
        for k in SOURCE_HTTP:
            if k in h and h[k] != want[k]:
                self.add(10, where + "." + k, "%r differs from snapshot value %r" % (h[k], want[k]))

    def excerpt(self, src, snap, where):
        ex = src["excerpt"]
        if not isinstance(ex, str) or not ex:
            self.add(3, where + ".excerpt", "must be a non-empty string")
            return
        if len(ex) > EXCERPT_MAX:
            self.add(14, where + ".excerpt", "longer than %d chars" % EXCERPT_MAX)
        body = self.bodies.get(snap.get("id")) if snap is not None else None
        if body is None:
            return
        text = body.decode("utf-8", errors="replace")
        line = src.get("line")
        if _is_int(line):
            lines = text.split("\n")
            hay = lines[line - 1] if 1 <= line <= len(lines) else ""
        else:
            hay = text
        if ex not in hay:
            self.add(14, where + ".excerpt", "excerpt not found in the source%s" % (" at line %d" % line if _is_int(line) else ""))

    def meta(self, f, where):
        d = f.get("derivation")
        if "derivation" in f and (not isinstance(d, str) or not DERIVATION_RE.match(d)):
            self.add(13, where + ".derivation", "does not match the derivation regex")
        if "stability" in f and f["stability"] not in STABILITY:
            self.add(13, where + ".stability", "unknown stability %r" % (f["stability"],))
        v = f.get("verification")
        if "verification" in f and self.fields(v, where + ".verification", ("method", "steps")):
            if v.get("method") not in METHODS:
                self.add(13, where + ".verification.method", "unknown method %r" % (v.get("method"),))
            steps = v.get("steps")
            if not isinstance(steps, list) or not steps or not all(isinstance(s, str) and s for s in steps):
                self.add(13, where + ".verification.steps", "must be a non-empty list of strings")

    def site_status(self, f, snap, where):
        if snap is None:
            return
        if snap.get("kind") != "http":
            self.add(10, where, "site_status needs a real HTTP fetch snapshot")
            return
        value = f.get("value")
        if value not in (f.get("enum_values") or ()) or value not in SITE_STATUS:
            return  # rule 6 owns values outside the enum
        code = snap.get("status_code")
        if not _is_int(code) or not 100 <= code <= 599:
            return  # already reported on the snapshot
        mapped = site_status_of(code, len(snap.get("redirect_chain") or []))
        if mapped != value:
            self.add(10, where + ".value", "snapshot status %d maps to %r, not %r" % (code, mapped, value))

    def priors(self, priors, vt, current, derived, where):
        if not isinstance(priors, list) or not priors:
            self.add(3, where, "must be a non-empty list")
            return
        for i, p in enumerate(priors):
            w = "%s[%d]" % (where, i)
            if not self.fields(p, w, PRIOR_FIELDS):
                continue
            if vt is not None and "value" in p:
                self.value(p["value"], vt, w + ".value", allow_empty=True)
                if p["value"] == current:
                    self.add(5, w + ".value", "prior value equals the current value")
            if "valid_until" in p:
                t = self.ts(p["valid_until"], w + ".valid_until")
                if t is not None and derived is not None and t > derived:
                    self.add(9, w + ".valid_until", "later than the fact's derived_at")
            if "source" in p:
                self.source(p["source"], w + ".source", None, prior=True)


def validate_facts(doc_or_bytes, now=None, bodies=None, allow_sample=False):
    """-> sorted list of Issue. Empty means valid.

    now: injected clock (W3 ts string or datetime); None skips the future check.
    bodies: {snapshot_id: bytes} of locally stored snapshot bodies; when given,
    hashes, byte counts (rule 8) and excerpts (rule 14) are rechecked.
    """
    if isinstance(doc_or_bytes, (bytes, str)):
        try:
            doc = parse_facts(doc_or_bytes)
        except (UnicodeDecodeError, ValueError) as e:
            return [Issue(1, "$", str(e))]
    else:
        doc = doc_or_bytes
        if not isinstance(doc, dict):
            return [Issue(1, "$", "top level is not an object")]
    c = _Checker(doc, now, bodies, allow_sample)
    c.run()
    return sorted(set(c.issues))


def rules_of(issues):
    return sorted({i.rule for i in issues})


def sort_facts(doc):
    out = copy.deepcopy(doc)
    out["facts"] = sorted(out["facts"], key=lambda f: f["key"])
    return out


def facts_by_key(doc):
    return {f["key"]: f for f in doc["facts"]}


# "match" blocks (geo/claims.py topics_for): which phrases in an answer assert
# a value for a fact. Phrases are literal text, never regexes.
MATCH_FIELDS = {
    "boolean": (("positive", "negative"), ("subject_terms",)),
    "integer": (("unit_terms",), ("subject_terms",)),
    "enum": (("values",), ("subject_terms",)),
}
MAX_PHRASE = 80


def _phrase_problems(v, where):
    if not isinstance(v, list) or not all(isinstance(p, str) for p in v):
        return ["%s must be a list of strings" % where]
    out = []
    for p in v:
        if not re.search(r"[A-Za-z0-9]", p) or len(p) > MAX_PHRASE:
            out.append("%s: phrase %r needs a letter or digit and at most %d characters" % (where, p, MAX_PHRASE))
    if len({p.strip().lower() for p in v}) != len(v):
        out.append("%s lists a phrase twice" % where)
    return out


def match_problems(match, value_type, enum_values=None):
    """Messages for a fact's match block; [] when it is usable."""
    if value_type not in MATCH_FIELDS:
        return ["match is only for boolean, integer or enum facts, not %s" % value_type]
    if not isinstance(match, dict):
        return ["match must be an object"]
    req, opt = MATCH_FIELDS[value_type]
    out = ["unknown match field %r" % k for k in sorted(set(match) - set(req) - set(opt))]
    out += ["match needs %r" % k for k in req if k not in match]
    for k in ("unit_terms", "positive", "negative", "subject_terms"):
        if k in match:
            out += _phrase_problems(match[k], k)
    if value_type == "boolean" and not out:
        if not (match["positive"] or match["negative"]):
            out.append("positive and negative are both empty")
        both = {p.strip().lower() for p in match["positive"]} & {p.strip().lower() for p in match["negative"]}
        if both:
            out.append("phrases in both positive and negative: %s" % ", ".join(sorted(both)))
    if value_type == "integer" and not out and not match["unit_terms"]:
        out.append("unit_terms is empty")
    if value_type == "enum" and "values" in match:
        vals = match["values"]
        if not isinstance(vals, dict) or not vals:
            out.append("values must map enum values to phrase lists")
        else:
            for v in sorted(vals):
                if isinstance(enum_values, list) and v not in enum_values:
                    out.append("values: %r is not in enum_values" % v)
                out += _phrase_problems(vals[v], "values[%s]" % v)
    return out


def runtime_problems(doc):
    """What collect and import-manual need from a facts file, as a list of messages.

    This is not validate_facts: it does not check sources or snapshots. It only
    refuses files the matcher cannot read (site.name, site.hosts, and a facts
    list of {key, value} with unique keys)."""
    out = []
    if not isinstance(doc, dict):
        return ["the facts file must be a JSON object"]
    site = doc.get("site")
    if not isinstance(site, dict) or not isinstance(site.get("name"), str) or not site.get("name"):
        out.append("site.name must be the brand name, e.g. \"Example Co\"")
    elif not isinstance(site.get("hosts"), list) or not site["hosts"] or \
            not all(isinstance(h, str) and h for h in site["hosts"]):
        out.append("site.hosts must list the site's hostnames, e.g. [\"example.com\", \"www.example.com\"]")
    facts = doc.get("facts")
    if not isinstance(facts, list):
        return out + ["facts must be a list of {\"key\": ..., \"value\": ...}"]
    keys = []
    for i, f in enumerate(facts):
        if not isinstance(f, dict) or not isinstance(f.get("key"), str) or "value" not in f:
            out.append("facts[%d] needs a string key and a value" % i)
            continue
        keys.append(f["key"])
        if "match" in f:
            out += ["facts[%s].match: %s" % (f["key"], m)
                    for m in match_problems(f["match"], f.get("value_type"), f.get("enum_values"))]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        out.append("duplicate fact keys: %s" % ", ".join(dup))
    return out


# ---------------------------------------------------------------------------
# Minimal BoardFlight loader (PLAN 5.6.1)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_PATH = os.path.join(_ROOT, "design", "boardflight.facts.sample.json")
RECORDED_DIR = os.path.join(_ROOT, "tests", "fixtures", "boardflight-2026-10-19")
REPO_FIXTURE = os.path.join(_ROOT, "tests", "fixtures", "boardflight-repo-e17bc0d", "structured-data.ts")
LOADER_GENERATED_AT = "2026-10-19T20:50:00Z"

# Recorded bodies whose bytes match a sample snapshot hash. home.html does not
# match snap-home-200 (the home page is no-store), so it is not used as a body.
RECORDED_BODIES = {"snap-llms-txt": "llms.txt", "snap-airport-jfk": "airport_jfk.html"}

# Verified 2026-10-19 in the local clone (read only): at e17bc0d, the parent of
# a37cde2, lib/seo/structured-data.ts has no sameAs; a37cde2 (2026-09-08T17:05:08Z)
# added lib/seo/identity.ts with BRAND_PROFILE_URLS.
PRIOR_SNAPSHOT = {
    "id": "snap-repo-structured-data-e17bc0d",
    "kind": "file",
    "repo": "daniel1001a/boardflight",
    "commit": "e17bc0ddd85a97851c8e634ed1b311444887ccf0",
    "path": "lib/seo/structured-data.ts",
}
SAME_AS_VALID_UNTIL = "2026-09-08T17:05:08Z"

LOADER_NOTICE = ("Built by geo.facts.build_boardflight: the 8 hand-assembled facts of "
                 "design/boardflight.facts.sample.json, sorted, plus 3 facts extracted by code from RECORDED "
                 "bodies. Inherits the sample's hand-assembled facts, so it is still a sample.")

# The phrases matcher v2 hard-coded for this fact, now declared as data.
LIVE_QUEUE_MATCH = {
    "positive": ["real-time TSA wait times", "real-time security wait times", "real-time wait times",
                 "real-time queue times", "live wait times", "live queue data", "uses real-time data",
                 "uses live data"],
    "negative": ["does not use live queue data", "doesn't use live queue data", "uses no live queue data",
                 "no live queue data", "does not use real-time data", "does not use live data",
                 "does not show real-time", "does not provide real-time", "doesn't show real-time",
                 "not real-time"],
}

_JSONLD_RE = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


class FactsError(ValueError):
    pass


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def jsonld_blocks(html_text):
    return _JSONLD_RE.findall(html_text)


def _line(text, n):
    lines = text.split("\n")
    if not 1 <= n <= len(lines):
        raise FactsError("line %d is out of range" % n)
    return lines[n - 1]


def _match(pattern, text, what):
    m = re.search(pattern, text)
    if not m:
        raise FactsError("%s: pattern %r not found" % (what, pattern))
    return m


def _llms_fact(key, value, value_type, line, excerpt, derivation, snap, derived_at, steps):
    return {
        "key": key, "value": value, "value_type": value_type,
        "source": {"kind": "http", "locator": snap["final_url"], "snapshot_id": snap["id"],
                   "line": line, "excerpt": excerpt},
        "derived_at": derived_at, "derivation": derivation, "content_hash": snap["content_hash"],
        "verification": {"method": "refetch_and_extract", "steps": steps},
        "stability": "changes_per_deploy",
    }


def load_recorded_bodies(doc, recorded_dir=RECORDED_DIR, repo_fixture=REPO_FIXTURE):
    """{snapshot_id: bytes} for the RECORDED bodies this repo holds."""
    out = {}
    for sid, name in RECORDED_BODIES.items():
        with open(os.path.join(recorded_dir, name), "rb") as fh:
            out[sid] = fh.read()
    if any(s.get("id") == PRIOR_SNAPSHOT["id"] for s in doc.get("source_snapshots", [])):
        with open(repo_fixture, "rb") as fh:
            out[PRIOR_SNAPSHOT["id"]] = fh.read()
    return out


def build_boardflight(sample_path=SAMPLE_PATH, recorded_dir=RECORDED_DIR, repo_fixture=REPO_FIXTURE,
                      generated_at=LOADER_GENERATED_AT):
    """-> facts doc (dict), deterministic for the same inputs."""
    with open(sample_path, "rb") as fh:
        doc = parse_facts(fh.read())
    snaps = {s["id"]: s for s in doc["source_snapshots"]}
    bodies = {}
    for sid, name in RECORDED_BODIES.items():
        with open(os.path.join(recorded_dir, name), "rb") as fh:
            bodies[sid] = fh.read()
        if _sha(bodies[sid]) != snaps[sid]["content_hash"]:
            raise FactsError("recorded %s does not match snapshot %s" % (name, sid))
    llms_snap, jfk_snap = snaps["snap-llms-txt"], snaps["snap-airport-jfk"]
    llms = bodies["snap-llms-txt"].decode("utf-8")

    by_key = facts_by_key(doc)
    # The sample's excerpt for line 7 is abbreviated with "...", which is not in the
    # source text; re-derive it verbatim with the fact's own verification regex.
    tsa = by_key["llms.tsa_check.passing_airports"]
    m = _match(r"pass that check at (\d+) of (\d+) airports: ([A-Z, ]+?(?: and [A-Z]{3}))\.",
               _line(llms, tsa["source"]["line"]), "tsa_check")
    codes = sorted(re.split(r", | and ", m.group(3)))
    if codes != tsa["value"] or len(codes) != int(m.group(1)):
        raise FactsError("tsa_check: recorded line 7 does not give the sample value")
    tsa["source"]["excerpt"] = m.group(0)

    line3 = _line(llms, 3)
    free = _match(r"\bFree, no account\.", line3, "offer.is_free")
    line5 = _line(llms, 5)
    live = _match(r"\bIt uses no live queue data\.", line5, "data.uses_live_queue_data")
    new = [
        _llms_fact("llms.offer.is_free", True, "boolean", 3, free.group(0), "llms_txt.regex.offer_is_free.v1",
                   llms_snap, generated_at,
                   ["GET source.locator", "Take line 3; match regex '\\bFree, no account\\.'",
                    "A match maps to true; compare to value"]),
        dict(_llms_fact("llms.data.uses_live_queue_data", False, "boolean", 5, live.group(0),
                        "llms_txt.regex.uses_live_queue_data.v1", llms_snap, generated_at,
                        ["GET source.locator", "Take line 5; match regex '\\bIt uses no live queue data\\.'",
                         "A match maps to false; compare to value"]),
             match=LIVE_QUEUE_MATCH),
    ]

    blocks = jsonld_blocks(bodies["snap-airport-jfk"].decode("utf-8"))
    org = json.loads(blocks[0])["@graph"][0]
    if org.get("@type") != "Organization" or not isinstance(org.get("sameAs"), list):
        raise FactsError("same_as: JSON-LD block 0 @graph[0] is not an Organization with sameAs")

    with open(repo_fixture, "rb") as fh:
        repo_body = fh.read()
    repo_text = repo_body.decode("utf-8")
    if "sameAs" in repo_text:
        raise FactsError("same_as prior: the pinned structured-data.ts mentions sameAs")
    org_line = next(i for i, ln in enumerate(repo_text.split("\n"), 1) if "export function organizationLd()" in ln)
    prior_snap = dict(PRIOR_SNAPSHOT, read_at=generated_at, bytes=len(repo_body), content_hash=_sha(repo_body))
    new.append({
        "key": "jsonld.organization.same_as",
        "value": list(org["sameAs"]),
        "value_type": "string_list",
        "source": {"kind": "jsonld", "locator": jfk_snap["final_url"], "snapshot_id": jfk_snap["id"],
                   "jsonld_index": 0, "json_path": "$['@graph'][0].sameAs",
                   "fragment_hash": _sha(blocks[0].encode("utf-8"))},
        "derived_at": generated_at,
        "derivation": "jsonld.path_lookup.v1",
        "content_hash": jfk_snap["content_hash"],
        "verification": {"method": "reparse_jsonld", "steps": [
            "GET source.locator",
            "Collect <script type=\"application/ld+json\"> blocks in document order; json.loads block at jsonld_index",
            "Resolve json_path; require @graph[0].@type Organization; compare the list to value"]},
        "stability": "changes_per_deploy",
        "prior_values": [{
            "value": [],
            "valid_until": SAME_AS_VALID_UNTIL,
            "source": {"kind": "file", "locator": PRIOR_SNAPSHOT["path"], "snapshot_id": PRIOR_SNAPSHOT["id"],
                       "line": org_line, "excerpt": _line(repo_text, org_line).strip()},
        }],
    })

    doc["generator"] = {"name": LOADER_GENERATOR, "version": "1", "sample_notice": LOADER_NOTICE}
    doc["generated_at"] = generated_at
    doc["source_snapshots"] = doc["source_snapshots"] + [prior_snap]
    doc["facts"] = sorted(doc["facts"] + new, key=lambda f: f["key"])
    return doc
