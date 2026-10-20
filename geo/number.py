"""Number and Insufficient value objects (W4 5.1, 6.2; PLAN 5.4.1).

A Number cannot be constructed without a valid n and non-empty evidence ids.
Construction collects every intrinsic error and raises one NumberError. Checks
that need the run (ids resolve, window, exclusion status) happen in the renderer.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Tuple

from . import ids

LABELS = ("Measured", "First-party", "Published", "Estimated")
KINDS = ("count", "rate", "money")
EXCLUDED_STATUSES = ("failed", "refused", "not_checkable")

LABEL_PREFIXES = {
    "Measured": frozenset(("cap", "pc", "clm")),
    "First-party": frozenset(("fct",)),
    "Published": frozenset(("src",)),
}

# Provisional thresholds (W4 6.2, 7.2; PROGRESS.md Step 7). Status is
# "provisional": fixed for the first live run so results are comparable, but
# not yet calibrated against real data and subject to change afterward.
# N_MIN_REPEATS and MIN_ENGINES come from PLAN; the others have no source value
# and are project choices (PROGRESS.md, Step 6). T_LOW_PERCENT is an
# integer percent so a rate k/n is compared as k * 100 < T_LOW_PERCENT * n.
THRESHOLDS = {
    "N_MIN_REPEATS": {"value": 3, "status": "provisional"},
    "MIN_ENGINES": {"value": 2, "status": "provisional"},
    "N_MIN_ENGINE": {"value": 6, "status": "provisional"},
    "N_MIN_CONTRADICTION": {"value": 3, "status": "provisional"},
    "K_CONTRA_REPRODUCE": {"value": 2, "status": "provisional"},
    "T_LOW_PERCENT": {"value": 20, "status": "provisional"},
}
N_MIN_REPEATS = THRESHOLDS["N_MIN_REPEATS"]["value"]
N_MIN_ENGINE = THRESHOLDS["N_MIN_ENGINE"]["value"]
N_MIN_CONTRADICTION = THRESHOLDS["N_MIN_CONTRADICTION"]["value"]


def threshold_values():
    """The plain {name: int} map written to manifest.thresholds."""
    return {k: v["value"] for k, v in sorted(THRESHOLDS.items())}


@dataclass(frozen=True)
class Statistic:
    statistic_id: str
    kind: str
    label: str
    min_n: int


# Rows of W4 6.2 that are built now. fact_value is left out: W4 gives it kind
# n/a, which none of count, rate, money fits (open question in PROGRESS.md).
# repeat_agreement.engine is left out until it is needed.
REGISTRY = {s.statistic_id: s for s in (
    Statistic("citation_rate.engine_prompt", "rate", "Measured", N_MIN_REPEATS),
    Statistic("mention_rate.engine_prompt", "rate", "Measured", N_MIN_REPEATS),
    Statistic("citation_rate.engine", "rate", "Measured", N_MIN_ENGINE),
    Statistic("contradiction_rate.engine", "rate", "Measured", N_MIN_CONTRADICTION),
    Statistic("failure_rate.engine", "rate", "Measured", 1),
    Statistic("blocking_fail.key_pages", "count", "Measured", 1),
    Statistic("price", "money", "Published", 1),
    Statistic("cost_total.run", "money", "Estimated", 1),
)}


class NumberError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        self.codes = sorted({code for code, _ in self.errors})
        super().__init__("; ".join("%s: %s" % e for e in self.errors))


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _id_tuple_errors(name, value, errs, require_sorted):
    if not isinstance(value, tuple):
        errs.append(("E_TYPE", "%s must be a tuple" % name))
        return ()
    for i in value:
        if not ids.is_evidence_id(i):
            errs.append(("E_TYPE", "%s holds a non-evidence id %r" % (name, i)))
    if require_sorted and list(value) != sorted(value):
        errs.append(("E_TYPE", "%s must be sorted" % name))
    return value


def _ts_pair_errors(window, errs):
    if (not isinstance(window, tuple) or len(window) != 2
            or not all(isinstance(t, str) and ids.TS.fullmatch(t) for t in window)):
        errs.append(("E_TYPE", "window must be a (ts, ts) tuple"))
    elif window[0] > window[1]:
        errs.append(("E_WINDOW_MISMATCH", "window start is after its end"))


def _label_errors(label, basis_labels, evidence_ids, errs):
    if label not in LABELS:
        errs.append(("E_TYPE", "unknown label %r" % (label,)))
        return
    if not isinstance(basis_labels, tuple):
        errs.append(("E_TYPE", "basis_labels must be a tuple"))
        return
    prefixes = {ids.evidence_prefix(i) for i in evidence_ids if ids.is_evidence_id(i)}
    if label == "Estimated":
        if not basis_labels:
            errs.append(("E_LABEL_MIXED", "Estimated needs basis_labels"))
            return
        if any(b not in LABEL_PREFIXES for b in basis_labels):
            errs.append(("E_LABEL_MIXED", "basis_labels must be Measured, First-party or Published"))
            return
        covered = set().union(*(LABEL_PREFIXES[b] for b in basis_labels))
        missing = prefixes - covered
        if missing:
            errs.append(("E_LABEL_MIXED", "basis_labels do not cover evidence kinds %s" % sorted(missing)))
        return
    if basis_labels:
        errs.append(("E_LABEL_MIXED", "basis_labels are only for Estimated"))
    bad = prefixes - LABEL_PREFIXES[label]
    if bad:
        errs.append(("E_LABEL_MIXED", "%s does not accept evidence kinds %s" % (label, sorted(bad))))


@dataclass(frozen=True)
class Number:
    statistic_id: str
    kind: str
    value: Any
    n: Any
    min_n: Any
    evidence_ids: Tuple[str, ...]
    label: str
    window: Tuple[str, str]
    hit_ids: Tuple[str, ...] = ()
    excluded: Tuple[Tuple[str, str], ...] = ()
    basis_labels: Tuple[str, ...] = ()
    scope: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        errs = self.intrinsic_errors()
        if errs:
            raise NumberError(errs)

    def intrinsic_errors(self):
        errs = []
        stat = REGISTRY.get(self.statistic_id)
        if stat is None:
            errs.append(("E_TYPE", "unknown statistic_id %r" % (self.statistic_id,)))
        if self.kind not in KINDS:
            errs.append(("E_TYPE", "unknown kind %r" % (self.kind,)))
        elif stat is not None and stat.kind != self.kind:
            errs.append(("E_TYPE", "%s is kind %s, not %s" % (stat.statistic_id, stat.kind, self.kind)))
        if stat is not None and self.label != stat.label:
            errs.append(("E_LABEL_MIXED", "%s is labelled %s, not %s" % (stat.statistic_id, stat.label, self.label)))

        ev = _id_tuple_errors("evidence_ids", self.evidence_ids, errs, require_sorted=True)
        hits = _id_tuple_errors("hit_ids", self.hit_ids, errs, require_sorted=True)
        if not ev and isinstance(self.evidence_ids, tuple):
            errs.append(("E_EVIDENCE_EMPTY", "evidence_ids is empty"))
        if not _is_int(self.n):
            errs.append(("E_N_MISSING", "n is missing or not an int"))
        elif ev:
            if len(set(ev)) != len(ev):
                errs.append(("E_N_MISMATCH", "evidence_ids has duplicates"))
            if self.n != len(ev):
                errs.append(("E_N_MISMATCH", "n=%d but %d evidence ids" % (self.n, len(ev))))

        if not _is_int(self.min_n):
            errs.append(("E_MIN_N_OVERRIDE", "min_n must be an int"))
        elif stat is not None and self.min_n != stat.min_n:
            errs.append(("E_MIN_N_OVERRIDE", "min_n=%d but registry says %d" % (self.min_n, stat.min_n)))
        # Below-min is reported only for a consistent, non-empty n, so an empty or
        # miscounted evidence list yields exactly its own code (W5-05 N1, N2).
        if stat is not None and _is_int(self.n) and ev and self.n == len(ev) and self.n < stat.min_n:
            errs.append(("E_N_BELOW_MIN", "n=%d below min_n=%d; build an Insufficient" % (self.n, stat.min_n)))

        if self.kind in ("count", "rate"):
            if not _is_int(self.value):
                errs.append(("E_TYPE", "count and rate values are ints"))
            elif self.value != len(hits):
                errs.append(("E_VALUE_MISMATCH", "value=%d but %d hit ids" % (self.value, len(hits))))
            if set(hits) - set(ev):
                errs.append(("E_VALUE_MISMATCH", "hit_ids must be a subset of evidence_ids"))
        elif self.kind == "money":
            if not isinstance(self.value, Decimal) or not self.value.is_finite():
                errs.append(("E_TYPE", "money values are finite Decimal"))
            if hits:
                errs.append(("E_VALUE_MISMATCH", "money has no hit_ids"))

        if not isinstance(self.excluded, tuple):
            errs.append(("E_TYPE", "excluded must be a tuple"))
        else:
            for item in self.excluded:
                if (not isinstance(item, tuple) or len(item) != 2 or not ids.is_evidence_id(item[0])
                        or item[1] not in EXCLUDED_STATUSES):
                    errs.append(("E_TYPE", "excluded items are (evidence id, failed|refused|not_checkable)"))
                elif item[0] in ev:
                    errs.append(("E_EXCLUSION", "%s is both counted and excluded" % item[0]))

        _label_errors(self.label, self.basis_labels, ev, errs)
        _ts_pair_errors(self.window, errs)
        if not isinstance(self.scope, Mapping):
            errs.append(("E_TYPE", "scope must be a mapping"))
        return errs


@dataclass(frozen=True)
class Insufficient:
    """A statistic whose n is below min_n. It never carries a value."""
    statistic_id: str
    n: Any
    min_n: Any
    evidence_ids: Tuple[str, ...] = ()
    excluded: Tuple[Tuple[str, str], ...] = ()
    scope: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        errs = self.intrinsic_errors()
        if errs:
            raise NumberError(errs)

    def intrinsic_errors(self):
        errs = []
        stat = REGISTRY.get(self.statistic_id)
        if stat is None:
            errs.append(("E_TYPE", "unknown statistic_id %r" % (self.statistic_id,)))
        ev = _id_tuple_errors("evidence_ids", self.evidence_ids, errs, require_sorted=True)
        if not _is_int(self.n):
            errs.append(("E_N_MISSING", "n is missing or not an int"))
        elif self.n != len(ev) or len(set(ev)) != len(ev):
            errs.append(("E_N_MISMATCH", "n=%d but %d unique evidence ids" % (self.n, len(set(ev)))))
        if not _is_int(self.min_n):
            errs.append(("E_MIN_N_OVERRIDE", "min_n must be an int"))
        elif stat is not None and self.min_n != stat.min_n:
            errs.append(("E_MIN_N_OVERRIDE", "min_n=%d but registry says %d" % (self.min_n, stat.min_n)))
        if stat is not None and _is_int(self.n) and self.n >= stat.min_n:
            errs.append(("E_TYPE", "n meets min_n; build a Number"))
        if not isinstance(self.excluded, tuple):
            errs.append(("E_TYPE", "excluded must be a tuple"))
        else:
            for item in self.excluded:
                if (not isinstance(item, tuple) or len(item) != 2 or not ids.is_evidence_id(item[0])
                        or item[1] not in EXCLUDED_STATUSES):
                    errs.append(("E_TYPE", "excluded items are (evidence id, failed|refused|not_checkable)"))
        return errs


def build(statistic_id, kind, value, evidence_ids, hit_ids=(), excluded=(), window=None,
          basis_labels=(), scope=None):
    """Return a Number, or an Insufficient when n is below the registry minimum.

    min_n and label always come from the registry, so a caller cannot lower them.
    """
    stat = REGISTRY.get(statistic_id)
    if stat is None:
        raise NumberError([("E_TYPE", "unknown statistic_id %r" % (statistic_id,))])
    ev = tuple(sorted(evidence_ids))
    exc = tuple(sorted(tuple(x) for x in excluded))
    if len(ev) < stat.min_n:
        return Insufficient(statistic_id, len(ev), stat.min_n, ev, exc, dict(scope or {}))
    return Number(statistic_id, kind, value, len(ev), stat.min_n, ev, stat.label, window,
                  tuple(sorted(hit_ids)), exc, tuple(basis_labels), dict(scope or {}))


def to_dict(num):
    """JSON form of a Number or Insufficient, as stored in decision.numbers."""
    if isinstance(num, Insufficient):
        return {"statistic_id": num.statistic_id, "insufficient": True, "n": num.n, "min_n": num.min_n,
                "evidence_ids": list(num.evidence_ids), "excluded": [list(x) for x in num.excluded],
                "scope": dict(num.scope)}
    value = format(num.value, "f") if isinstance(num.value, Decimal) else num.value
    return {"statistic_id": num.statistic_id, "insufficient": False, "kind": num.kind, "value": value,
            "n": num.n, "min_n": num.min_n, "evidence_ids": list(num.evidence_ids), "label": num.label,
            "window": list(num.window), "hit_ids": list(num.hit_ids),
            "excluded": [list(x) for x in num.excluded], "basis_labels": list(num.basis_labels),
            "scope": dict(num.scope)}


NUMBER_DICT_FIELDS = ("statistic_id", "insufficient", "kind", "value", "n", "min_n", "evidence_ids", "label",
                      "window", "hit_ids", "excluded", "basis_labels", "scope")
INSUFFICIENT_DICT_FIELDS = ("statistic_id", "insufficient", "n", "min_n", "evidence_ids", "excluded", "scope")


def from_dict(d):
    """Rebuild a Number or Insufficient from to_dict output; raises NumberError on any problem."""
    if not isinstance(d, dict) or not isinstance(d.get("insufficient"), bool):
        raise NumberError([("E_TYPE", "a stored number is an object with a bool insufficient")])
    fields = INSUFFICIENT_DICT_FIELDS if d["insufficient"] else NUMBER_DICT_FIELDS
    if set(d) != set(fields):
        raise NumberError([("E_TYPE", "stored number fields %s, expected %s" % (sorted(d), sorted(fields)))])

    def tup(v):
        return tuple(v) if isinstance(v, list) else v

    excluded = tuple(tup(x) for x in d["excluded"]) if isinstance(d["excluded"], list) else d["excluded"]
    if d["insufficient"]:
        return Insufficient(d["statistic_id"], d["n"], d["min_n"], tup(d["evidence_ids"]), excluded, d["scope"])
    value = d["value"]
    if d["kind"] == "money" and isinstance(value, str):
        try:
            value = Decimal(value)
        except ArithmeticError:
            raise NumberError([("E_TYPE", "money value %r is not a decimal" % (value,))])
    return Number(d["statistic_id"], d["kind"], value, d["n"], d["min_n"], tup(d["evidence_ids"]), d["label"],
                  tup(d["window"]), tup(d["hit_ids"]), excluded, tup(d["basis_labels"]), d["scope"])
