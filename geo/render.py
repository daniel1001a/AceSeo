"""Report renderer (W4 5.2 to 5.5; PLAN 5.4.1 fragment subset).

The only input is a Report of typed fragments: Text, Number, Insufficient,
EvidenceRef, Url. Digits reach the output only through Number, Insufficient,
ids and URLs. The renderer itself appends the excluded/skipped section, the
not_checked list and the footer. All errors are collected into one RenderError;
output goes to a temp file that is os.replace'd only on success.
"""

import os
import re
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple

from . import ids
from .number import Insufficient, Number

FOOTER = ("These results describe API-model behaviour: answers returned by the configured models "
          "through their official APIs. They are not what users of consumer apps see "
          "(PLAN assumption A7).")

# W4 5.5 (a). Emitted by code on every report; a decision must list each item.
NOT_CHECKED_BASELINE = (
    ("consumer_ui_answers", "Answers shown inside consumer apps and search result pages were not observed."),
    ("personalization_location", "Personalisation, location and conversation history were not varied."),
    ("logged_in_surfaces", "Logged-in, app-only and paid surfaces were not observed."),
    ("engines_not_configured", "Engines that are not configured for this run were not queried."),
    ("traffic_ranking_outcomes", "Traffic, ranking and conversion outcomes were not measured."),
    ("gemini_grounding_excluded", "Gemini grounding with Google Search is excluded because its terms forbid "
                                  "storing or analysing grounded results."),
)
BASELINE_ITEMS = tuple(item for item, _ in NOT_CHECKED_BASELINE)

CAPTURE_RATE_STATS = ("citation_rate.engine_prompt", "mention_rate.engine_prompt")
_DIGIT = re.compile(r"\d")  # Unicode digits on purpose (W4 5.2, F14)


@dataclass(frozen=True)
class Text:
    text: str


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str


@dataclass(frozen=True)
class Url:
    url: str


@dataclass(frozen=True)
class Block:
    heading: Text
    fragments: Tuple


@dataclass(frozen=True)
class Report:
    title: Text
    blocks: Tuple[Block, ...]
    decision_ids: Tuple[str, ...] = ()


class RenderError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        self.codes = sorted({code for code, _ in self.errors})
        super().__init__("; ".join("%s: %s" % e for e in self.errors))


class _Ctx:
    def __init__(self, index):
        self.index = index
        self.errors = []
        self.insufficient = []

    def err(self, code, msg):
        self.errors.append((code, msg))


def _text(frag, ctx, where):
    if not isinstance(frag, Text) or not isinstance(frag.text, str):
        ctx.err("E_TYPE", "%s must be Text, got %s" % (where, type(frag).__name__))
        return ""
    if _DIGIT.search(frag.text):
        ctx.err("E_STRAY_DIGIT", "digit in Text at %s: %r" % (where, frag.text))
        return ""
    return frag.text


def _resolve(eid, ctx):
    ev = ctx.index.lookup(eid)
    if ev is None:
        ctx.err("E_EVIDENCE_UNRESOLVED", "%s does not resolve in the run" % eid)
    return ev


def _check_number_against_run(num, ctx):
    for code, msg in num.intrinsic_errors():
        ctx.err(code, msg)
    resolved = [_resolve(e, ctx) for e in num.evidence_ids]
    for h in num.hit_ids:
        _resolve(h, ctx)
    for eid, status in num.excluded:
        ev = _resolve(eid, ctx)
        if ev is not None and ev.status != status:
            ctx.err("E_EXCLUSION", "%s is listed as %s but is %s" % (eid, status, ev.status))
    if any(ev is None for ev in resolved):
        return
    if num.statistic_id == "failure_rate.engine":
        _check_failure_rate(num, resolved, ctx)
    else:
        for ev in resolved:
            if ev.status != "ok":
                ctx.err("E_EXCLUSION", "%s is counted but its status is %s" % (ev.id, ev.status))
    times = [ev.timestamp for ev in resolved if ev.timestamp is not None]
    if times and (min(times), max(times)) != tuple(num.window):
        ctx.err("E_WINDOW_MISMATCH", "%s window %s does not equal evidence range %s..%s"
                % (num.statistic_id, num.window, min(times), max(times)))
    if num.statistic_id in CAPTURE_RATE_STATS or num.statistic_id == "failure_rate.engine":
        engine = num.scope.get("engine")
        prompt_id = num.scope.get("prompt_id") if num.statistic_id in CAPTURE_RATE_STATS else None
        if engine is None or (num.statistic_id in CAPTURE_RATE_STATS and prompt_id is None):
            ctx.err("E_TYPE", "%s needs scope engine%s" % (
                num.statistic_id, " and prompt_id" if prompt_id is None else ""))
        elif num.statistic_id in CAPTURE_RATE_STATS:
            expected = ctx.index.non_ok_captures(engine, prompt_id)
            missing = sorted(set(expected) - set(num.excluded))
            if missing:
                ctx.err("E_EXCLUDED_MISSING", "%s omits excluded attempts %s"
                        % (num.statistic_id, [m[0] for m in missing]))


