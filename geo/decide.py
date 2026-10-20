"""Decision engine: the R1, R0, R2, R3, R4 cascade (W4 3.6, 6.2, 6.4, 7.1, 7.2).

Input is a validated RunIndex. Every rule reads Numbers built by number.build,
so a below-minimum statistic is an Insufficient and never decides anything.
There is no composite score: the record keeps each rule's result, the ids it
read, and the independence groups of those ids (confidence_basis).

Order (D1): R1 first, then R0 as the gate on R2 to R4. The first rule that fires
ends the cascade; later rules are not_evaluated. R1 unknown (a blocking key
check is not_checkable and none failed) makes R0 fire with reason
page_checks_incomplete (D5).
"""

import re
from urllib.parse import urlsplit

from . import SCHEMA_VERSION, number
from .number import Insufficient, Number
from .records import _finish
from .render import NOT_CHECKED_BASELINE

RULE_SET_VERSION = 1
ORDER = ("R1", "R0", "R2", "R3", "R4")
OUTCOMES = {"R0": "insufficient_evidence", "R1": "seo_first", "R2": "geo_fix_facts", "R3": "geo_content",
            "R4": "no_action"}
HYPOTHESIS_RULES = ("R1", "R3")
RESULTS = ("fired", "not_fired", "unknown", "not_evaluated")
CONTRA_VERDICTS = ("contradicted", "outdated")
SCOPE = "site"

COMMON_FIELDS = ("kind", "schema_version", "id", "identity_sha256", "run_id", "created_at", "tool_build")
DECISION_FIELDS = COMMON_FIELDS + (
    "scope", "rule_set_version", "outcome", "fired_rule_id", "evaluations", "input_ids", "numbers",
    "hypothesis", "assumption_refs", "confidence_basis", "thresholds_snapshot", "why", "not_checked")


class DecisionError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__("%s: %s" % (code, message))


def assumption_refs(fired_rule_id):
    return ["A6", "A7"] if fired_rule_id == "R1" else ["A7"]


def threshold_problems(thresholds):
    """Messages for a manifest.thresholds that is not exactly the provisional registry."""
    expected = number.threshold_values()
    if not isinstance(thresholds, dict):
        return ["thresholds is not an object"]
    out = []
    for k in sorted(set(expected) | set(thresholds)):
        if k not in thresholds:
            out.append("thresholds lacks %s" % k)
        elif k not in expected:
            out.append("thresholds has unknown %s" % k)
        elif thresholds[k] != expected[k] or isinstance(thresholds[k], bool):
            out.append("thresholds %s=%r but the registry says %r" % (k, thresholds[k], expected[k]))
    return out


# --- site and mention matching (W4 6.1 principle 6) ---------------------------

def site_host(manifest):
    """The host shared by every key page, without a leading www. (project choice, PROGRESS Step 6)."""
    hosts = {urlsplit(u).hostname for u in manifest["key_pages"]}
    if len(hosts) != 1:
        raise DecisionError("E_SITE", "key pages must share one host, got %s" % sorted(hosts))
    host = hosts.pop()
    return host[4:] if host.startswith("www.") else host


def cites_site(capture, site):
    for c in capture["citations"]:
        host = urlsplit(c["url"]).hostname or ""
        if host == site or host.endswith("." + site):
            return True
    return False


def mentions_site(capture, terms):
    text = capture["answer_text"] or ""
    return any(re.search(r"(?<!\w)%s(?!\w)" % re.escape(t), text, re.I) for t in terms)


# --- statistics ----------------------------------------------------------------

def _window(records, field):
    times = [r[field] for r in records]
    return (min(times), max(times)) if times else None


def _ids(records):
    return [r["id"] for r in records]


def blocking_fail(page_checks):
    key = [r for r in page_checks if r["url_role"] == "key" and r["blocking_on_fail"]]
    checked = [r for r in key if r["result"] in ("pass", "fail")]
    return key, number.build(
        "blocking_fail.key_pages", "count", sum(r["result"] == "fail" for r in checked), _ids(checked),
        hit_ids=[r["id"] for r in checked if r["result"] == "fail"],
        excluded=[(r["id"], "not_checkable") for r in key if r["result"] == "not_checkable"],
        window=_window(checked, "fetched_at"))


