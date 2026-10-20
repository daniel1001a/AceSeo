"""Builders for the run manifest and capture records (W4 3.1 to 3.3).

Builders compute every derived field (id, identity_sha256, series_key,
cost_from_usage_usd) so callers cannot hand-type them.
"""

from . import SCHEMA_VERSION, TOOL_BUILD, cost, ids
from .canonical import canonical_bytes, sha256_hex

CAPTURE_STATUSES = ("ok", "failed", "refused")
# Extensions of W4 3.3 (Step 3):
#   incomplete  a 200 that stopped before a final answer (anthropic stop_reason
#               pause_turn; openai status other than completed, unverified). The
#               partial text is kept but never counted as ok.
#   tool_error  a 200 whose web search tool reported an error in the body
#               (anthropic web_search_tool_result_error, documented).
ERROR_CLASSES = ("timeout", "connection", "http_error", "rate_limited", "parse_error", "empty_answer",
                 "incomplete", "tool_error")
NULL_RAW_ERROR_CLASSES = ("timeout", "connection")
SKIP_REASONS = ("budget_cap", "user_abort", "terms_gate")
TRANSPORTS = ("live", "fixture")


def plan_sha256(engines, prompts_sha256, repeats, key_pages, thresholds):
    return sha256_hex(canonical_bytes({"engines": engines, "prompts_sha256": prompts_sha256,
                                       "repeats": repeats, "key_pages": key_pages,
                                       "thresholds": thresholds}))


def new_manifest(*, started_at, engines, engines_excluded, opt_in_selected, input_hashes, repeats,
                 max_attempts, key_pages, key_content, mention_terms, thresholds, planned_slots,
                 cap_usd, transport, run_kind="collect", source_run_ids=()):
    """input_hashes: {"prompts_sha256", "facts_sha256", "sources_sha256"}."""
    if transport not in TRANSPORTS:
        raise ValueError("transport must be live or fixture")
    key_pages = sorted(ids.url_norm_v1(u) for u in key_pages)
    run_id = ids.make_run_id(
        plan_sha256(engines, input_hashes["prompts_sha256"], repeats, key_pages, thresholds), started_at)
    return {
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "tool_build": TOOL_BUILD,
        "run_kind": run_kind,
        "source_run_ids": list(source_run_ids),
        "started_at": started_at,
        "sealed_at": None,
        "engines": engines,
        "engines_excluded": engines_excluded,
        "opt_in_selected": sorted(opt_in_selected),
        "prompts_sha256": input_hashes["prompts_sha256"],
        "facts_sha256": input_hashes["facts_sha256"],
        "sources_sha256": input_hashes["sources_sha256"],
        "repeats": repeats,
        "max_attempts": max_attempts,
        "key_pages": key_pages,
        "key_content": key_content,
        "mention_terms": list(mention_terms),
        "thresholds": thresholds,
        "planned_slots": planned_slots,
        "skipped_slots": [],
        "budget": {"cap_usd": cap_usd, "spent_estimate_usd": "0"},
        "transport": transport,
    }


def _finish(record, slug):
    identity = ids.record_identity(record)
    record["identity_sha256"] = ids.identity_sha256(identity)
    record["id"] = ids.make_id(identity, slug)
    if record["kind"] in ("capture", "page_check"):
        record["series_key"] = ids.series_key(identity)
    return record


def capture(manifest, snapshot, prompt, repeat_index, attempt, *, started_at, completed_at, status,
            request_sha256, raw_sha256, raw_path, answer_text, citations, cost_estimate_usd,
            error_class=None, http_status=None, usage=None, search_observed=None, created_at=None):
    """prompt: {prompt_id, text, prompt_sha256} from inputs/prompts.json."""
    rec = {
        "kind": "capture",
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "created_at": created_at or completed_at,
        "tool_build": manifest["tool_build"],
        "engine": snapshot["engine"],
        "engine_snapshot": snapshot,
        "prompt_id": prompt["prompt_id"],
        "prompt_text": prompt["text"],
        "prompt_sha256": prompt["prompt_sha256"],
        "repeat_index": repeat_index,
        "attempt": attempt,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
        "error_class": error_class,
        "http_status": http_status,
        "request_sha256": request_sha256,
        "raw_sha256": raw_sha256,
        "raw_path": raw_path,
        "answer_text": answer_text,
        "citations": citations,
        "usage": usage,
        "cost_estimate_usd": cost_estimate_usd,
        "cost_from_usage_usd": None,
        "cost_billed_usd": None,
        "cost_billed_field": None,
        "search_observed": search_observed,
    }
    if usage is not None:
        d = cost.cost_from_usage(snapshot["price_snapshot"], usage)
        rec["cost_from_usage_usd"] = None if d is None else cost.dec_str(d)
    return _finish(rec, snapshot["engine"])


def page_check(manifest, *, check_name, check_version, url_norm, agent_profile, params, fetched_at,
               final_url, http_status, redirect_chain, response_headers, raw_sha256, raw_path,
               derived_from_raw, result, not_checkable_reason, blocking_on_fail, detail, created_at=None):
    rec = {
        "kind": "page_check",
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "created_at": created_at or fetched_at,
        "tool_build": manifest["tool_build"],
        "check_name": check_name,
        "check_version": check_version,
        "url_norm": url_norm,
        "url_role": "key" if url_norm in manifest["key_pages"] else "other",
        "agent_profile": agent_profile,
        "params": params,
        "fetched_at": fetched_at,
        "final_url": final_url,
        "http_status": http_status,
        "redirect_chain": redirect_chain,
        "response_headers": response_headers,
        "raw_sha256": raw_sha256,
        "raw_path": raw_path,
        "derived_from_raw": derived_from_raw,
        "result": result,
        "not_checkable_reason": not_checkable_reason,
        "blocking_on_fail": blocking_on_fail,
        "detail": detail,
    }
    return _finish(rec, check_name)
