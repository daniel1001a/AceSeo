"""Price snapshots and per-call costs in Decimal (W4 3.3 price_snapshot, V15).

Prices are Published and cite a src_ id. Token counts before a call are
Estimated (PLAN A8). When a provider documents no per-call search limit, the
pre-call estimate assumes one search per call and says so (decision 2026-10-19:
OpenAI and Perplexity, label Estimated).
"""

import re
from decimal import Decimal

from . import ids

DEC = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]{1,12})?")
UNITS = ("input_token", "output_token", "cached_input_token", "search_call")
PER = {"1": Decimal(1), "1k": Decimal(1000), "1m": Decimal(1000000)}
CONDITION = re.compile(r"input_tokens>=(0|[1-9][0-9]*)")

ASSUMED_SEARCHES_WHEN_UNCAPPED = 1
SEARCH_BASIS_DOCUMENTED = "documented_max_searches_per_call"
SEARCH_BASIS_ASSUMED = "assumed_1_search_per_call_estimated"


class CostError(ValueError):
    pass


def is_dec(s):
    return isinstance(s, str) and DEC.fullmatch(s) is not None


def dec_str(d):
    """Decimal to a W4 dec string; refuses negatives and more than 12 places."""
    if not isinstance(d, Decimal) or not d.is_finite() or d < 0:
        raise CostError("not a non-negative finite Decimal: %r" % (d,))
    s = format(d.normalize(), "f")
    if s in ("-0", ""):
        s = "0"
    if not DEC.fullmatch(s):
        raise CostError("decimal does not fit the dec format: %s" % s)
    return s


def _source_for(entry, unit):
    sources = entry.get("sources") or []
    if not sources or any(not s.get("url") or not s.get("retrieved") for s in sources):
        raise CostError("price entry lacks a source with url and retrieved date")
    if unit == "search_call":
        for s in sources:
            if "search" in s.get("covers", "").lower():
                return s
    return sources[0]


def price_snapshot(price_key, entry):
    """Return (rows, sources). rows follow W4 3.3; sources are sources.json entries."""
    rows = []
    used = {}

    def add(unit, per, price, condition):
        s = _source_for(entry, unit)
        ref = ids.src_ref(s["url"], s["retrieved"], price_key)
        used[ref] = {"src_ref": ref, "url": s["url"], "retrieved": s["retrieved"], "locator": price_key,
                     "covers": s.get("covers", "")}
        if not is_dec(price):
            raise CostError("%s %s price is not a dec string" % (price_key, unit))
        rows.append({"unit": unit, "per": per, "price_usd": price, "condition": condition, "source_ref": ref})

    add("input_token", "1m", entry["input_per_mtok"], None)
    add("output_token", "1m", entry["output_per_mtok"], None)
    for tier in sorted(entry.get("input_tiers", []), key=lambda t: t["min_prompt_tokens"]):
        cond = "input_tokens>=%d" % tier["min_prompt_tokens"]
        add("input_token", "1m", tier["input_per_mtok"], cond)
        add("output_token", "1m", tier["output_per_mtok"], cond)
    add("search_call", "1", entry["search_per_call"], None)
    return rows, [used[k] for k in sorted(used)]


def _threshold(condition):
    if condition is None:
        return 0
    m = CONDITION.fullmatch(condition)
    if m is None:
        raise CostError("unknown price condition %r" % (condition,))
    return int(m.group(1))


def _rate(rows, unit, input_tokens):
    """Per-unit price for unit: the row with the highest satisfied threshold."""
    best = None
    for r in rows:
        if r["unit"] != unit:
            continue
        t = _threshold(r["condition"])
        if input_tokens >= t and (best is None or t > best[0]):
            best = (t, Decimal(r["price_usd"]) / PER[r["per"]])
    return None if best is None else best[1]


def _total(rows, input_tokens, output_tokens, cached_input_tokens, search_calls):
    total = Decimal(0)
    for unit, qty in (("input_token", input_tokens), ("output_token", output_tokens),
                      ("cached_input_token", cached_input_tokens), ("search_call", search_calls)):
        if not qty:
            continue
        rate = _rate(rows, unit, input_tokens)
        if rate is None:
            return None
        total += Decimal(qty) * rate
    return total


def cost_from_usage(rows, usage):
    """Decimal recomputed from usage x price snapshot, or None if usage is incomplete."""
    if not isinstance(usage, dict):
        return None
    vals = [usage.get(k) for k in ("input_tokens", "output_tokens", "cached_input_tokens", "search_calls")]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in vals):
        return None
    return _total(rows, *vals)


def planned_searches(max_searches_per_call):
    """(upper searches per call, basis). None means the provider documents no cap:
    assume 1 and label it Estimated (decision 2026-10-19)."""
    if max_searches_per_call is None:
        return ASSUMED_SEARCHES_WHEN_UNCAPPED, SEARCH_BASIS_ASSUMED
    return max_searches_per_call, SEARCH_BASIS_DOCUMENTED


def cost_estimate(rows, max_searches_per_call, assumptions):
    """Pre-call Estimated cost. Returns (expected Decimal, detail dict).

    The expected value uses the planning assumption searches_per_call (W5-10,
    same as step0). The upper value uses the per-call search cap: documented
    (anthropic max_uses) or assumed 1 when the provider documents none.
    """
    upper_searches, basis = planned_searches(max_searches_per_call)
    tin = assumptions["input_tokens_per_call"]
    tout = assumptions["output_tokens_per_call"]
    searches = assumptions["searches_per_call"]
    total = _total(rows, tin, tout, 0, searches)
    upper = _total(rows, tin, tout, 0, max(searches, upper_searches))
    if total is None or upper is None:
        raise CostError("price snapshot lacks a unit needed for the estimate")
    return total, {"label": "Estimated", "input_tokens": tin, "output_tokens": tout,
                   "searches": searches, "upper_searches": upper_searches, "upper_basis": basis,
                   "upper_usd": dec_str(upper)}