def capture_numbers(manifest, captures):
    """Per engine: per-prompt citation and mention rates, then the pooled citation_rate.engine.

    Only prompts whose citation_rate.engine_prompt is a Number feed the pool (D2).
    Returns {engine: {"prompt": [Number|Insufficient...], "engine": Number|Insufficient, "ok": [cap...]}}.
    """
    site = site_host(manifest)
    out = {}
    for snap in manifest["engines"]:
        engine = snap["engine"]
        caps = [c for c in captures if c["engine"] == engine]
        prompt_nums, pool, pool_excl = [], [], []
        for prompt_id in sorted({c["prompt_id"] for c in caps}):
            attempts = [c for c in caps if c["prompt_id"] == prompt_id]
            ok = [c for c in attempts if c["status"] == "ok"]
            excl = [(c["id"], c["status"]) for c in attempts if c["status"] != "ok"]
            scope = {"engine": engine, "prompt_id": prompt_id}
            cited = [c["id"] for c in ok if cites_site(c, site)]
            mentioned = [c["id"] for c in ok if mentions_site(c, manifest["mention_terms"])]
            cit = number.build("citation_rate.engine_prompt", "rate", len(cited), _ids(ok), cited, excl,
                               _window(ok, "completed_at"), scope=scope)
            men = number.build("mention_rate.engine_prompt", "rate", len(mentioned), _ids(ok), mentioned, excl,
                               _window(ok, "completed_at"), scope=scope)
            prompt_nums += [cit, men]
            if isinstance(cit, Number):
                pool += ok
                pool_excl += excl
        hits = [c["id"] for c in pool if cites_site(c, site)]
        eng = number.build("citation_rate.engine", "rate", len(hits), _ids(pool), hits, pool_excl,
                           _window(pool, "completed_at"), scope={"engine": engine})
        out[engine] = {"vendor": snap["model_vendor"], "prompt": prompt_nums, "engine": eng,
                       "ok": [c for c in caps if c["status"] == "ok"]}
    return out


def rule_claims(claims):
    return [c for c in claims if c["matcher"] == "rule" and c["fact_key"] is not None]


def contradiction_numbers(manifest, captures, claims):
    by_cap = {}
    for c in rule_claims(claims):
        by_cap.setdefault(c["capture_id"], []).append(c)
    out = {}
    for snap in manifest["engines"]:
        engine = snap["engine"]
        eligible = [c for c in captures if c["engine"] == engine and c["status"] == "ok" and c["id"] in by_cap]
        hits = [c["id"] for c in eligible if any(x["verdict"] in CONTRA_VERDICTS for x in by_cap[c["id"]])]
        out[engine] = number.build("contradiction_rate.engine", "rate", len(hits), _ids(eligible), hits,
                                   window=_window(eligible, "completed_at"), scope={"engine": engine})
    return out


def is_low(num, t_low_percent):
    return num.value * 100 < t_low_percent * num.n


# --- confidence basis (W4 6.4) --------------------------------------------------

def group_key(eid, lookup):
    """lookup(id) -> record dict or None. Raises DecisionError for an id with no group rule yet."""
    rec = lookup(eid)
    prefix = eid.split("_", 1)[0]
    if rec is None:
        raise DecisionError("E_REF_UNRESOLVED", "%s does not resolve" % eid)
    if prefix == "pc":
        return "site:" + urlsplit(rec["url_norm"]).hostname
    if prefix == "cap":
        return "vendor:" + rec["engine_snapshot"]["model_vendor"]
    if prefix == "clm":
        return group_key(rec["capture_id"], lookup)
    if prefix == "src" and rec.get("url"):
        return "published:" + urlsplit(rec["url"]).hostname
    raise DecisionError("E_DECISION", "no independence group rule for %s yet" % eid)


def confidence_basis(input_ids, lookup):
    groups = {}
    for eid in input_ids:
        groups.setdefault(group_key(eid, lookup), []).append(eid)
    return [{"group_key": g, "evidence_ids": sorted(groups[g])} for g in sorted(groups)]


# --- the cascade -----------------------------------------------------------------

def _eval(rule_id, result, reason_code, input_ids=()):
    return {"rule_id": rule_id, "result": result, "reason_code": reason_code, "input_ids": sorted(set(input_ids))}


