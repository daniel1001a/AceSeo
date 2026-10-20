"""Provider adapters (PLAN Step 3; W4 3.3, U1, Q5).

An adapter builds the request body (step0.request_builder, verified shapes only)
and maps an HTTP status plus exact response bytes to a capture outcome. It never
sends anything; the transport does that (geo.collect).

Field provenance, recorded per adapter in FIELD_STATUS:
  documented  seen in the provider doc read on 2026-10-19 (scratchpad copies)
  live        also seen in a real response of run_20261020T142935Z_74e3cd
              (2026-10-20; replayed by tests/test_live_fixtures.py)
  unverified  general knowledge, not in a doc read in this project, and not yet
              seen in a recorded real response
The first live run returned 10 ok anthropic responses and 20 openai HTTP 429
insufficient_quota bodies; no ok openai or perplexity response has been
recorded, so those mappings are still tested on SYNTHETIC bodies shaped like the
documented examples. Perplexity's response
mapping was read from docs.perplexity.ai on 2026-10-20 (agent-api quickstart,
tools/web-search, migrate-from-sonar/how-to).
"""

import json
import re
from collections import namedtuple

from step0 import request_builder

Outcome = namedtuple("Outcome", "status error_class answer_text citations usage search_observed")


def _failed(error_class):
    return Outcome("failed", error_class, "", [], None, None)


def _http_failure(http_status):
    if http_status == 429:
        return _failed("rate_limited")
    return _failed("http_error")


def _load(body):
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _error_type(body):
    doc = _load(body)
    err = doc.get("error") if doc else None
    return err.get("type") if isinstance(err, dict) else None


def _nonneg_int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def _citation(url, title, cited_text, position, provider_field):
    return {"url": url, "title": title if isinstance(title, str) else None,
            "cited_text": cited_text if isinstance(cited_text, str) else None,
            "position": position, "provider_field": provider_field}


def _http_url(u):
    return isinstance(u, str) and (u.startswith("https://") or u.startswith("http://"))


class Adapter:
    engine = None
    builder = None
    FIELD_STATUS = {}

    def build(self, engine_entry, prompt):
        """-> step0 request dict {method, url, headers, auth_header, body}."""
        if (engine_entry.get("request_shape") or {}).get("builder") != self.builder:
            raise request_builder.ConfigError("%s: request_shape.builder is not %s" % (self.engine, self.builder))
        return request_builder.build_request(engine_entry, prompt)

    def auth_value(self, api_key):
        raise NotImplementedError

    def parse(self, http_status, body):
        raise NotImplementedError


class OpenAIAdapter(Adapter):
    """Responses API with the web_search tool."""

    engine = "openai"
    builder = "openai_responses_v1"
    FIELD_STATUS = {
        "output[].type web_search_call, action.type search": "documented",
        "output[].type message, content[].type output_text, text": "documented",
        "content[].annotations[].type url_citation, url, title, start_index, end_index": "documented",
        "auth Authorization: Bearer": "documented",
        "HTTP 429 error.type insufficient_quota": "live",
        "usage.input_tokens, usage.output_tokens": "unverified",
        "usage.input_tokens_details.cached_tokens": "unverified",
        "content[].type refusal, refusal": "unverified",
        "top-level status incomplete": "unverified",
    }

    def auth_value(self, api_key):
        return "Bearer " + api_key

    def parse(self, http_status, body):
        if http_status == 429 and _error_type(body) == "insufficient_quota":
            return _failed("quota_exhausted")
        if not 200 <= http_status < 300:
            return _http_failure(http_status)
        doc = _load(body)
        if doc is None or not isinstance(doc.get("output"), list):
            return _failed("parse_error")
        texts, refusals, citations, searches = [], [], [], 0
        for i, item in enumerate(doc["output"]):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "web_search_call":
                action = item.get("action")
                if isinstance(action, dict) and action.get("type") == "search":
                    searches += 1
            elif item.get("type") == "message" and isinstance(item.get("content"), list):
                for j, part in enumerate(item["content"]):
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                        for k, a in enumerate(part.get("annotations") or []):
                            if isinstance(a, dict) and a.get("type") == "url_citation" and _http_url(a.get("url")):
                                citations.append(_citation(
                                    a["url"], a.get("title"), None, len(citations),
                                    "output[%d].content[%d].annotations[%d]" % (i, j, k)))
                    elif part.get("type") == "refusal" and isinstance(part.get("refusal"), str):
                        refusals.append(part["refusal"])
        usage = self._usage(doc.get("usage"), searches)
        text = "".join(texts)
        if refusals and not text:
            return Outcome("refused", None, "".join(refusals), [], usage, searches)
        if doc.get("status") not in (None, "completed"):
            return Outcome("failed", "incomplete", text, citations, usage, searches)
        if not text.strip():
            return Outcome("failed", "empty_answer", "", [], usage, searches)
        return Outcome("ok", None, text, citations, usage, searches)

    @staticmethod
    def _usage(u, searches):
        if not isinstance(u, dict):
            return None
        tin, tout = _nonneg_int(u.get("input_tokens")), _nonneg_int(u.get("output_tokens"))
        if tin is None or tout is None:
            return None
        # cached_input_tokens stays null: whether input_tokens already includes
        # cached tokens is unverified, so cost_from_usage is not computed.
        return {"input_tokens": tin, "output_tokens": tout, "cached_input_tokens": None,
                "search_calls": searches}