def _check_failure_rate(num, resolved, ctx):
    """failure_rate counts every attempt of the engine; its hits are exactly the non-ok ones."""
    engine = num.scope.get("engine")
    if engine is None:
        return
    for ev in resolved:
        if ev.kind != "capture" or ev.record.get("engine") != engine:
            ctx.err("E_EXCLUSION", "%s is not a capture of %s" % (ev.id, engine))
    attempts = sorted(r["id"] for r in ctx.index.of_kind("capture") if r["engine"] == engine)
    missing = sorted(set(attempts) - set(num.evidence_ids))
    if missing:
        ctx.err("E_EXCLUDED_MISSING", "failure_rate.engine omits attempts %s" % missing)
    non_ok = sorted(i for i, _ in ctx.index.non_ok_captures(engine))
    if sorted(num.hit_ids) != [i for i in non_ok if i in set(num.evidence_ids)]:
        ctx.err("E_VALUE_MISMATCH", "failure_rate.engine hits must be exactly the non-ok attempts")


def _fmt_number(num):
    ev = ", ".join(num.evidence_ids)
    label = num.label
    if num.basis_labels:
        label += "; basis " + ", ".join(num.basis_labels)
    if num.kind == "rate":
        head = "%d/%d" % (num.value, num.n)
    elif num.kind == "count":
        head = "%d (n=%d)" % (num.value, num.n)
    else:
        head = "USD %s (n=%d)" % (format(num.value, "f"), num.n)
    out = "%s [%s] {%s%s; evidence: %s" % (head, label, num.statistic_id, _fmt_scope(num.scope), ev)
    if num.hit_ids:
        out += "; hits: " + ", ".join(num.hit_ids)
    if num.excluded:
        out += "; excluded: " + _fmt_excluded(num.excluded)
    return out + "; window %s..%s}" % num.window


def _fmt_scope(scope):
    return "".join("; %s %s" % kv for kv in sorted(scope.items())) if scope else ""


def _fmt_excluded(excluded):
    by = {}
    for eid, status in excluded:
        by.setdefault(status, []).append(eid)
    return "; ".join("%s [%s]" % (s, ", ".join(by[s])) for s in sorted(by))


def _fmt_insufficient(ins):
    out = "insufficient evidence (n=%d, minimum %d) {%s%s; evidence: %s" % (
        ins.n, ins.min_n, ins.statistic_id, _fmt_scope(ins.scope), ", ".join(ins.evidence_ids) or "none")
    if ins.excluded:
        out += "; excluded: " + _fmt_excluded(ins.excluded)
    return out + "}"


def _fragment(frag, ctx, where):
    if isinstance(frag, Text):
        return _text(frag, ctx, where)
    if isinstance(frag, Number):
        _check_number_against_run(frag, ctx)
        return _fmt_number(frag)
    if isinstance(frag, Insufficient):
        for code, msg in frag.intrinsic_errors():
            ctx.err(code, msg)
        for eid in frag.evidence_ids:
            _resolve(eid, ctx)
        for eid, _ in frag.excluded:
            _resolve(eid, ctx)
        ctx.insufficient.append(frag)
        return _fmt_insufficient(frag)
    if isinstance(frag, EvidenceRef):
        if not ids.is_evidence_id(frag.evidence_id):
            ctx.err("E_TYPE", "EvidenceRef %r is not an evidence id" % (frag.evidence_id,))
            return ""
        _resolve(frag.evidence_id, ctx)
        return "[%s]" % frag.evidence_id
    if isinstance(frag, Url):
        if not isinstance(frag.url, str) or not re.match(r"https?://[^\s<>]+$", frag.url):
            ctx.err("E_TYPE", "Url %r is not an http(s) URL" % (frag.url,))
            return ""
        return "<%s>" % frag.url
    ctx.err("E_TYPE", "unsupported fragment %s at %s" % (type(frag).__name__, where))
    return ""


def _excluded_section(index):
    m = index.manifest
    lines = ["## Excluded and skipped", ""]
    non_ok = index.non_ok_captures()
    by_id = {r["id"]: r for r in index.of_kind("capture")}
    if non_ok:
        for eid, status in non_ok:
            r = by_id[eid]
            reason = r.get("error_class") or status
            lines.append("- %s: %s (%s)" % (eid, status, reason))
    else:
        lines.append("- no failed or refused attempts")
    for s in m.get("skipped_slots", []):
        lines.append("- skipped slot %s %s repeat %d: %s" % (s["engine"], s["prompt_id"], s["repeat_index"], s["reason"]))
    for e in m.get("engines_excluded", []):
        lines.append("- engine %s excluded: %s (terms_status %s)" % (e["engine"], e["reason"], e["terms_status"]))
    for r in index.of_kind("page_check"):
        if r.get("result") == "not_checkable":
            lines.append("- %s: not_checkable (%s)" % (r["id"], r.get("not_checkable_reason")))
    return lines


