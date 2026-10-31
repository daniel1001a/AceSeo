"""LLM-proposed claims: an LLM may propose, only rules decide (SPEC D1).

The LLM step runs outside this tool, for example in Claude Code on a
subscription, so it needs no API key. It reads a run's captures and writes a
proposals file:

  {"model": "who proposed, free text",
   "proposals": [{"capture_id": "cap_...", "quote": "exact sentence from the answer",
                  "fact_key": "a key in the run's facts, or null",
                  "asserted_value": <what the sentence says the value is, optional>}]}

import_proposals checks every quote exists in the capture's answer, stores each
as a claim with matcher "llm" and verdict needs_review in RUN_DIR/proposals.jsonl
and validates the run again. That file sits beside the run's record files and
decide never reads it, so a proposal cannot change a decision, the run's
records or its report numbers.

confirm_proposal turns a proposal the user agrees with into a rule: it adds a
phrase from the quote to the fact's "match" block in the user's facts file. The
rule matcher then decides that kind of sentence in the next run. Nothing in an
existing run is edited.
"""

import json
import os

from . import facts as facts_mod
from .canonical import canonical_bytes, strict_loads
from .claims import _decide, claim_record, facts_by_key, match_text
from .store import PROPOSALS_FILE
from .validate import load_valid_run

LLM_MATCHER = "llm"
LLM_MATCHER_VERSION = 1
DOC_FIELDS = {"model", "proposals"}
PROPOSAL_FIELDS = {"capture_id", "quote", "fact_key", "asserted_value"}


class ProposalError(ValueError):
    pass


def _run_facts(run_dir):
    with open(os.path.join(run_dir, "inputs", "facts.json"), "rb") as f:
        return strict_loads(f.read().decode("utf-8"))


def _check_doc(doc):
    if not isinstance(doc, dict) or set(doc) != DOC_FIELDS:
        raise ProposalError("the proposals file must be an object with exactly %s" % sorted(DOC_FIELDS))
    if not isinstance(doc["model"], str) or not doc["model"].strip():
        raise ProposalError("model must name who proposed the claims")
    if not isinstance(doc["proposals"], list) or not doc["proposals"]:
        raise ProposalError("proposals must be a non-empty list")
    for i, p in enumerate(doc["proposals"]):
        if not isinstance(p, dict) or not {"capture_id", "quote", "fact_key"} <= set(p) <= PROPOSAL_FIELDS:
            raise ProposalError("proposals[%d] needs capture_id, quote, fact_key (asserted_value optional)" % i)
        if not isinstance(p["capture_id"], str) or not isinstance(p["quote"], str) or not p["quote"].strip():
            raise ProposalError("proposals[%d]: capture_id and quote must be non-empty strings" % i)
        if p["fact_key"] is not None and not isinstance(p["fact_key"], str):
            raise ProposalError("proposals[%d]: fact_key must be a string or null" % i)


def comparison(fact, proposal):
    """What the asserted value would be against the fact, for the user to read. Never stored."""
    if fact is None:
        return "no fact"
    if "asserted_value" not in proposal:
        return "no asserted value"
    verdict, basis = _decide(fact["key"], fact, proposal["asserted_value"])
    return "%s (%s)" % (verdict, basis)


def build_proposals(index, facts_doc, doc, created_at):
    """Return [(claim record, proposal, comparison)] or raise ProposalError."""
    _check_doc(doc)
    captures = {c["id"]: c for c in index.of_kind("capture")}
    facts = facts_by_key(facts_doc)
    out = []
    for i, p in enumerate(doc["proposals"]):
        cap = captures.get(p["capture_id"])
        if cap is None or cap["status"] != "ok":
            raise ProposalError("proposals[%d]: %r is not an ok capture of this run" % (i, p["capture_id"]))
        text = cap["answer_text"] or ""
        quote = p["quote"].strip()
        start = text.find(quote)
        if start < 0:
            raise ProposalError("proposals[%d]: the quote is not in the answer of %s" % (i, cap["id"]))
        key = p["fact_key"]
        if key is not None and key not in facts:
            raise ProposalError("proposals[%d]: fact_key %r is not in the run's facts" % (i, key))
        rec = claim_record(
            index.manifest, cap, span_start=start, span_end=start + len(quote), statement=quote,
            fact_key=key, fact_value_snapshot=facts[key]["value"] if key else None,
            verdict="needs_review", verdict_basis="undecided", created_at=created_at,
            matcher=LLM_MATCHER, matcher_version=LLM_MATCHER_VERSION)
        out.append((rec, p, comparison(facts.get(key), p)))
    return out


