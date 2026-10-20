"""Copy the raw provider responses of a run into regression fixtures.

export_fixtures reads a run that validates, takes each capture's raw response
body, replaces identifier fields (REDACT_KEYS, at any depth) with "redacted",
re-parses the redacted body with the capture's adapter and refuses unless the
outcome still equals what the capture recorded. It then writes
<dest>/<engine>/<sha256 of the redacted body>.json plus <dest>/index.json,
which tests/test_live_fixtures.py replays. Nothing is sent.

Only JSON bodies are exported. The redaction is a fixed key list, not a
detector: read the files before committing them.
"""

import json
import os

from .adapters import ADAPTERS
from .canonical import canonical_bytes, sha256_hex
from .validate import load_valid_run

# id..previous_response_id: account/session identifiers. signature,
# encrypted_content, tool_use_id: opaque per-response provider blobs the
# adapters never read; dropped so the fixtures do not carry them for no
# reason (release cleanup, 2026-10-20).
REDACT_KEYS = ("id", "user", "safety_identifier", "prompt_cache_key", "metadata", "previous_response_id",
               "signature", "encrypted_content", "tool_use_id")
REDACTED = "redacted"
INDEX = "index.json"


class ExportError(ValueError):
    pass


def redact(obj):
    if isinstance(obj, dict):
        return {k: (REDACTED if k in REDACT_KEYS and v is not None else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def expected(outcome):
    return {"status": outcome.status, "error_class": outcome.error_class,
            "answer_text_sha256": sha256_hex(outcome.answer_text.encode("utf-8")),
            "citation_urls": [c["url"] for c in outcome.citations],
            "usage": outcome.usage, "search_observed": outcome.search_observed}


def _recorded(cap):
    return {"status": cap["status"], "error_class": cap["error_class"],
            "answer_text_sha256": sha256_hex(cap["answer_text"].encode("utf-8")),
            "citation_urls": [c["url"] for c in cap["citations"]],
            "usage": cap["usage"], "search_observed": cap["search_observed"]}


def export_fixtures(run_dir, dest, secrets=()):
    """-> list of index entries written. dest/index.json must not exist yet."""
    index = load_valid_run(run_dir, secrets)
    if index.manifest["transport"] != "live":
        raise ExportError("only a live run holds real responses (this run's transport is %s)"
                          % index.manifest["transport"])
    index_path = os.path.join(dest, INDEX)
    if os.path.exists(index_path):
        raise ExportError("%s exists; export into an empty directory" % index_path)
    entries, files = [], {}
    for cap in sorted(index.of_kind("capture"), key=lambda c: c["id"]):
        adapter = ADAPTERS.get(cap["engine"])
        if adapter is None or cap["http_status"] is None or not cap["raw_path"].endswith(".json"):
            continue
        with open(os.path.join(run_dir, cap["raw_path"]), "rb") as f:
            raw = f.read()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        body = json.dumps(redact(doc), ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8") + b"\n"
        for s in secrets:
            if s and s.encode("utf-8") in body:
                raise ExportError("refusing: a secret appears in %s" % cap["raw_path"])
        exp = expected(adapter.parse(cap["http_status"], body))
        if exp != _recorded(cap):
            raise ExportError("redaction changed the parse of %s; not exported" % cap["id"])
        rel = "%s/%s.json" % (cap["engine"], sha256_hex(body))
        files[rel] = body
        entries.append({"file": rel, "engine": cap["engine"], "http_status": cap["http_status"],
                        "source_capture_id": cap["id"], "model": cap["engine_snapshot"]["model"], "expected": exp})
    if not entries:
        raise ExportError("no JSON provider responses in %s" % run_dir)
    for rel, body in files.items():
        path = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)
    doc = {"run_id": index.manifest["run_id"], "redacted_keys": list(REDACT_KEYS), "fixtures": entries}
    with open(index_path, "wb") as f:
        f.write(canonical_bytes(doc))
    return entries
