"""Capture collection (PLAN Step 3; W4 2.1, 3.3; W5 T3).

Dry run is the default: collect() plans every slot, prices it (Estimated) and
returns the plan. It writes nothing and never touches a transport. Sending
requires send=True, an injected transport and an API key per engine. Live
network access exists only in UrllibTransport, which only geo.cli --live builds.

Everything that can refuse a run is checked before the run directory exists:
  - send without the flag, or without a transport or key
  - an engine whose adapter is not implemented (perplexity: interface only)
  - planned first attempts priced above the budget cap
At send time each slot passes the terms gate again on its frozen snapshot. A
slot that fails it is logged in skipped_slots (reason terms_gate); nothing is
written for it and the transport is not called.

The API key is used only to build the auth header in memory. It is passed to
RunWriter as a secret, so any file containing it is refused. Only the request
body is stored (raw/<sha>.json); headers are never stored.
"""

import datetime
import json
import socket
import time
import urllib.error
import urllib.request
from collections import namedtuple
from decimal import Decimal

from . import config, cost, number, records, terms
from .adapters import ADAPTERS, IMPLEMENTED, Outcome
from .canonical import canonical_bytes, sha256_hex
from .store import RunWriter, input_hashes

# Failed attempts worth another try. refused and ok are final; parse_error,
# empty_answer and incomplete are retried too, since a repeat is a new sample.
RETRY_BACKOFF_S = 2


class CollectError(ValueError):
    pass


class TermsGateError(CollectError):
    """Raised by the send guard; the collector logs the slot as terms_gate."""


class TransportError(Exception):
    def __init__(self, error_class):
        if error_class not in records.NULL_RAW_ERROR_CLASSES:
            raise ValueError("transport errors are timeout or connection")
        Exception.__init__(self, error_class)
        self.error_class = error_class


Slot = namedtuple("Slot", "engine prompt repeat_index request body request_sha256 estimate")
Plan = namedtuple("Plan", "snapshots excluded sources prompts_doc slots terms_skips estimates total_usd upper_usd")

TERMS_REASONS = (terms.REASON_RESTRICTED, terms.REASON_UNVERIFIED, terms.REASON_OPT_IN)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _entry(engines_doc, name):
    return next(e for e in engines_doc["engines"] if e["engine"] == name)


def build_plan(engines_doc, prices_doc, prompts, repeats, opt_in_selected=()):
    """prompts: [{prompt_id, text}]. Raises CollectError for an unimplemented adapter."""
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise CollectError("repeats must be a positive int")
    snaps, excluded, sources = config.split_engines(engines_doc, prices_doc, opt_in_selected)
    for s in snaps:
        if s["engine"] not in IMPLEMENTED:
            raise CollectError("%s: adapter is not implemented (interface only); deselect it" % s["engine"])
    prompts_doc = config.prompt_inputs(prompts)
    slots, estimates = [], {}
    total = upper = Decimal(0)
    for snap in snaps:
        entry = _entry(engines_doc, snap["engine"])
        d, detail = cost.cost_estimate(snap["price_snapshot"], entry["request_shape"].get("max_searches_per_call"),
                                       prices_doc["token_assumptions"])
        estimates[snap["engine"]] = dict(detail, expected_usd=cost.dec_str(d))
        adapter = ADAPTERS[snap["engine"]]
        for p in prompts_doc["prompts"]:
            req = adapter.build(entry, p)
            body = canonical_bytes(req["body"])
            for r in range(repeats):
                slots.append(Slot(snap["engine"], p, r, req, body, sha256_hex(body), d))
                total += d
                upper += Decimal(detail["upper_usd"])
    # W5-02 A and C: slots of an engine excluded by the terms gate are logged as
    # skipped (terms_gate) and never built or sent. Engines excluded for other
    # reasons (disabled, unverified request shape) have no slots.
    terms_skips = [{"engine": e["engine"], "prompt_id": p["prompt_id"], "repeat_index": r, "reason": terms.SKIP_REASON}
                   for e in excluded if e["reason"] in TERMS_REASONS
                   for p in prompts_doc["prompts"] for r in range(repeats)]
    return Plan(snaps, excluded, sources, prompts_doc, slots, terms_skips, estimates, total, upper)