def evaluate(manifest, page_checks, captures, claims):
    """Return (evaluations, fired_rule_id, numbers). Pure: reads records only."""
    t = manifest["thresholds"]
    key, bf = blocking_fail(page_checks)
    if not key:
        raise DecisionError("E_NO_PAGE_CHECKS", "no blocking key-page checks; run page checks first")
    cap_nums = capture_numbers(manifest, captures)
    contra = contradiction_numbers(manifest, captures, claims)
    numbers = [bf]
    for engine in sorted(cap_nums):
        numbers += cap_nums[engine]["prompt"] + [cap_nums[engine]["engine"], contra[engine]]

    evals = []
    not_checkable = [r["id"] for r in key if r["result"] == "not_checkable"]
    fails = [r["id"] for r in key if r["result"] == "fail"]
    if fails:
        evals.append(_eval("R1", "fired", "blocking_fail", _ids(key)))
    elif not_checkable:
        evals.append(_eval("R1", "unknown", "page_checks_incomplete", _ids(key)))
    else:
        evals.append(_eval("R1", "not_fired", "blocking_checks_pass", _ids(key)))

    def finish(fired):
        done = {e["rule_id"] for e in evals}
        evals.extend(_eval(r, "not_evaluated", "cascade_stopped") for r in ORDER if r not in done)
        return evals, fired, numbers

    if fails:
        return finish("R1")

    if not_checkable:
        evals.append(_eval("R0", "fired", "page_checks_incomplete", not_checkable))
        return finish("R0")
    all_ok = [c["id"] for e in cap_nums.values() for c in e["ok"]]
    sufficient = {e: v for e, v in cap_nums.items() if isinstance(v["engine"], Number)}
    vendors = {v["vendor"] for v in sufficient.values()}
    if len(vendors) < t["MIN_ENGINES"]:
        evals.append(_eval("R0", "fired", "engines_below_minimum", all_ok))
        return finish("R0")
    evals.append(_eval("R0", "not_fired", "engines_sufficient",
                       [i for v in sufficient.values() for i in v["engine"].evidence_ids]))

    eligible = [c for c in rule_claims(claims) if c["capture_id"] in set(all_ok)]
    by_key = {}
    for c in eligible:
        if c["verdict"] in CONTRA_VERDICTS:
            by_key.setdefault(c["fact_key"], []).append(c)
    reproduced = [k for k in sorted(by_key)
                  if len({c["capture_id"] for c in by_key[k]}) >= t["K_CONTRA_REPRODUCE"]]
    if reproduced:
        hit = [c for k in reproduced for c in by_key[k]]
        evals.append(_eval("R2", "fired", "contradiction_reproduced",
                           [c["id"] for c in hit] + [c["capture_id"] for c in hit]))
        return finish("R2")
    evals.append(_eval("R2", "not_fired", "no_reproduced_contradiction",
                       [c["id"] for c in eligible] + [c["capture_id"] for c in eligible]))

    by_vendor = {}
    for v in sufficient.values():
        by_vendor.setdefault(v["vendor"], []).append(v["engine"])
    low = [vd for vd in sorted(by_vendor) if all(is_low(n, t["T_LOW_PERCENT"]) for n in by_vendor[vd])]
    if len(low) >= t["MIN_ENGINES"]:
        evals.append(_eval("R3", "fired", "citation_low_in_vendors",
                           [i for vd in low for n in by_vendor[vd] for i in n.evidence_ids]))
        return finish("R3")
    evals.append(_eval("R3", "not_fired", "citation_not_low",
                       [i for ns in by_vendor.values() for n in ns for i in n.evidence_ids]))

    evals.append(_eval("R4", "fired", "no_rule_fired", [i for e in evals for i in e["input_ids"]]))
    return finish("R4")


def not_checked_items(manifest, page_checks, claims, numbers, evaluations):
    """W4 5.5 sources (a) to (f), plus rules the cascade did not reach."""
    items = [{"item": item, "reason_code": "baseline", "detail": text} for item, text in NOT_CHECKED_BASELINE]
    for e in manifest["engines_excluded"]:
        items.append({"item": "engine_excluded", "reason_code": e["reason"], "detail": e["engine"]})
    for s in manifest["skipped_slots"]:
        items.append({"item": "skipped_slot", "reason_code": s["reason"],
                      "detail": "%s %s repeat %d" % (s["engine"], s["prompt_id"], s["repeat_index"])})
    for r in page_checks:
        if r["result"] == "not_checkable":
            items.append({"item": "page_check_not_checkable", "reason_code": r["not_checkable_reason"],
                          "detail": r["id"]})
    for c in claims:
        if c["verdict"] in ("needs_review", "unsupported"):
            items.append({"item": "claim_" + c["verdict"], "reason_code": c["verdict_basis"], "detail": c["id"]})
    for n in numbers:
        if isinstance(n, Insufficient):
            where = " ".join("%s=%s" % kv for kv in sorted(n.scope.items()))
            items.append({"item": "insufficient", "reason_code": "below_min_n",
                          "detail": ("%s %s" % (n.statistic_id, where)).strip()})
    for e in evaluations:
        if e["result"] == "not_evaluated":
            items.append({"item": "rule_not_evaluated", "reason_code": e["reason_code"], "detail": e["rule_id"]})
    return items


