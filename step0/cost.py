"""Offline cost estimate for Step 0 slots, in Decimal, against a sourced price table.

Prices are Published (each entry must cite a source URL and retrieved date) and
token counts are Estimated (synthetic until Step 0 measures them, PLAN A8). The
estimator refuses to produce totals if any price it needs lacks a source.
"""

from decimal import Decimal

MTOK = Decimal(1000000)


class PriceSourceError(ValueError):
    pass


def dec_str(d):
    s = format(d.normalize(), "f")
    return "0" if s in ("-0", "") else s


def _require_sources(key, entry):
    sources = entry.get("sources") or []
    if not sources:
        raise PriceSourceError("price %s has no source" % key)
    for s in sources:
        if not s.get("url") or not s.get("retrieved"):
            raise PriceSourceError("price %s has a source without url or retrieved date" % key)


def _token_rates(entry, input_tokens):
    rate_in = Decimal(entry["input_per_mtok"])
    rate_out = Decimal(entry["output_per_mtok"])
    for tier in sorted(entry.get("input_tiers", []), key=lambda t: t["min_prompt_tokens"]):
        if input_tokens >= tier["min_prompt_tokens"]:
            rate_in = Decimal(tier["input_per_mtok"])
            rate_out = Decimal(tier["output_per_mtok"])
    return rate_in, rate_out


def per_call(entry, assumptions):
    tin = assumptions["input_tokens_per_call"]
    tout = assumptions["output_tokens_per_call"]
    searches = assumptions["searches_per_call"]
    rate_in, rate_out = _token_rates(entry, tin)
    tokens = Decimal(tin) * rate_in / MTOK + Decimal(tout) * rate_out / MTOK
    search = Decimal(searches) * Decimal(entry["search_per_call"])
    return tokens, search


def estimate(slots, engines_doc, prices_doc, cap_usd):
    """slots: list of slot dicts with an "engine" key. Returns a dict of decimal strings."""
    cap = Decimal(cap_usd)
    assumptions = prices_doc["token_assumptions"]
    by_engine = {e["engine"]: e for e in engines_doc["engines"]}
    counts = {}
    for slot in slots:
        counts[slot["engine"]] = counts.get(slot["engine"], 0) + 1

    # Check every needed price before computing anything.
    for name in counts:
        key = by_engine[name].get("price_key")
        entry = prices_doc["prices"].get(key) if key else None
        if entry is None:
            raise PriceSourceError("engine %s has no price entry" % name)
        _require_sources(key, entry)

    rows = []
    total = Decimal(0)
    search_total = Decimal(0)
    unbounded = []
    worst_search = Decimal(0)
    for name in sorted(counts):
        n = counts[name]
        engine = by_engine[name]
        key = engine["price_key"]
        entry = prices_doc["prices"][key]
        tokens, search = per_call(entry, assumptions)
        max_searches = engine["request_shape"].get("max_searches_per_call")
        if max_searches is None:
            unbounded.append(name)
            worst = None
        else:
            worst = Decimal(n) * Decimal(max_searches) * Decimal(entry["search_per_call"])
            worst_search += worst
        engine_total = Decimal(n) * (tokens + search)
        total += engine_total
        search_total += Decimal(n) * search
        rows.append({
            "engine": name,
            "n_slots": n,
            "price_key": key,
            "price_label": entry["label"],
            "price_sources": [s["url"] for s in entry["sources"]],
            "per_call_tokens_usd": dec_str(tokens),
            "per_call_search_usd": dec_str(search),
            "per_call_total_usd": dec_str(tokens + search),
            "search_fee_usd": dec_str(Decimal(n) * search),
            "total_usd": dec_str(engine_total),
            "search_fee_upper_usd": None if worst is None else dec_str(worst),
            "max_searches_per_call": max_searches,
        })

    status = "over_budget" if total > cap else "within_cap_estimated"
    return {
        "status": status,
        "cap_usd": dec_str(cap),
        "total_usd": dec_str(total),
        "search_fee_total_usd": dec_str(search_total),
        "search_fee_upper_total_usd": None if unbounded else dec_str(worst_search),
        "search_fee_unbounded_engines": unbounded,
        "token_assumptions": assumptions,
        "engines": rows,
    }
