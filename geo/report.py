"""Report builder: a decision record -> render.Report (W4 5).

Prose is Text without digits. Every number in the report is a Number or an
Insufficient rebuilt from the decision record, so each one carries its n and
evidence ids, and the renderer checks them against the run again. Rule ids
(R0 to R4) contain digits, so rules are named in words; the decision record
and its EvidenceRef keep the ids.
"""

from . import number
from .number import NumberError
from .render import Block, EvidenceRef, Report, Text, Url

RULE_NAMES = {
    "R0": "evidence gate",
    "R1": "blocking SEO checks on key pages",
    "R2": "reproduced fact contradictions",
    "R3": "low citation across vendors",
    "R4": "no other rule fired",
}

OUTCOME_TEXT = {
    "seo_first": "SEO first. A blocking check failed on a key page. Fix it before any GEO work, because AI "
                 "search engines cannot cite a page they cannot fetch or index.",
    "insufficient_evidence": "Insufficient evidence. There are not enough usable captures, or a key page "
                             "could not be checked. Collect more evidence before acting on GEO.",
    "geo_fix_facts": "GEO first: fix facts. Several answers repeat the same claim that contradicts the "
                     "site's own facts. Make the correct fact easier to find and quote.",
    "geo_content": "GEO first: content. Key pages pass the blocking checks, but the configured engines "
                   "rarely cite the site. Work on content that answers the prompts.",
    "no_action": "No action. Key pages pass the blocking checks and no GEO rule fired.",
}

# W5-09: the sentences above are draft wording, not reviewed by the lead. Each
# recommendation says so, in words, right after the sentence.
PROVISIONAL_WORDING_NOTE = " (provisional wording)"

CLAIM_VERDICTS = ("contradicted", "outdated")


class ReportError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__("%s: %s" % (code, message))


def _item(frags):
    """A list item; the first one in a block has no leading newline."""
    return [Text("\n- " if frags else "- ")]


def _refs(ids, sep=", "):
    out = []
    for i, eid in enumerate(ids):
        if i:
            out.append(Text(sep))
        out.append(EvidenceRef(eid))
    return out


def stored_numbers(dec):
    """Rebuild every stored number. A missing n, missing ids or any other defect refuses the report."""
    nums = dec.get("numbers")
    if not isinstance(nums, list):
        raise ReportError("E_SCHEMA", "%s has no numbers list" % dec.get("id"))
    out = []
    for i, d in enumerate(nums):
        try:
            out.append(number.from_dict(d))
        except NumberError as e:
            raise ReportError("E_SCHEMA", "%s numbers[%d]: %s" % (dec.get("id"), i, e))
    return out


def _decision(index, decision_id):
    ev = index.lookup(decision_id)
    if ev is None or ev.kind != "decision":
        raise ReportError("E_REF_UNRESOLVED", "%s is not a decision in this run" % decision_id)
    return ev.record


def build_report(index, decision_id):
    dec = _decision(index, decision_id)
    nums = stored_numbers(dec)
    fired = dec["fired_rule_id"]

    rec = [Text(OUTCOME_TEXT[dec["outcome"]] + PROVISIONAL_WORDING_NOTE),
           Text(" The deciding rule is the %s rule. Decision record: " % RULE_NAMES[fired]),
           EvidenceRef(decision_id), Text(".")]
    if dec["hypothesis"]:
        rec.append(Text(" This outcome is a hypothesis to test, not a measured effect."))
    rec.append(Text(" All thresholds are provisional, fixed for the first live run but not yet calibrated "
                    "against real data; the decision record keeps their values."))
    blocks = [Block(Text("Recommendation"), tuple(rec))]

    rules = []
    for e in dec["evaluations"]:
        rules += _item(rules) + [Text("%s: %s (%s)." % (RULE_NAMES[e["rule_id"]], e["result"], e["reason_code"]))]
        if e["input_ids"]:
            rules += [Text(" Read: ")] + _refs(e["input_ids"])
    blocks.append(Block(Text("Rule evaluations"), tuple(rules)))

    meas = []
    for n in nums:
        meas += _item(meas) + [n]
    blocks.append(Block(Text("Measurements"), tuple(meas)))

    groups = []
    for g in dec["confidence_basis"]:
        groups += _item(groups) + [Text("%s: " % g["group_key"])] + _refs(g["evidence_ids"])
    blocks.append(Block(Text("Independence groups"), tuple(groups)))

    fails = [r for r in index.of_kind("page_check")
             if r["url_role"] == "key" and r["blocking_on_fail"] and r["result"] == "fail"]
    if fails:
        frags = []
        for r in fails:
            frags += _item(frags) + [EvidenceRef(r["id"]), Text(" %s failed (%s) on " % (r["check_name"],
                                                                                    r["agent_profile"])),
                      Url(r["url_norm"])]
        blocks.append(Block(Text("Failing blocking checks"), tuple(frags)))

    bad = [c for c in index.of_kind("claim") if c["verdict"] in CLAIM_VERDICTS]
    if bad:
        frags = []
        for c in bad:
            frags += _item(frags) + [EvidenceRef(c["id"]), Text(" is %s against fact " % c["verdict"]),
                      EvidenceRef(c["fact_ref"]), Text(", in capture "), EvidenceRef(c["capture_id"])]
        blocks.append(Block(Text("Contradicted or outdated claims"), tuple(frags)))

    return Report(Text("GEO evidence report"), tuple(blocks), decision_ids=(decision_id,))


def latest_decision_id(index):
    decs = sorted(index.of_kind("decision"), key=lambda d: (d["created_at"], d["id"]))
    if not decs:
        raise ReportError("E_NO_DECISION", "the run has no decision record")
    return decs[-1]["id"]
