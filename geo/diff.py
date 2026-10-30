"""aceseo diff RUN_A RUN_B: what changed between two runs that both validate.

Every number comes from the stored decision numbers (report.stored_numbers),
so a rate is shown as k/n exactly as the decision recorded it; nothing is
recomputed. Claim verdicts count rule claims only (LLM proposals are never
counted). Page checks are compared by check name, URL, agent profile and
params. The output is sorted and byte-stable for the same two runs.

Two runs with different facts or prompts files are not comparable, so diff
refuses unless allow_input_change is given; then the change is stated first.
"""

from collections import Counter

from .canonical import canonical_bytes
from .decide import rule_claims
from .number import Insufficient
from .report import _decision, latest_decision_id, stored_numbers

INPUT_HASHES = (("facts", "facts_sha256"), ("prompts", "prompts_sha256"))


class DiffError(ValueError):
    pass


def _num_text(num):
    if num is None:
        return "absent"
    if isinstance(num, Insufficient):
        return "insufficient (n=%d, needs %d)" % (num.n, num.min_n)
    if num.kind == "money":
        return "$%s" % num.value
    if num.kind == "rate":
        return "%d/%d" % (num.value, num.n)
    return "%d (n=%d)" % (num.value, num.n)


def _scope_text(scope):
    return " ".join("%s=%s" % (k, scope[k]) for k in sorted(scope))


def _numbers(index):
    dec = _decision(index, latest_decision_id(index))
    out = {}
    for num in stored_numbers(dec):
        label = num.statistic_id + (" " + _scope_text(num.scope) if num.scope else "")
        out[label] = num
    return dec, out


def _verdicts(index):
    by_fact = {}
    for c in rule_claims(index.of_kind("claim")):
        by_fact.setdefault(c["fact_key"], Counter())[c["verdict"]] += 1
    return by_fact


def _counter_text(counter):
    if not counter:
        return "none"
    return ", ".join("%s %d" % (v, counter[v]) for v in sorted(counter))


def _page_checks(index):
    out = {}
    for pc in index.of_kind("page_check"):
        key = "%s %s" % (pc["check_name"], pc["url_norm"])
        if pc.get("agent_profile") not in (None, "default"):
            key += " (%s)" % pc["agent_profile"]
        if pc.get("params"):
            key += " " + canonical_bytes(pc["params"]).decode("utf-8")
        out.setdefault(key, []).append(pc["result"])
    return {k: ", ".join(sorted(v)) for k, v in out.items()}


def _section(title, a, b, render):
    keys = sorted(set(a) | set(b))
    changed = [k for k in keys if render(a.get(k)) != render(b.get(k))]
    lines = ["", "## %s" % title, ""]
    lines += ["- %s: %s -> %s" % (k, render(a.get(k)), render(b.get(k))) for k in changed]
    if not keys:
        lines.append("- none in either run")
    elif not changed:
        lines.append("- no change")
    lines.append("(%d unchanged)" % (len(keys) - len(changed)))
    return lines


def diff_text(index_a, index_b, allow_input_change=False):
    ma, mb = index_a.manifest, index_b.manifest
    changed_inputs = [name for name, field in INPUT_HASHES if ma.get(field) != mb.get(field)]
    if changed_inputs and not allow_input_change:
        raise DiffError("the runs used different %s files, so their numbers are not comparable; "
                        "pass --allow-input-change to compare anyway" % " and ".join(changed_inputs))
    dec_a, nums_a = _numbers(index_a)
    dec_b, nums_b = _numbers(index_b)
    lines = ["# aceseo diff", "",
             "A: %s (started %s)" % (ma["run_id"], ma["started_at"]),
             "B: %s (started %s)" % (mb["run_id"], mb["started_at"])]
    if changed_inputs:
        lines.append("WARNING: the %s file changed between the runs; differences below may come from that"
                     % " and ".join(changed_inputs))
    lines.append("outcome: %s (rule %s) -> %s (rule %s)" % (
        dec_a["outcome"], dec_a["fired_rule_id"], dec_b["outcome"], dec_b["fired_rule_id"]))
    lines += _section("Numbers (rates as k/n, from each run's latest decision)", nums_a, nums_b, _num_text)
    lines += _section("Rule-claim verdicts by fact", _verdicts(index_a), _verdicts(index_b),
                      lambda c: _counter_text(c or Counter()))
    lines += _section("Page checks", _page_checks(index_a), _page_checks(index_b),
                      lambda r: r if r is not None else "absent")
    return "\n".join(lines) + "\n"
