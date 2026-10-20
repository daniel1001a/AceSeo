"""Rule claim matcher and claim records (W4 3.5; W3 3.3; PLAN 6.2).

The matcher splits an answer into sentences and gives each sentence at most one
claim. A sentence becomes a claim only when it hits a known topic. It is decided
(matched, contradicted, outdated) only when the sentence is about the site, hits
exactly one topic, the asserted value parses, and the fact exists. A topic whose
fact is absent gives unsupported. Everything else is needs_review: an unparsed
value, a hedge, two topics in one sentence, no site mention, or a mention of
another domain that shares the site name (W3 wrong_entity).

Digit classes are [0-9], never \\d (W4 F14).
"""

import re
from collections import namedtuple

from . import SCHEMA_VERSION, ids
from .facts import facts_by_key
from .records import _finish

MATCHER = "rule"
# v2: topic readers and the entity check see the sentence with Markdown
# emphasis and code marks removed. Real answers bold the value
# ("covers **33 US airports**"), which v1 read as no value.
MATCHER_VERSION = 2
MATCHERS = ("rule", "llm")

VERDICT_BASES = {
    "matched": ("exact", "normalized"),
    "contradicted": ("value_mismatch",),
    "outdated": ("prior_value",),
    "unsupported": ("no_fact",),
    "needs_review": ("undecided",),
}
NO_FACT_VERDICTS = ("unsupported", "needs_review")

Spec = namedtuple("Spec", "span_start span_end topic fact_key verdict verdict_basis")

UNDECIDED = object()   # the topic hit, but no value could be read
NOT_LIVE = "not_live"  # inactive, down, parked: not one of the W3 site_status values
HAS_PROFILES = "has_profiles"

_I = re.I
_MARKUP = re.compile(r"\*\*|__|`")

# A sentence ends at . ! ? followed by space or end (so "boardflight.com" stays
# whole) but not after an abbreviation such as "U.S.", at a CJK full stop, or at
# a line end.
_SENTENCE = re.compile(r"\S[^\n]*?(?:(?<!\.[A-Za-z])[.!?](?=\s|$)|[。！？]|$)", re.M)
_DOMAIN = re.compile(r"(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(?![A-Za-z0-9-])")


# --- topics ------------------------------------------------------------------

_STATUS_NEG = re.compile(
    r"\b(?:inactive|defunct|parked|offline|abandoned|shut\s+down|no\s+longer\s+(?:operating|active|available|online|"
    r"maintained)|not\s+(?:operating|active|operational|live|online|available)|is\s+(?:currently\s+)?down|"
    r"no\s+active\s+(?:live\s+)?service)\b"
    r"|已停用|停止營運|停止运营|已關閉|已关闭|沒有在營運|没有在运营|不再營運|不再运营|已失效|無法使用|无法使用", _I)
_STATUS_POS = re.compile(
    r"\b(?:is\s+(?:currently\s+|still\s+)?(?:live|online|active|operational|up\s+and\s+running)|"
    r"still\s+(?:operating|active|online)|actively\s+maintained)\b"
    r"|仍在營運|還在營運|仍在运营|还在运营|正常營運|正常运营", _I)

_COUNT = re.compile(r"\bcover(?:s|ed|ing)?\s+([^\n]{0,40}?)\s*\bairports\b", _I)
_COUNT_VALUE = re.compile(r"([0-9]{1,4})(?:\s+(?:US|U\.S\.|United\s+States))?", _I)

_FREE_POS = re.compile(
    r"\b(?:is\s+(?:completely\s+|totally\s+|entirely\s+)?free|free\s+to\s+use|free\s+of\s+charge|"
    r"no\s+account\s+(?:is\s+)?(?:needed|required)|costs?\s+nothing)\b", _I)
_FREE_NEG = re.compile(
    r"\b(?:is\s+not\s+free|isn't\s+free|paid\s+(?:app|service|subscription|plan|tier)|"
    r"requires?\s+(?:a\s+)?(?:paid\s+)?(?:subscription|account)|subscription\s+fee)\b|\bcosts?\s+\$[0-9]", _I)

_LIVE_NEG = re.compile(
    r"\b(?:uses?\s+no\s+(?:real[- ]time|live)|(?:does\s+not|doesn't|do\s+not)\s+(?:use|provide|show)\s+"
    r"(?:any\s+)?(?:real[- ]time|live)|no\s+(?:real[- ]time|live)\s+(?:queue|wait|security|tsa)|"
    r"not\s+(?:real[- ]time|live)\s+(?:queue|wait|data))", _I)
