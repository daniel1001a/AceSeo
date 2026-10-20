"""In-memory index of one run's records, used by the renderer to resolve evidence ids."""

from collections import namedtuple

Evidence = namedtuple("Evidence", "id kind status timestamp record")

# The timestamp that places each kind of evidence in time (Number.window).
_TIME_FIELD = {"capture": "completed_at", "page_check": "fetched_at", "claim": "created_at",
               "decision": "created_at"}


def _status(record):
    kind = record.get("kind")
    if kind == "capture":
        return record.get("status")
    if kind == "page_check":
        return "not_checkable" if record.get("result") == "not_checkable" else "ok"
    return "ok"


class RunIndex:
    """records: iterable of record dicts. aux: {fct_/src_ id: {"timestamp": ts}}."""

    def __init__(self, manifest, records, aux=None):
        self.manifest = manifest
        self.records = list(records)
        self._by_id = {}
        for r in self.records:
            rid = r["id"]
            self._by_id[rid] = Evidence(rid, r["kind"], _status(r), r.get(_TIME_FIELD[r["kind"]]), r)
        for aid, info in (aux or {}).items():
            self._by_id[aid] = Evidence(aid, aid.split("_", 1)[0], "ok", info.get("timestamp"), info)

    def lookup(self, evidence_id):
        return self._by_id.get(evidence_id)

    def of_kind(self, kind):
        return [r for r in self.records if r["kind"] == kind]

    def non_ok_captures(self, engine=None, prompt_id=None):
        out = []
        for r in self.of_kind("capture"):
            if r["status"] == "ok":
                continue
            if engine is not None and r["engine"] != engine:
                continue
            if prompt_id is not None and r["prompt_id"] != prompt_id:
                continue
            out.append((r["id"], r["status"]))
        return sorted(out)