def plan_summary(plan, cap_usd, max_attempts):
    """The dry-run report. Every cost here is Estimated."""
    return {
        "mode": "dry_run",
        "writes": "none",
        "planned_slots": len(plan.slots) + len(plan.terms_skips),
        "sendable_slots": len(plan.slots),
        "skipped_slots": plan.terms_skips,
        "max_attempts": max_attempts,
        "engines": [s["engine"] for s in plan.snapshots],
        "engines_excluded": plan.excluded,
        "estimate": {"label": "Estimated", "first_attempts_usd": cost.dec_str(plan.total_usd),
                     "upper_first_attempts_usd": cost.dec_str(plan.upper_usd),
                     "per_call": plan.estimates, "cap_usd": cap_usd,
                     "within_cap": plan.total_usd <= Decimal(cap_usd)},
        "requests": [{"engine": s.engine, "prompt_id": s.prompt["prompt_id"], "repeat_index": s.repeat_index,
                      "method": s.request["method"], "url": s.request["url"],
                      "auth_header": s.request["auth_header"], "request_sha256": s.request_sha256}
                     for s in plan.slots],
    }


def guard(snapshot, opt_in_selected):
    """Terms gate at send time (W5 T3). Raises before anything is written or sent."""
    allowed, reason = terms.gate(snapshot, opt_in_selected)
    if not allowed:
        raise TermsGateError("%s: %s" % (snapshot["engine"], reason))


def collect(engines_doc, prices_doc, prompts, facts_bytes, *, root, repeats, cap_usd, key_pages,
            mention_terms, key_content=(), thresholds=None, opt_in_selected=(), max_attempts=2,
            send=False, transport=None, api_keys=None, clock=utc_now, sleep=time.sleep, on_start=None,
            progress=None):
    """Dry run (default) -> plan summary dict. send=True -> run directory path.

    on_start(writer), if given, runs after the run directory exists and before
    the first slot is sent (the pipeline runs page checks there). progress(event),
    if given, gets one dict per capture attempt and per skipped slot."""
    if not cost.is_dec(cap_usd):
        raise CollectError("cap_usd must be a dec string")
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise CollectError("max_attempts must be a positive int")
    plan = build_plan(engines_doc, prices_doc, prompts, repeats, opt_in_selected)
    if not send:
        if transport is not None or api_keys:
            raise CollectError("a transport or API keys were given without send=True")
        return plan_summary(plan, cap_usd, max_attempts)

    if transport is None or getattr(transport, "kind", None) not in records.TRANSPORTS:
        raise CollectError("send=True needs a transport with kind live or fixture")
    keys = api_keys or {}
    missing = [s["engine"] for s in plan.snapshots if not keys.get(s["engine"])]
    if missing:
        raise CollectError("no API key for %s" % ", ".join(missing))
    if plan.total_usd > Decimal(cap_usd):
        raise CollectError("Estimated first attempts %s exceed the cap %s; nothing sent"
                           % (cost.dec_str(plan.total_usd), cap_usd))
    if not plan.slots and not plan.terms_skips:
        raise CollectError("no slots planned")

    writer = start_run(plan, facts_bytes, root=root, repeats=repeats, cap_usd=cap_usd, key_pages=key_pages,
                       mention_terms=mention_terms, key_content=key_content, thresholds=thresholds,
                       opt_in_selected=opt_in_selected, max_attempts=max_attempts, transport=transport,
                       secrets=[keys[s["engine"]] for s in plan.snapshots], clock=clock)
    if on_start is not None:
        on_start(writer)
    Collector(writer, plan, transport, keys, opt_in_selected, clock, sleep, progress).run()
    return writer.run_dir


def start_run(plan, facts_bytes, *, root, repeats, cap_usd, key_pages, mention_terms, key_content, thresholds,
              opt_in_selected, max_attempts, transport, secrets, clock):
    """Create the run directory and manifest for a checked plan. Returns the RunWriter."""
    inputs = {"prompts": canonical_bytes(plan.prompts_doc), "facts": facts_bytes,
              "sources": canonical_bytes({"sources": plan.sources})}
    manifest = records.new_manifest(
        started_at=clock(), engines=plan.snapshots, engines_excluded=plan.excluded,
        opt_in_selected=opt_in_selected, input_hashes=input_hashes(inputs), repeats=repeats,
        max_attempts=max_attempts, key_pages=key_pages, key_content=list(key_content),
        mention_terms=mention_terms, thresholds=thresholds or number.threshold_values(),
        planned_slots=len(plan.slots) + len(plan.terms_skips), cap_usd=cap_usd, transport=transport.kind)
    manifest["skipped_slots"] = [dict(s) for s in plan.terms_skips]
    return RunWriter(root, manifest, inputs, secrets=secrets)