def _not_checked_section(index, ctx):
    lines = ["## Not checked", ""]
    for item, text in NOT_CHECKED_BASELINE:
        lines.append("- %s: %s" % (item, text))
    m = index.manifest
    for e in m.get("engines_excluded", []):
        lines.append("- engine_excluded: %s (%s)" % (e["engine"], e["reason"]))
    if m.get("skipped_slots"):
        lines.append("- skipped_slots: listed under Excluded and skipped")
    for r in index.of_kind("page_check"):
        if r.get("result") == "not_checkable":
            lines.append("- page_check_not_checkable: %s" % r["id"])
    for r in index.of_kind("claim"):
        if r.get("verdict") in ("needs_review", "unsupported"):
            lines.append("- claim_%s: %s" % (r["verdict"], r["id"]))
    # One line per statistic and n: a repeats-1 run otherwise lists the same
    # line once per prompt. Each measurement keeps its scope under Measurements.
    groups = {}
    for ins in ctx.insufficient:
        key = (ins.statistic_id, ins.n, ins.min_n)
        groups[key] = groups.get(key, 0) + 1
    for (stat, n, min_n), count in groups.items():
        lines.append("- insufficient: %s (n=%d, minimum %d)%s" % (
            stat, n, min_n, " x%d, listed under Measurements" % count if count > 1 else ""))
    return lines


def _proposals_section(index):
    """LLM proposals (proposals.jsonl): listed for review, never counted."""
    if not index.proposals:
        return []
    lines = ["", "## LLM-proposed claims (not counted)", "",
             "Proposed by an LLM outside the run and checked only for their quote. No rule read them;",
             "confirm one with `aceseo confirm` to turn it into a rule for the next run.", ""]
    for r in sorted(index.proposals, key=lambda r: r["id"]):
        lines.append("- %s %s, in capture %s: %s" % (
            r["id"], "fact %s" % r["fact_key"] if r["fact_key"] else "no fact", r["capture_id"], r["statement"]))
    return lines


def _check_decisions(report, ctx):
    for did in report.decision_ids:
        ev = _resolve(did, ctx)
        if ev is None:
            continue
        if ev.kind != "decision":
            ctx.err("E_TYPE", "%s is not a decision" % did)
            continue
        items = ev.record.get("not_checked")
        if not items:
            ctx.err("E_NOT_CHECKED_MISSING", "%s has an empty not_checked" % did)
            continue
        listed = {i.get("item") for i in items if isinstance(i, dict)}
        missing = [b for b in BASELINE_ITEMS if b not in listed]
        if missing:
            ctx.err("E_NOT_CHECKED_MISSING", "%s not_checked lacks %s" % (did, missing))


def render_text(report, index):
    """Return the report text or raise RenderError with every error found."""
    ctx = _Ctx(index)
    if not isinstance(report, Report):
        raise RenderError([("E_TYPE", "input must be a Report")])
    out = ["# " + _text(report.title, ctx, "title"), ""]
    out.append("Run: %s (transport %s)" % (index.manifest.get("run_id"), index.manifest.get("transport")))
    out.append("")
    for bi, block in enumerate(report.blocks):
        if not isinstance(block, Block):
            ctx.err("E_TYPE", "block %d is %s, not Block" % (bi, type(block).__name__))
            continue
        out.append("## " + _text(block.heading, ctx, "block %d heading" % bi))
        out.append("")
        if not isinstance(block.fragments, tuple):
            ctx.err("E_TYPE", "block %d fragments must be a tuple" % bi)
            continue
        out.append("".join(_fragment(f, ctx, "block %d fragment %d" % (bi, fi))
                           for fi, f in enumerate(block.fragments)))
        out.append("")
    _check_decisions(report, ctx)
    out.extend(_excluded_section(index))
    out.append("")
    out.extend(_not_checked_section(index, ctx))
    out.extend(_proposals_section(index))
    out.extend(["", "---", FOOTER, ""])
    if ctx.errors:
        raise RenderError(ctx.errors)
    text = "\n".join(out)
    if FOOTER not in text:  # asserted after rendering (W4 5.5)
        raise RenderError([("E_NOT_CHECKED_MISSING", "footer missing")])
    return text


def render(report, index, out_path):
    """Render to out_path, which must not exist. No file is left behind on failure."""
    if os.path.exists(out_path):
        raise FileExistsError(out_path)
    text = render_text(report, index)
    d = os.path.dirname(os.path.abspath(out_path))
    fd, tmp = tempfile.mkstemp(prefix=".render-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return out_path


__all__ = ["Block", "Decimal", "EvidenceRef", "FOOTER", "NOT_CHECKED_BASELINE", "Report",
           "RenderError", "Text", "Url", "render", "render_text"]
