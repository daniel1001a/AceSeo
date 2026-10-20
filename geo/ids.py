"""Evidence ids, identity hashing, series keys and URL normalisation (W4 2.3, 2.4).

All patterns use [0-9], never \\d, and are applied with fullmatch so a trailing
newline cannot slip through "$".
"""

import re
from urllib.parse import urlsplit, urlunsplit

from .canonical import canonical_bytes, sha256_hex

ID_DOMAIN = b"geo-evidence/id/v1\n"

SLUG_PATTERN = r"[a-z0-9](?:[a-z0-9-]{0,22}[a-z0-9])?"
SLUG = re.compile(SLUG_PATTERN)
RUN_ID = re.compile(r"run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{6}")
RECORD_ID = re.compile(r"(?P<prefix>cap|pc|clm|dec)_(?P<slug>%s)_(?P<h>[0-9a-f]{16})" % SLUG_PATTERN)
AUX_REF = re.compile(r"(?P<prefix>fct|src)_(?P<h>[0-9a-f]{16})")
SHA256 = re.compile(r"[0-9a-f]{64}")
TS = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z")
TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

KIND_PREFIX = {"capture": "cap", "page_check": "pc", "claim": "clm", "decision": "dec"}
PREFIX_KIND = {v: k for k, v in KIND_PREFIX.items()}

IDENTITY_KEYS = {
    "capture": ("kind", "run_id", "engine", "model", "tool_version", "prompt_id",
                "prompt_sha256", "repeat_index", "attempt"),
    "page_check": ("kind", "run_id", "check_name", "check_version", "url_norm",
                   "agent_profile", "params"),
    "claim": ("kind", "run_id", "capture_id", "facts_sha256", "matcher", "matcher_version",
              "span_start", "span_end"),
    "decision": ("kind", "run_id", "rule_set_version", "scope"),
    "fct": ("kind", "facts_sha256", "fact_key"),
    "src": ("kind", "url", "retrieved", "locator"),
}

DEFAULT_PORTS = {"http": 80, "https": 443}


class IdError(ValueError):
    pass


def is_slug(s):
    return isinstance(s, str) and SLUG.fullmatch(s) is not None


def is_record_id(s):
    return isinstance(s, str) and RECORD_ID.fullmatch(s) is not None


def is_evidence_id(s):
    return isinstance(s, str) and (RECORD_ID.fullmatch(s) is not None or AUX_REF.fullmatch(s) is not None)


def evidence_prefix(s):
    m = RECORD_ID.fullmatch(s) or AUX_REF.fullmatch(s)
    return m.group("prefix") if m else None


def _check_identity(identity):
    kind = identity.get("kind")
    keys = IDENTITY_KEYS.get(kind)
    if keys is None:
        raise IdError("unknown identity kind: %r" % (kind,))
    if set(identity) != set(keys):
        raise IdError("identity for %s must have exactly %s" % (kind, ", ".join(keys)))
    for key, value in identity.items():
        if isinstance(value, float):
            raise IdError("identity field %s is a float" % key)


def identity_sha256(identity):
    _check_identity(identity)
    return sha256_hex(ID_DOMAIN + canonical_bytes(identity))


def make_id(identity, slug):
    """Record id for capture, page_check, claim or decision."""
    prefix = KIND_PREFIX.get(identity.get("kind"))
    if prefix is None:
        raise IdError("not a record kind: %r" % (identity.get("kind"),))
    if not is_slug(slug):
        raise IdError("bad slug: %r" % (slug,))
    return "%s_%s_%s" % (prefix, slug, identity_sha256(identity)[:16])


def fct_ref(facts_sha256, fact_key):
    return "fct_" + identity_sha256({"kind": "fct", "facts_sha256": facts_sha256, "fact_key": fact_key})[:16]


def src_ref(url, retrieved, locator):
    return "src_" + identity_sha256({"kind": "src", "url": url, "retrieved": retrieved, "locator": locator})[:16]


def series_key(identity):
    """sha256 of the identity dict without run_id and attempt (W4 2.4); no domain prefix."""
    _check_identity(identity)
    rest = {k: v for k, v in identity.items() if k not in ("run_id", "attempt")}
    return sha256_hex(canonical_bytes(rest))


def capture_identity(record):
    snap = record.get("engine_snapshot") or {}
    return {
        "kind": "capture",
        "run_id": record.get("run_id"),
        "engine": record.get("engine"),
        "model": snap.get("model"),
        "tool_version": snap.get("tool_version"),
        "prompt_id": record.get("prompt_id"),
        "prompt_sha256": record.get("prompt_sha256"),
        "repeat_index": record.get("repeat_index"),
        "attempt": record.get("attempt"),
    }


def record_identity(record):
    kind = record.get("kind")
    if kind == "capture":
        return capture_identity(record)
    keys = IDENTITY_KEYS.get(kind)
    if keys is None or kind not in KIND_PREFIX:
        raise IdError("not a record kind: %r" % (kind,))
    return {k: record.get(k) for k in keys}


def record_slug(record, claim_engine=None):
    kind = record.get("kind")
    if kind == "capture":
        return record.get("engine")
    if kind == "page_check":
        return record.get("check_name")
    if kind == "claim":
        return claim_engine
    if kind == "decision":
        return record.get("scope")
    return None


def id_problems(record, claim_engine=None):
    """Return a list of messages; empty when id and identity_sha256 match the record."""
    rid = record.get("id")
    m = RECORD_ID.fullmatch(rid) if isinstance(rid, str) else None
    if m is None:
        return ["id %r does not match RECORD_ID" % (rid,)]
    problems = []
    kind = record.get("kind")
    if PREFIX_KIND.get(m.group("prefix")) != kind:
        problems.append("id prefix %s does not match kind %s" % (m.group("prefix"), kind))
    slug = record_slug(record, claim_engine)
    if slug is not None and m.group("slug") != slug:
        problems.append("id slug %s does not match %s" % (m.group("slug"), slug))
    try:
        digest = identity_sha256(record_identity(record))
    except IdError as e:
        return problems + [str(e)]
    if record.get("identity_sha256") != digest:
        problems.append("identity_sha256 does not recompute")
    if m.group("h") != digest[:16]:
        problems.append("id hash %s does not equal recomputed %s" % (m.group("h"), digest[:16]))
    return problems


def make_run_id(plan_sha256, started_at):
    """run_<YYYYMMDDTHHMMSSZ>_<hex6>; started_at is a W4 ts string."""
    if not TS.fullmatch(started_at or ""):
        raise IdError("started_at must be a ts: %r" % (started_at,))
    if not SHA256.fullmatch(plan_sha256 or ""):
        raise IdError("plan_sha256 must be a sha256 hex")
    stamp = started_at[0:4] + started_at[5:7] + started_at[8:10] + "T" + \
        started_at[11:13] + started_at[14:16] + started_at[17:19] + "Z"
    hex6 = sha256_hex(canonical_bytes({"plan_sha256": plan_sha256, "started_at": started_at}))[:6]
    return "run_%s_%s" % (stamp, hex6)


def url_norm_v1(url):
    """Lowercase scheme and host, drop default port and fragment, keep path and query exact."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise IdError("not an absolute http(s) URL: %r" % (url,))
    host = parts.hostname.lower()
    if ":" in host:
        host = "[%s]" % host
    port = parts.port
    netloc = host if port is None or port == DEFAULT_PORTS[scheme] else "%s:%d" % (host, port)
    if parts.username is not None or parts.password is not None:
        userinfo = parts.netloc.rpartition("@")[0]
        netloc = userinfo + "@" + netloc
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))