def decide(index, created_at):
    """Build the decision record for a validated RunIndex. The caller appends it to the run."""
    m = index.manifest
    problems = threshold_problems(m["thresholds"])
    if problems:
        raise DecisionError("E_THRESHOLDS", "; ".join(problems))
    page_checks = index.of_kind("page_check")
    captures = index.of_kind("capture")
    claims = index.of_kind("claim")
    evals, fired, numbers = evaluate(m, page_checks, captures, claims)
    input_ids = sorted({i for e in evals for i in e["input_ids"]})

    def lookup(eid):
        ev = index.lookup(eid)
        return None if ev is None else ev.record

    rec = {
        "kind": "decision",
        "schema_version": SCHEMA_VERSION,
        "run_id": m["run_id"],
        "created_at": created_at,
        "tool_build": m["tool_build"],
        "scope": SCOPE,
        "rule_set_version": RULE_SET_VERSION,
        "outcome": OUTCOMES[fired],
        "fired_rule_id": fired,
        "evaluations": evals,
        "input_ids": input_ids,
        "numbers": [number.to_dict(n) for n in numbers],
        "hypothesis": fired in HYPOTHESIS_RULES,
        "assumption_refs": assumption_refs(fired),
        "confidence_basis": confidence_basis(input_ids, lookup),
        "thresholds_snapshot": dict(m["thresholds"]),
        "why": [{"template_id": "%s.%s" % (e["rule_id"], e["reason_code"]), "evidence_ids": e["input_ids"]}
                for e in evals if e["result"] != "not_evaluated"],
        "not_checked": not_checked_items(m, page_checks, claims, numbers, evals),
    }
    return _finish(rec, SCOPE)


def decision_problems(rec, manifest):
    """V23 consistency messages for a decision record (outcome, order, hypothesis, refs, thresholds)."""
    out = []
    fired = rec["fired_rule_id"]
    if fired not in OUTCOMES:
        return ["fired_rule_id %r is not R0 to R4" % (fired,)]
    if rec["outcome"] != OUTCOMES[fired]:
        out.append("outcome %r does not match %s (%s)" % (rec["outcome"], fired, OUTCOMES[fired]))
    evals = rec["evaluations"]
    shape = ("rule_id", "result", "reason_code", "input_ids")
    if (not isinstance(evals, list) or not all(isinstance(e, dict) and set(e) == set(shape) for e in evals)
            or [e["rule_id"] for e in evals] != list(ORDER)):
        return out + ["evaluations must be one entry per rule in order %s" % (ORDER,)]
    pos = ORDER.index(fired)
    for i, e in enumerate(evals):
        r = e["result"]
        if r not in RESULTS or not isinstance(e["reason_code"], str) or not isinstance(e["input_ids"], list):
            out.append("bad evaluation %r" % (e,))
        elif i == pos and r != "fired":
            out.append("%s is the fired rule but its result is %s" % (fired, r))
        elif i > pos and r != "not_evaluated":
            out.append("%s comes after the fired rule but is %s" % (e["rule_id"], r))
        elif i < pos and r != "not_fired" and not (e["rule_id"] == "R1" and r == "unknown" and fired == "R0"):
            out.append("%s comes before the fired rule but is %s" % (e["rule_id"], r))
    union = sorted({i for e in evals if isinstance(e["input_ids"], list) for i in e["input_ids"]})
    if not rec["input_ids"] or rec["input_ids"] != union:
        out.append("input_ids must be the non-empty sorted union of evaluation input_ids")
    if rec["hypothesis"] is not (fired in HYPOTHESIS_RULES):
        out.append("hypothesis must be %s for %s" % (fired in HYPOTHESIS_RULES, fired))
    refs = rec["assumption_refs"]
    if (not isinstance(refs, list) or not all(isinstance(a, str) and re.fullmatch(r"A[0-9]+", a) for a in refs)
            or "A7" not in refs or (fired == "R1" and "A6" not in refs)):
        out.append("assumption_refs %r must contain A7, and A6 when R1 fired" % (refs,))
    why = rec["why"]
    if (not isinstance(why, list) or not why
            or not all(isinstance(w, dict) and set(w) == {"template_id", "evidence_ids"}
                       and isinstance(w["evidence_ids"], list) and set(w["evidence_ids"]) <= set(union)
                       for w in why)):
        out.append("why must be non-empty and cite only input_ids")
    if rec["thresholds_snapshot"] != manifest["thresholds"]:
        out.append("thresholds_snapshot does not equal manifest.thresholds")
    if rec["scope"] != SCOPE:
        out.append("scope must be %s" % SCOPE)
    return out
