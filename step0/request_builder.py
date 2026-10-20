"""Build the exact HTTP requests for Step 0 slots, offline.

Request shapes come only from engines.json entries whose request_shape.status is
"verified" (checked against the provider's official docs, source_url + retrieved).
Anything else is reported and gets no request. API keys are never read; the auth
header is recorded by name only and its value is never produced.
"""

import re

from .canonical import canonical_bytes, sha256_hex

PROMPT_ID = re.compile(r"^p_[a-z0-9_]{1,40}$")
PLACEHOLDER = re.compile(r"\{[A-Z_]+\}")

STATUS_OK = "ok"
STATUS_UNVERIFIED_TERMS = "unverified_terms"
STATUS_RESTRICTED_TERMS = "restricted_terms"
STATUS_UNVERIFIED_SHAPE = "unverified_request_shape"
STATUS_DISABLED = "disabled"
STATUS_OPT_IN_NOT_SELECTED = "opt_in_not_selected"


class ConfigError(ValueError):
    pass


def load_prompts(doc):
    subs = doc["substitutions"]
    seen = set()
    out = []
    for p in doc["prompts"]:
        pid = p["prompt_id"]
        if not PROMPT_ID.match(pid):
            raise ConfigError("bad prompt_id: %s" % pid)
        if pid in seen:
            raise ConfigError("duplicate prompt_id: %s" % pid)
        seen.add(pid)
        text = p["template"]
        for key, value in subs.items():
            text = text.replace("{%s}" % key, value)
        if PLACEHOLDER.search(text):
            raise ConfigError("unfilled placeholder in %s: %s" % (pid, text))
        out.append({
            "prompt_id": pid,
            "type": p["type"],
            "lang": p["lang"],
            "text": text,
            "prompt_sha256": sha256_hex(text.encode("utf-8")),
        })
    return out


def engine_status(engine, opt_in_selected):
    terms = engine.get("terms_status")
    if terms == "verified-restricted":
        return STATUS_RESTRICTED_TERMS
    if terms != "verified-allowed":
        return STATUS_UNVERIFIED_TERMS
    shape = engine.get("request_shape") or {}
    if shape.get("status") != "verified" or shape.get("builder") not in BUILDERS:
        return STATUS_UNVERIFIED_SHAPE
    if not shape.get("source_url") or not shape.get("retrieved"):
        return STATUS_UNVERIFIED_SHAPE
    if not engine.get("enabled"):
        return STATUS_DISABLED
    if engine.get("opt_in") and engine["engine"] not in opt_in_selected:
        return STATUS_OPT_IN_NOT_SELECTED
    return STATUS_OK


def _openai_responses_v1(engine, text):
    # developers.openai.com/api/docs/guides/tools-web-search, curl example
    return {
        "model": engine["model"],
        "tools": [{"type": "web_search"}],
        "input": text,
    }


def _anthropic_messages_v1(engine, text):
    # platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool, curl example with max_uses
    shape = engine["request_shape"]
    tool = {"type": shape["tool_version"], "name": "web_search"}
    if shape.get("max_searches_per_call") is not None:
        tool["max_uses"] = shape["max_searches_per_call"]
    return {
        "model": engine["model"],
        "max_tokens": shape["max_tokens"],
        "messages": [{"role": "user", "content": text}],
        "tools": [tool],
    }


def _perplexity_agent_v1(engine, text):
    # docs.perplexity.ai/docs/agent-api/tools/web-search.md; search_type "web" and
    # max_output_tokens from getting-started/pricing.md and agent-api/models.md
    shape = engine["request_shape"]
    return {
        "model": engine["model"],
        "input": text,
        "tools": [{"type": "web_search", "search_type": shape["search_type"]}],
        "max_output_tokens": shape["max_output_tokens"],
    }


BUILDERS = {
    "openai_responses_v1": _openai_responses_v1,
    "anthropic_messages_v1": _anthropic_messages_v1,
    "perplexity_agent_v1": _perplexity_agent_v1,
}


def build_request(engine, prompt):
    shape = engine["request_shape"]
    auth = shape["auth_header"].lower()
    headers = dict(shape.get("headers", {}))
    if any(name.lower() == auth for name in headers):
        raise ConfigError("%s: auth header must not appear in headers" % engine["engine"])
    body = BUILDERS[shape["builder"]](engine, prompt["text"])
    return {
        "method": shape["method"],
        "url": shape["endpoint"],
        "headers": headers,
        "auth_header": shape["auth_header"],
        "body": body,
    }


def build_plan(engines_doc, prompts, repeats, opt_in_selected=()):
    """Return (plan, request_files). request_files maps sha256 -> canonical body bytes."""
    if not isinstance(repeats, int) or repeats < 1:
        raise ConfigError("repeats must be a positive int")
    opt_in_selected = set(opt_in_selected)
    known = {e["engine"] for e in engines_doc["engines"]}
    unknown = opt_in_selected - known
    if unknown:
        raise ConfigError("unknown opt-in engine: %s" % ", ".join(sorted(unknown)))

    engines = []
    slots = []
    request_files = {}
    for engine in sorted(engines_doc["engines"], key=lambda e: e["engine"]):
        status = engine_status(engine, opt_in_selected)
        shape = engine.get("request_shape") or {}
        engines.append({
            "engine": engine["engine"],
            "status": status,
            "model": engine.get("model"),
            "terms_status": engine.get("terms_status"),
            "request_shape_source": shape.get("source_url"),
            "request_shape_retrieved": shape.get("retrieved"),
        })
        if status != STATUS_OK:
            continue
        for prompt in prompts:
            req = build_request(engine, prompt)
            body = canonical_bytes(req["body"])
            digest = sha256_hex(body)
            request_files[digest] = body
            for repeat_index in range(repeats):
                slots.append({
                    "engine": engine["engine"],
                    "model": engine["model"],
                    "tool_version": shape["tool_version"],
                    "prompt_id": prompt["prompt_id"],
                    "prompt_sha256": prompt["prompt_sha256"],
                    "repeat_index": repeat_index,
                    "method": req["method"],
                    "url": req["url"],
                    "headers": req["headers"],
                    "auth_header": req["auth_header"],
                    "request_sha256": digest,
                })
    plan = {"engines": engines, "repeats": repeats, "slots": slots}
    return plan, request_files
