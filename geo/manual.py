"""Manual import: put an answer a person copied from a surface with no API into the claim ledger.

Some surfaces (for example Google AI Overviews) have no official API this tool
may call. A person can still read the answer themselves and save it as a text
file. import_manual stores that text, an optional screenshot and any source
URLs the person saw as one capture with access "manual", in a run of its own
(run_kind "manual", transport "manual"), then runs the same rule matcher over
it so its claims get evidence ids like any other.

A manual run never holds page checks or a decision, and decide refuses it, so
manual observations never enter a citation rate, a contradiction rate or a
rule outcome. They are listed by `geo ledger`, labelled manual.
"""

import unicodedata

from . import ids, number, records
from .canonical import canonical_bytes, strict_loads
from .claims import claims_for_run
from .config import prompt_inputs, with_config_sha
from .store import RunWriter, input_hashes
from .validate import load_valid_run

TOOL_VERSION = "manual-import-v1"
PROMPT_ID = "p_manual"


class ManualError(ValueError):
    pass


def manual_snapshot(surface, vendor, model):
    return with_config_sha({
        "engine": surface, "model": model, "model_vendor": vendor, "tool_version": TOOL_VERSION,
        "terms_status": records.MANUAL, "terms_url": None, "terms_last_updated": None,
        "terms_retrieved": None, "opt_in": False, "price_snapshot": [],
    })


def _citations(urls):
    out = []
    for i, u in enumerate(urls):
        try:
            ids.url_norm_v1(u)
        except ids.IdError:
            raise ManualError("source URL %r is not an absolute http(s) URL" % (u,))
        out.append({"url": u, "title": None, "cited_text": None, "position": i, "provider_field": "manual"})
    return out


def import_manual(root, *, text_bytes, surface, query, facts_bytes, mention_terms, observed_at, created_at,
                  screenshot_bytes=None, source_urls=(), vendor=None, model="unknown", secrets=()):
    """Create a manual run under root and return its directory.

    text_bytes: the answer exactly as saved (UTF-8). query: what the person typed
    into the surface. observed_at: when they saw the answer (a W4 ts)."""
    if not ids.is_slug(surface):
        raise ManualError("surface must be a slug like google-aio, got %r" % (surface,))
    vendor = vendor or surface.split("-")[0]
    if not ids.is_slug(vendor):
        raise ManualError("vendor must be a slug, got %r" % (vendor,))
    if not (ids.TS.fullmatch(observed_at or "") and ids.TS.fullmatch(created_at or "")):
        raise ManualError("observed_at and created_at must be timestamps like 2026-10-20T09:30:00.000000Z")
    if observed_at > created_at:
        raise ManualError("observed_at %s is in the future" % observed_at)
    try:
        answer = text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ManualError("the answer file is not UTF-8 text")
    if not answer.strip():
        raise ManualError("the answer file is empty")
    if not query or not query.strip():
        raise ManualError("query must be the text that was typed into the surface")
    if not mention_terms:
        raise ManualError("at least one mention term is needed")
    citations = _citations(source_urls)
    facts_doc = strict_loads(facts_bytes.decode("utf-8"))

    snap = manual_snapshot(surface, vendor, model)
    prompts_doc = prompt_inputs([{"prompt_id": PROMPT_ID, "text": unicodedata.normalize("NFC", query.strip())}])
    inputs = {"prompts": canonical_bytes(prompts_doc), "facts": facts_bytes,
              "sources": canonical_bytes({"sources": []})}
    manifest = records.new_manifest(
        started_at=observed_at, engines=[snap], engines_excluded=[], opt_in_selected=[],
        input_hashes=input_hashes(inputs), repeats=1, max_attempts=1, key_pages=[], key_content=[],
        mention_terms=list(mention_terms), thresholds=number.threshold_values(), planned_slots=1,
        cap_usd="0", transport=records.MANUAL, run_kind=records.MANUAL)
    writer = RunWriter(root, manifest, inputs, secrets=secrets)
    raw_sha, raw_path = writer.put_raw(text_bytes, "txt")
    attachments = []
    if screenshot_bytes is not None:
        sha, rel = writer.put_raw(screenshot_bytes, "bin")
        attachments.append({"role": "screenshot", "raw_sha256": sha, "raw_path": rel})
    cap = records.capture(
        manifest, snap, prompts_doc["prompts"][0], 0, 1, started_at=observed_at, completed_at=observed_at,
        status="ok", request_sha256=None, raw_sha256=raw_sha, raw_path=raw_path, answer_text=answer,
        citations=citations, cost_estimate_usd="0", created_at=created_at, access=records.MANUAL,
        attachments=attachments)
    writer.append(cap)
    for rec in claims_for_run(manifest, [cap], facts_doc, created_at):
        writer.append(rec)
    load_valid_run(writer.run_dir, secrets)
    return writer.run_dir