_LIVE_POS = re.compile(
    r"\b(?:(?:uses?|provides?|shows?|offers?|displays?)\s+(?:real[- ]time|live)\s+(?:(?:security|tsa|queue|wait|"
    r"checkpoint)\s+)*(?:data|wait\s+times|times|updates|feeds?)|real[- ]time\s+(?:(?:tsa|security|checkpoint)\s+)?"
    r"(?:wait|queue)\s+times|live\s+queue\s+data)\b", _I)

_SAMEAS_NONE = re.compile(
    r"\b(?:no|without|lacks?|(?:does\s+not|doesn't)\s+have)\s+(?:any\s+)?(?:official\s+|verified\s+|public\s+)?"
    r"(?:social(?:\s+media)?\s+(?:profiles?|accounts?|presence)|linkedin|github|profiles?)\b", _I)
_SAMEAS_SOME = re.compile(r"\bhas\s+(?:an?\s+)?(?:official\s+)?(?:linkedin|github)\b", _I)

# Topics with no fact in any facts file yet: a site claim about them is unsupported.
_NO_FACT = re.compile(
    r"\b(?:founded|launched|established)\s+in\s+[0-9]{4}\b|\bheadquartered\b|\b(?:ios|android)\s+app\b|"
    r"\bapp\s+store\b|\bemployees\b", _I)


def _site_status(s):
    neg, pos = _STATUS_NEG.search(s), _STATUS_POS.search(s)
    if not (neg or pos):
        return None
    if neg and pos:
        return UNDECIDED
    return NOT_LIVE if neg else "live"


def _airport_count(s):
    m = _COUNT.search(s)
    if not m:
        return None
    v = _COUNT_VALUE.fullmatch(m.group(1).strip())
    return int(v.group(1)) if v else UNDECIDED  # hedges ("about 40") and words stay undecided


def _pair(pos_re, neg_re, pos_value, neg_value, negation_wins):
    def topic(s):
        neg, pos = neg_re.search(s), pos_re.search(s)
        if not (neg or pos):
            return None
        if neg and pos and not negation_wins:
            return UNDECIDED
        return neg_value if neg else pos_value
    return topic


def _same_as(s):
    none, some = _SAMEAS_NONE.search(s), _SAMEAS_SOME.search(s)
    if not (none or some):
        return None
    if none and some:
        return UNDECIDED
    return [] if none else HAS_PROFILES


# (topic, fact_key, reader). A reader returns None (no hit), UNDECIDED or the
# asserted value. The negated live-data phrases contain the positive ones
# ("does not use live queue data"), so for that topic the negation wins.
TOPICS = (
    ("site_status", "site_status", _site_status),
    ("airport_count", "llms.coverage.airport_count", _airport_count),
    ("is_free", "llms.offer.is_free", _pair(_FREE_POS, _FREE_NEG, True, False, negation_wins=False)),
    ("uses_live_queue_data", "llms.data.uses_live_queue_data",
     _pair(_LIVE_POS, _LIVE_NEG, True, False, negation_wins=True)),
    ("same_as", "jsonld.organization.same_as", _same_as),
)


# --- entity -------------------------------------------------------------------

def _entity(sentence, site):
    """site, other (a different domain that shares the site name) or none."""
    hosts = {h.lower() for h in site.get("hosts", ())}
    name = site.get("name") or ""
    stem = name.lower()
    mentions_site = other = False
    covered = []
    for m in _DOMAIN.finditer(sentence):
        host = m.group(1).lower().rstrip(".")
        covered.append(m.span())
        if host in hosts:
            mentions_site = True
        elif stem and stem in host:
            other = True
    if name:
        for m in re.finditer(r"\b%s\b" % re.escape(name), sentence, _I):
            if not any(a <= m.start() < b for a, b in covered):
                mentions_site = True
    if other:
        return "other"
    return "site" if mentions_site else "none"


def sentences(text):
    """(start, end) spans; end excludes trailing whitespace."""
    out = []
    for m in _SENTENCE.finditer(text or ""):
        s, e = m.span()
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            out.append((s, e))
    return out


# --- verdicts -----------------------------------------------------------------

