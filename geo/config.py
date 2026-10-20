"""Engine snapshots, prompt and source inputs for a run manifest (W4 3.2, 3.3)."""

import unicodedata

from . import cost, terms
from .canonical import canonical_bytes, sha256_hex

SNAPSHOT_FIELDS = ("engine", "model", "model_vendor", "tool_version", "terms_status", "terms_url",
                   "terms_last_updated", "terms_retrieved", "opt_in", "price_snapshot")


class ConfigError(ValueError):
    pass


def with_config_sha(snapshot):
    snap = {k: v for k, v in snapshot.items() if k != "config_sha256"}
    snap["config_sha256"] = sha256_hex(canonical_bytes(snap))
    return snap


def engine_snapshot(engine, prices_doc):
    """Return (snapshot, sources) for an engines.json entry, or raise ConfigError."""
    shape = engine.get("request_shape") or {}
    if not engine.get("model") or not shape.get("tool_version"):
        raise ConfigError("%s has no model or tool_version" % engine.get("engine"))
    key = engine.get("price_key")
    entry = (prices_doc.get("prices") or {}).get(key) if key else None
    if entry is None:
        raise ConfigError("%s has no price entry" % engine["engine"])
    rows, sources = cost.price_snapshot(key, entry)
    snap = {
        "engine": engine["engine"],
        "model": engine["model"],
        "model_vendor": engine["model_vendor"],
        "tool_version": shape["tool_version"],
        "terms_status": engine.get("terms_status"),
        "terms_url": engine.get("terms_url"),
        "terms_last_updated": engine.get("terms_last_updated"),
        "terms_retrieved": engine.get("terms_retrieved"),
        "opt_in": bool(engine.get("opt_in")),
        "price_snapshot": rows,
    }
    return with_config_sha(snap), sources


def split_engines(engines_doc, prices_doc, opt_in_selected):
    """Apply the terms gate to configured engines.

    Returns (snapshots, excluded, sources). An engine is excluded (and never
    snapshotted for capture) when its terms are not verified-allowed, its opt-in
    is not selected, it is disabled, or its request shape is unverified.
    """
    snapshots, excluded, sources = [], [], {}
    for engine in sorted(engines_doc["engines"], key=lambda e: e["engine"]):
        status = engine.get("terms_status")
        probe = {"engine": engine["engine"], "terms_status": status, "opt_in": bool(engine.get("opt_in"))}
        allowed, reason = terms.gate(probe, opt_in_selected)
        shape = engine.get("request_shape") or {}
        if allowed and not engine.get("enabled"):
            allowed, reason = False, "disabled"
        if allowed and shape.get("status") != "verified":
            allowed, reason = False, "request_shape_unverified"
        if not allowed:
            excluded.append({"engine": engine["engine"], "terms_status": status, "reason": reason})
            continue
        snap, srcs = engine_snapshot(engine, prices_doc)
        snapshots.append(snap)
        for s in srcs:
            sources[s["src_ref"]] = s
    return snapshots, excluded, [sources[k] for k in sorted(sources)]


def prompt_inputs(prompts):
    """prompts: [{prompt_id, text}] -> canonical inputs/prompts.json document."""
    out = []
    for p in prompts:
        text = unicodedata.normalize("NFC", p["text"])
        out.append({"prompt_id": p["prompt_id"], "text": text,
                    "prompt_sha256": sha256_hex(text.encode("utf-8"))})
    return {"prompts": out}