class AnthropicAdapter(Adapter):
    """Messages API with the web_search server tool (max_uses from engines.json)."""

    engine = "anthropic"
    builder = "anthropic_messages_v1"
    FIELD_STATUS = {
        "content[].type text, text, citations[].type web_search_result_location": "live",
        "citations[].url, title, cited_text": "live",
        "content[].type thinking (ignored)": "live",
        "content[].type web_search_tool_result_error, error_code (HTTP 200)": "documented",
        "usage.input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens": "live",
        "usage.server_tool_use.web_search_requests": "live",
        "stop_reason end_turn": "live",
        "stop_reason pause_turn": "documented",
        "auth x-api-key": "live",
        "stop_reason refusal": "unverified",
    }

    def auth_value(self, api_key):
        return api_key

    def parse(self, http_status, body):
        if not 200 <= http_status < 300:
            return _http_failure(http_status)
        doc = _load(body)
        if doc is None or not isinstance(doc.get("content"), list):
            return _failed("parse_error")
        texts, citations, tool_errors = [], [], []
        for i, block in enumerate(doc["content"]):
            if isinstance(block, dict) and block.get("type") == "web_search_tool_result":
                err = block.get("content")
                if isinstance(err, dict) and err.get("type") == "web_search_tool_result_error":
                    tool_errors.append(err.get("error_code"))
            if not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str):
                continue
            texts.append(block["text"])
            for k, c in enumerate(block.get("citations") or []):
                if isinstance(c, dict) and c.get("type") == "web_search_result_location" and _http_url(c.get("url")):
                    citations.append(_citation(c["url"], c.get("title"), c.get("cited_text"), len(citations),
                                               "content[%d].citations[%d]" % (i, k)))
        u = doc.get("usage") if isinstance(doc.get("usage"), dict) else {}
        stu = u.get("server_tool_use") if isinstance(u.get("server_tool_use"), dict) else {}
        searches = _nonneg_int(stu.get("web_search_requests"))
        if searches is None and not stu:
            searches = 0 if "usage" in doc else None
        usage = self._usage(u, searches)
        text = "".join(texts)
        stop = doc.get("stop_reason")
        if stop == "refusal":
            return Outcome("refused", None, text, [], usage, searches)
        if stop == "pause_turn":  # the server loop paused; this tool does not continue turns
            return Outcome("failed", "incomplete", text, citations, usage, searches)
        # A tool error arrives in a 200 (documented). max_uses_exceeded only means
        # the planned cap was reached, so the answer stands. too_many_requests is
        # a rate limit. Any other code means the search did not run as planned.
        errs = [e for e in tool_errors if e != "max_uses_exceeded"]
        if "too_many_requests" in errs:
            return Outcome("failed", "rate_limited", text, citations, usage, searches)
        if errs:
            return Outcome("failed", "tool_error", text, citations, usage, searches)
        if not text.strip():
            return Outcome("failed", "empty_answer", "", [], usage, searches)
        return Outcome("ok", None, text, citations, usage, searches)

    @staticmethod
    def _usage(u, searches):
        tin, tout = _nonneg_int(u.get("input_tokens")), _nonneg_int(u.get("output_tokens"))
        cached = _nonneg_int(u.get("cache_read_input_tokens", 0))
        creation = _nonneg_int(u.get("cache_creation_input_tokens", 0))
        if tin is None or tout is None or cached is None or searches is None or creation != 0:
            return None  # incomplete, or cache writes we have no price row for
        return {"input_tokens": tin, "output_tokens": tout, "cached_input_tokens": cached,
                "search_calls": searches}