def import_proposals(run_dir, doc, created_at, secrets=()):
    """Append the proposals to RUN_DIR/proposals.jsonl; return build_proposals' list."""
    index = load_valid_run(run_dir, secrets)
    built = build_proposals(index, _run_facts(run_dir), doc, created_at)
    taken = {r["id"] for r in index.records} | {r["id"] for r in index.proposals}
    new_ids = set()
    for rec, _, _ in built:
        if rec["id"] in taken or rec["id"] in new_ids:
            raise ProposalError("%s is already in this run (same capture, span and fact)" % rec["id"])
        new_ids.add(rec["id"])
    data = b"".join(canonical_bytes(rec) + b"\n" for rec, _, _ in built)
    for s in secrets:
        if s and s.encode("utf-8") in data:
            raise ProposalError("a proposal contains a secret; nothing written")
    with open(os.path.join(run_dir, PROPOSALS_FILE), "ab") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    load_valid_run(run_dir, secrets)
    return built


# --- confirm: promote a proposal to a rule in the user's facts file ----------

def _promote(fact, phrase, value):
    """Return the fact's new match block with phrase added, or raise ProposalError."""
    vt = fact.get("value_type")
    match = json.loads(json.dumps(fact.get("match") or {}))
    if vt == "boolean":
        if value not in ("true", "false"):
            raise ProposalError("a boolean fact needs --value true or --value false")
        side = "positive" if value == "true" else "negative"
        match.setdefault("positive", [])
        match.setdefault("negative", [])
        target = match[side]
    elif vt == "enum":
        allowed = fact.get("enum_values") or []
        if value not in allowed:
            raise ProposalError("an enum fact needs --value, one of %s" % allowed)
        target = match.setdefault("values", {}).setdefault(value, [])
    elif vt == "integer":
        if value is not None:
            raise ProposalError("an integer fact takes no --value; the phrase becomes a unit term")
        target = match.setdefault("unit_terms", [])
    else:
        raise ProposalError("fact %r has value_type %r; only boolean, integer and enum facts take a match block"
                            % (fact["key"], vt))
    if phrase.lower() in (t.lower() for t in target):
        raise ProposalError("%r is already a match phrase of %s" % (phrase, fact["key"]))
    target.append(phrase)
    return match


def confirm_proposal(run_dir, claim_id, facts_path, phrase, value=None):
    """Add phrase to the match block of the proposal's fact in facts_path.

    Returns (spec, new facts doc) where spec is what the rule matcher now decides
    for the proposal's statement. The file is only written when that decision
    is about the proposal's fact."""
    index = load_valid_run(run_dir)
    rec = next((r for r in index.proposals if r["id"] == claim_id), None)
    if rec is None:
        raise ProposalError("%s is not an LLM proposal of this run (see aceseo ledger)" % claim_id)
    if rec["fact_key"] is None:
        raise ProposalError("%s has no fact_key; add the fact to the facts file first" % claim_id)
    if not phrase or phrase.lower() not in rec["statement"].lower():
        raise ProposalError("the phrase must be part of the statement: %r" % rec["statement"])
    with open(facts_path, "rb") as f:
        doc = strict_loads(f.read().decode("utf-8"))
    problems = facts_mod.runtime_problems(doc)
    if problems:
        raise ProposalError("%s: %s" % (facts_path, "; ".join(problems)))
    fact = facts_by_key(doc).get(rec["fact_key"])
    if fact is None:
        raise ProposalError("%s has no fact %r" % (facts_path, rec["fact_key"]))
    fact["match"] = _promote(fact, phrase, value)
    problems = facts_mod.runtime_problems(doc)
    if problems:
        raise ProposalError("the new match block is refused: %s" % "; ".join(problems))
    cap = next(c for c in index.of_kind("capture") if c["id"] == rec["capture_id"])
    specs = [s for s in match_text(rec["statement"], doc,
                                  context_text=cap["answer_text"],
                                  source_urls=[c["url"] for c in cap["citations"]])
             if s.fact_key == rec["fact_key"]]
    if not specs:
        raise ProposalError("with that phrase the rule matcher still does not decide %r for %s; "
                            "the statement must also name the site and the phrase must cover the value"
                            % (rec["statement"], rec["fact_key"]))
    tmp = facts_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, facts_path)
    return specs[0], doc
