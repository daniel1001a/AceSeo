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
# v3: no site-specific patterns. Besides the three built-in topics, a fact is
# matched only through the "match" block declared in the facts file.
MATCHER_VERSION = 3
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

_FREE_POS = re.compile(
    r"\b(?:is\s+(?:completely\s+|totally\s+|entirely\s+)?free|free\s+to\s+use|free\s+of\s+charge|"
    r"no\s+account\s+(?:is\s+)?(?:needed|required)|costs?\s+nothing)\b", _I)
_FREE_NEG = re.compile(
    r"\b(?:is\s+not\s+free|isn't\s+free|paid\s+(?:app|service|subscription|plan|tier)|"
    r"requires?\s+(?:a\s+)?(?:paid\s+)?(?:subscription|account)|subscription\s+fee)\b|\bcosts?\s+\$[0-9]", _I)

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


# Built-in topics: (topic, fact_key, reader). A reader returns None (no hit),
# UNDECIDED or the asserted value. These three are generic; any other fact is
# matched only through the "match" block its facts file declares.
BUILTIN_TOPICS = (
    ("site_status", "site_status", _site_status),
    ("is_free", "llms.offer.is_free", _pair(_FREE_POS, _FREE_NEG, True, False, negation_wins=False)),
    ("same_as", "jsonld.organization.same_as", _same_as),
)
BUILTIN_KEYS = tuple(sorted(k for _, k, _ in BUILTIN_TOPICS))


# --- declared topics (facts file "match" blocks) --------------------------------

# A hedge right before a number makes the count undecided ("about 33").
_HEDGE = re.compile(
    r"(?:\b(?:about|around|approximately|approx\.?|over|more\s+than|nearly|almost|roughly|at\s+least|"
    r"up\s+to|under|fewer\s+than|less\s+than|some)|~)\s*$", _I)

_RANGE = re.compile(r"[0-9]\s*(?:or|to|-|\u2013)\s*$", _I)  # "3 or 4 plans", "3-4 plans"


def phrase_re(phrases):
    """Literal phrases, case-insensitive, whole words; any run of spaces or
    hyphens in a phrase matches any run of spaces or hyphens in the text."""
    parts = []
    for p in sorted(phrases, key=len, reverse=True):
        words = [w for w in re.split(r"[\s-]+", p.strip()) if w]
        parts.append(r"[\s-]+".join(re.escape(w) for w in words))
    return re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(parts), _I)


def _subject(match):
    terms = match.get("subject_terms")
    return phrase_re(terms) if terms else None


def _boolean_reader(match):
    subj = _subject(match)
    pos = phrase_re(match["positive"]) if match.get("positive") else None
    neg = phrase_re(match["negative"]) if match.get("negative") else None

    def read(s):
        if subj and not subj.search(s):
            return None
        negs = [m.span() for m in neg.finditer(s)] if neg else []
        # A positive phrase inside a negative one ("use live data" in "does not
        # use live data") is part of the negation, not a second hit.
        poss = [m.span() for m in pos.finditer(s)
                if not any(a < m.end() and m.start() < b for a, b in negs)] if pos else []
        if not (negs or poss):
            return None
        if negs and poss:
            return UNDECIDED
        return False if negs else True
    return read


def _integer_reader(match):
    subj = _subject(match)
    unit = phrase_re(match["unit_terms"])
    # A number, then up to two words ("33 US airports"), then a unit term.
    count = re.compile(r"(?<![A-Za-z0-9.,])([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(\+?)\s+(?:(?![0-9])\S+\s+){0,2}?(?:%s)"
                       % unit.pattern[len("(?<![A-Za-z0-9])"):], _I)

    def read(s):
        if subj and not subj.search(s):
            return None
        if not unit.search(s):
            return None
        values = set()
        for m in count.finditer(s):
            if m.group(2) or _HEDGE.search(s[:m.start()]) or _RANGE.search(s[:m.start()]):
                return UNDECIDED
            values.add(int(m.group(1).replace(",", "")))
        if len(values) == 1:
            return values.pop()
        # No plain number ("dozens of", other digits): undecided only when a
        # subject term says the sentence is about this fact.
        return UNDECIDED if values or subj else None
    return read


def _enum_reader(match):
    subj = _subject(match)
    readers = [(v, phrase_re(ps)) for v, ps in sorted(match["values"].items()) if ps]

    def read(s):
        if subj and not subj.search(s):
            return None
        hits = [v for v, r in readers if r.search(s)]
        if not hits:
            return None
        return hits[0] if len(hits) == 1 else UNDECIDED
    return read


DECLARED_READERS = {"boolean": _boolean_reader, "integer": _integer_reader, "enum": _enum_reader}


def topics_for(facts_doc):
    """Built-in topics, then one topic per fact with a match block, keyed by the
    fact key. A declared match block on a built-in key replaces the built-in."""
    declared = {}
    for f in facts_doc.get("facts") or ():
        if isinstance(f, dict) and isinstance(f.get("match"), dict) and f.get("value_type") in DECLARED_READERS:
            declared[f["key"]] = DECLARED_READERS[f["value_type"]](f["match"])
    out = [t for t in BUILTIN_TOPICS if t[1] not in declared]
    out += [(k, k, declared[k]) for k in sorted(declared)]
    return tuple(out)


def matched_keys(facts_doc):
    """Fact keys the rule matcher can decide for this facts file."""
    return tuple(sorted(k for _, k, _ in topics_for(facts_doc)))


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
        return ("matched", "exact") if fact.get("value_type") == "integer" else ("matched", "normalized")
    if any(_same(asserted, p) for p in priors):
        return ("outdated", "prior_value")
    return ("contradicted", "value_mismatch")


def match_text(text, facts_doc):
    """Return one Spec per claim-bearing sentence of text, in text order."""
    site = facts_doc.get("site") or {}
    facts = facts_by_key(facts_doc)
    topics = topics_for(facts_doc)
    out = []
    for s, e in sentences(text):
        sent = _MARKUP.sub("", text[s:e])
        hits = [(topic, key, value) for topic, key, read in topics
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