class Collector:
    def __init__(self, writer, plan, transport, api_keys, opt_in_selected, clock, sleep, progress=None):
        self.writer, self.plan, self.transport = writer, plan, transport
        self.progress = progress
        self.keys, self.opt_in, self.clock, self.sleep = api_keys, opt_in_selected, clock, sleep
        self.manifest = writer.manifest
        self.snaps = {s["engine"]: s for s in plan.snapshots}
        self.cap = Decimal(self.manifest["budget"]["cap_usd"])
        self.spent = Decimal(0)
        self.calls = 0
        self.exhausted = set()  # engines that answered quota_exhausted

    def skip(self, slot, reason):
        entry = {"engine": slot.engine, "prompt_id": slot.prompt["prompt_id"],
                 "repeat_index": slot.repeat_index, "reason": reason}
        self.manifest["skipped_slots"].append(entry)
        self._note(dict(entry, event="skip"))

    def _note(self, event):
        if self.progress is not None:
            self.progress(event)

    def run(self):
        i, self.sent_this_slot = 0, False
        try:
            for i, slot in enumerate(self.plan.slots):
                self.run_slot(slot)
        except KeyboardInterrupt:
            rest = self.plan.slots[i + 1:] if self.sent_this_slot else self.plan.slots[i:]
            for slot in rest:
                self.skip(slot, "user_abort")
            raise
        finally:
            self.writer.write_manifest()

    def run_slot(self, slot):
        self.sent_this_slot = False
        snap = self.snaps[slot.engine]
        if slot.engine in self.exhausted:
            self.skip(slot, "quota_exhausted")
            return
        for attempt in range(1, self.manifest["max_attempts"] + 1):
            try:
                guard(snap, self.opt_in)
            except TermsGateError:
                if attempt == 1:
                    self.skip(slot, terms.SKIP_REASON)
                return
            if self.spent + slot.estimate > self.cap:
                if attempt == 1:
                    self.skip(slot, "budget_cap")
                return
            self.sent_this_slot = True
            rec = self.send(slot, snap, attempt)
            if rec["status"] != "failed":
                return
            if rec["error_class"] == "quota_exhausted":  # retrying cannot help
                self.exhausted.add(slot.engine)
                return
            if attempt < self.manifest["max_attempts"]:
                self.sleep(RETRY_BACKOFF_S * attempt)

    def send(self, slot, snap, attempt):
        adapter = ADAPTERS[slot.engine]
        req_sha, _ = self.writer.put_raw(slot.body, "json", request=True)
        headers = dict(slot.request["headers"])
        headers[slot.request["auth_header"]] = adapter.auth_value(self.keys[slot.engine])
        started = self.clock()
        self.calls += 1
        self.spent += slot.estimate
        self.manifest["budget"]["spent_estimate_usd"] = cost.dec_str(self.spent)
        raw_sha = raw_path = http_status = None
        try:
            http_status, body = self.transport(slot.request["method"], slot.request["url"], headers, slot.body)
        except TransportError as e:
            outcome = Outcome("failed", e.error_class, "", [], None, None)
        else:
            raw_sha, raw_path = self.writer.put_raw(body, _raw_ext(body))
            outcome = adapter.parse(http_status, body)
        rec = records.capture(
            self.manifest, snap, slot.prompt, slot.repeat_index, attempt, started_at=started,
            completed_at=self.clock(), status=outcome.status, request_sha256=req_sha, raw_sha256=raw_sha,
            raw_path=raw_path, answer_text=outcome.answer_text, citations=outcome.citations,
            cost_estimate_usd=cost.dec_str(slot.estimate), error_class=outcome.error_class,
            http_status=http_status, usage=outcome.usage, search_observed=outcome.search_observed)
        self.writer.append(rec)
        self.writer.write_manifest()
        self._note({"event": "capture", "done": self.calls, "total": len(self.plan.slots),
                    "engine": slot.engine, "prompt_id": slot.prompt["prompt_id"],
                    "repeat_index": slot.repeat_index, "attempt": attempt, "status": rec["status"],
                    "error_class": rec["error_class"], "spent_estimate_usd": cost.dec_str(self.spent)})
        return rec


def _raw_ext(body):
    try:
        json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "bin"
    return "json"


class FixtureTransport:
    """Serves queued (http_status, body) pairs or TransportError per engine URL.
    Records every call's (method, url, header names, body) in .calls; header
    values are kept only so tests can check the auth header was built."""

    kind = "fixture"

    def __init__(self, responses):
        self.responses = {url: list(q) for url, q in responses.items()}
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        item = self.responses[url].pop(0)
        if isinstance(item, TransportError):
            raise item
        return item


class UrllibTransport:
    """Live HTTPS transport. Never used by tests with a real opener."""

    kind = "live"

    def __init__(self, timeout_s=120, opener=urllib.request.urlopen):
        self.timeout_s, self.opener = timeout_s, opener

    def __call__(self, method, url, headers, body):
        if not url.startswith("https://"):
            raise CollectError("live transport sends to https only")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener(req, timeout=self.timeout_s) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (socket.timeout, TimeoutError):
            raise TransportError("timeout")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise TransportError("timeout")
            raise TransportError("connection")
        except (ConnectionError, OSError):
            raise TransportError("connection")