def _same(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return a == b
    return type(a) is type(b) and a == b


def _decide(topic, fact, asserted):
    current = fact["value"]
    priors = [p.get("value") for p in fact.get("prior_values") or () if isinstance(p, dict)]
    if topic == "site_status":
        if asserted == "live":
            return ("matched", "normalized") if current == "live" else ("contradicted", "value_mismatch")
        # "inactive" is not a W3 status; it only contradicts a live site (W3 3.3).
        return ("contradicted", "value_mismatch") if current == "live" else ("needs_review", "undecided")
    if topic == "same_as" and asserted == HAS_PROFILES:
        return ("matched", "normalized") if current else ("contradicted", "value_mismatch")
    if _same(asserted, current):
        return ("matched", "exact") if topic == "airport_count" else ("matched", "normalized")
    if any(_same(asserted, p) for p in priors):
        return ("outdated", "prior_value")
    return ("contradicted", "value_mismatch")


def match_text(text, facts_doc):
    """Return one Spec per claim-bearing sentence of text, in text order."""
    site = facts_doc.get("site") or {}
    facts = facts_by_key(facts_doc)
    out = []
    for s, e in sentences(text):
        sent = _MARKUP.sub("", text[s:e])
        hits = [(topic, key, value) for topic, key, read in TOPICS
                for value in [read(sent)] if value is not None]
        no_fact = _NO_FACT.search(sent) is not None
        if not hits and not no_fact:
            continue
        entity = _entity(sent, site)
        if len(hits) + int(no_fact) > 1 or entity != "site":
            topic = hits[0][0] if len(hits) == 1 and not no_fact else None
            out.append(Spec(s, e, topic, None, "needs_review", "undecided"))
            continue
        if no_fact:
            out.append(Spec(s, e, None, None, "unsupported", "no_fact"))
            continue
        topic, key, value = hits[0]
        fact = facts.get(key)
        if value is UNDECIDED:
            out.append(Spec(s, e, topic, None, "needs_review", "undecided"))
        elif fact is None:
            out.append(Spec(s, e, topic, None, "unsupported", "no_fact"))
        else:
            verdict, basis = _decide(topic, fact, value)
            fk = key if verdict not in NO_FACT_VERDICTS else None
            out.append(Spec(s, e, topic, fk, verdict, basis))
    return out


# --- records ------------------------------------------------------------------

def claim_record(manifest, capture, *, span_start, span_end, statement, fact_key, fact_value_snapshot,
                 verdict, verdict_basis, created_at, matcher=MATCHER, matcher_version=MATCHER_VERSION,
                 fact_ref=None, facts_sha256=None):
    """Build one claim record. fact_ref and facts_sha256 default to the computed values."""
    sha = manifest["facts_sha256"] if facts_sha256 is None else facts_sha256
    rec = {
        "kind": "claim",
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "created_at": created_at,
        "tool_build": manifest["tool_build"],
        "capture_id": capture["id"],
        "span_start": span_start,
        "span_end": span_end,
        "statement": statement,
        "fact_key": fact_key,
        "fact_ref": fact_ref if fact_ref is not None or fact_key is None else ids.fct_ref(sha, fact_key),
        "facts_sha256": sha,
        "fact_value_snapshot": fact_value_snapshot,
        "verdict": verdict,
        "verdict_basis": verdict_basis,
        "matcher": matcher,
        "matcher_version": matcher_version,
    }
    return _finish(rec, capture["engine"])


def claims_for_capture(manifest, capture, facts_doc, created_at):
    """Rule-matcher claims for one ok capture; none for other statuses."""
    if capture.get("status") != "ok":
        return []
    text = capture.get("answer_text") or ""
    facts = facts_by_key(facts_doc)
    out = []
    for sp in match_text(text, facts_doc):
        out.append(claim_record(
            manifest, capture, span_start=sp.span_start, span_end=sp.span_end,
            statement=text[sp.span_start:sp.span_end], fact_key=sp.fact_key,
            fact_value_snapshot=facts[sp.fact_key]["value"] if sp.fact_key else None,
            verdict=sp.verdict, verdict_basis=sp.verdict_basis, created_at=created_at))
    return out


def claims_for_run(manifest, captures, facts_doc, created_at):
    out = []
    for cap in sorted(captures, key=lambda c: c["id"]):
        out.extend(claims_for_capture(manifest, cap, facts_doc, created_at))
    return out