class PerplexityAdapter(Adapter):
    """Agent API (POST /v1/agent) with the web_search tool.

    The answer is the output_text of message items (same as OpenAI Responses).
    Sources arrive in separate output items of type search_results; the answer
    cites them with inline [n] markers, where n is a result's id. A result
    counts as a citation only when the answer carries its marker, so a result
    that was retrieved but never cited is not a citation (matching the other
    adapters, which report only sources attached to the answer). Whether
    markers appear depends on the prompt, so the request asks for them
    (step0.request_builder, the documented instruction).
    """

    engine = "perplexity"
    builder = "perplexity_agent_v1"
    FIELD_STATUS = {
        "auth Authorization: Bearer": "documented",
        "output[].type message, content[].type output_text, text": "documented",
        "output[].type search_results, results[].id, url, title": "documented",
        "answer text [n] markers map to results[].id": "documented",
        "usage.input_tokens, usage.output_tokens": "documented",
        "usage.input_tokens_details.cached_tokens": "documented",
        "usage.tool_calls_details.search_web.invocation": "documented",
        "top-level status completed": "documented",
        "top-level status other than completed": "unverified",
        "refusal content part": "unverified",
    }
    MARKER = re.compile(r"\[(\d+)\]")

    def auth_value(self, api_key):
        return "Bearer " + api_key

    def parse(self, http_status, body):
        if not 200 <= http_status < 300:
            return _http_failure(http_status)
        doc = _load(body)
        if doc is None or not isinstance(doc.get("output"), list):
            return _failed("parse_error")
        texts, results = [], {}
        for i, item in enumerate(doc["output"]):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "search_results" and isinstance(item.get("results"), list):
                for k, r in enumerate(item["results"]):
                    rid = _nonneg_int(r.get("id")) if isinstance(r, dict) else None
                    if rid is not None and rid not in results and _http_url(r.get("url")):
                        results[rid] = (r, "output[%d].results[%d]" % (i, k))
            elif item.get("type") == "message" and isinstance(item.get("content"), list):
                for part in item["content"]:
                    if isinstance(part, dict) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
        text = "".join(texts)
        citations, seen = [], set()
        for m in self.MARKER.finditer(text):
            rid = int(m.group(1))
            if rid in results and rid not in seen:
                seen.add(rid)
                r, field = results[rid]
                citations.append(_citation(r["url"], r.get("title"), None, len(citations), field))
        u = doc.get("usage") if isinstance(doc.get("usage"), dict) else None
        searches = self._searches(u)
        usage = self._usage(u, searches)
        if doc.get("status") not in (None, "completed"):
            return Outcome("failed", "incomplete", text, citations, usage, searches)
        if not text.strip():
            return Outcome("failed", "empty_answer", "", [], usage, searches)
        return Outcome("ok", None, text, citations, usage, searches)

    @staticmethod
    def _searches(u):
        if u is None:
            return None
        details = u.get("tool_calls_details")
        if not isinstance(details, dict):
            return 0  # documented: tool-call usage appears only when a tool ran
        sw = details.get("search_web")
        return 0 if sw is None else (_nonneg_int(sw.get("invocation")) if isinstance(sw, dict) else None)

    @staticmethod
    def _usage(u, searches):
        if u is None:
            return None
        tin, tout = _nonneg_int(u.get("input_tokens")), _nonneg_int(u.get("output_tokens"))
        det = u.get("input_tokens_details") if isinstance(u.get("input_tokens_details"), dict) else {}
        cached = _nonneg_int(det.get("cached_tokens", 0))
        if tin is None or tout is None or cached is None or searches is None:
            return None
        # A nonzero cached count has no price row (prices.json), so cost_from_usage
        # stays null for that capture instead of guessing a cache price.
        return {"input_tokens": tin, "output_tokens": tout, "cached_input_tokens": cached,
                "search_calls": searches}


ADAPTERS = {a.engine: a for a in (OpenAIAdapter(), AnthropicAdapter(), PerplexityAdapter())}
IMPLEMENTED = ("anthropic", "openai", "perplexity")
