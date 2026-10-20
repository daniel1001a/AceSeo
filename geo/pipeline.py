"""End-to-end run (PLAN Step 7): page checks -> captures -> claims -> decision -> report.

Everything lands in one run directory. The run is validated after every stage;
the report is rendered only from a run that validates.

run_offline accepts only a fixture transport and a FixtureFetcher, so it never
opens a socket. run_live accepts only a live transport; it is what
`geo collect --live` calls.
"""

import os
from collections import namedtuple

from . import collect, decide, render
from .canonical import strict_load_path
from .claims import claims_for_run
from .pagechecks import FixtureFetcher, PageCheckRunner
from .report import build_report
from .validate import load_valid_run

Result = namedtuple("Result", "run_dir decision_id text")


class PipelineError(ValueError):
    pass


def run_offline(engines_doc, prices_doc, prompts, facts_bytes, *, root, repeats, cap_usd, key_pages,
                mention_terms, transport, fetcher, api_keys, clock, key_content=(), thresholds=None,
                opt_in_selected=(), max_attempts=2, sleep=lambda s: None, out_path=None):
    """-> Result(run_dir, decision_id, text). out_path, if given, must not exist."""
    if getattr(transport, "kind", None) != "fixture":
        raise PipelineError("the offline pipeline needs a fixture transport")
    if not isinstance(fetcher, FixtureFetcher):
        raise PipelineError("the offline pipeline needs a FixtureFetcher")
    return _run(engines_doc, prices_doc, prompts, facts_bytes, root=root, repeats=repeats, cap_usd=cap_usd,
                key_pages=key_pages, mention_terms=mention_terms, transport=transport, fetcher=fetcher,
                api_keys=api_keys, clock=clock, key_content=key_content, thresholds=thresholds,
                opt_in_selected=opt_in_selected, max_attempts=max_attempts, sleep=sleep, out_path=out_path)


def run_live(engines_doc, prices_doc, prompts, facts_bytes, *, root, repeats, cap_usd, key_pages,
             mention_terms, transport, fetcher, api_keys, clock, key_content=(), thresholds=None,
             opt_in_selected=(), max_attempts=2, sleep=None, out_path=None, progress=None):
    """Same stages as run_offline, with a live transport. Sends real requests."""
    if getattr(transport, "kind", None) != "live":
        raise PipelineError("run_live needs a live transport")
    return _run(engines_doc, prices_doc, prompts, facts_bytes, root=root, repeats=repeats, cap_usd=cap_usd,
                key_pages=key_pages, mention_terms=mention_terms, transport=transport, fetcher=fetcher,
                api_keys=api_keys, clock=clock, key_content=key_content, thresholds=thresholds,
                opt_in_selected=opt_in_selected, max_attempts=max_attempts,
                sleep=sleep or collect.time.sleep, out_path=out_path, progress=progress)


def _note(progress, event, **fields):
    if progress is not None:
        progress(dict(fields, event=event))


def _run(engines_doc, prices_doc, prompts, facts_bytes, *, root, repeats, cap_usd, key_pages, mention_terms,
         transport, fetcher, api_keys, clock, key_content, thresholds, opt_in_selected, max_attempts, sleep,
         out_path, progress=None):
    held = {}

    def on_start(writer):
        held["writer"] = writer
        _note(progress, "page_checks", run_dir=writer.run_dir, urls=len(writer.manifest["key_pages"]))
        PageCheckRunner(writer, fetcher, clock).run()

    run_dir = collect.collect(
        engines_doc, prices_doc, prompts, facts_bytes, root=root, repeats=repeats, cap_usd=cap_usd,
        key_pages=key_pages, mention_terms=mention_terms, key_content=key_content, thresholds=thresholds,
        opt_in_selected=opt_in_selected, max_attempts=max_attempts, send=True, transport=transport,
        api_keys=api_keys, clock=clock, sleep=sleep, on_start=on_start, progress=progress)
    writer = held["writer"]
    secrets = tuple(v for v in (api_keys or {}).values() if v)

    index = load_valid_run(run_dir, secrets)
    _note(progress, "claims")
    facts_doc = strict_load_path(os.path.join(run_dir, "inputs", "facts.json"))
    for rec in claims_for_run(index.manifest, index.of_kind("capture"), facts_doc, clock()):
        writer.append(rec)

    index = load_valid_run(run_dir, secrets)
    _note(progress, "decision")
    dec = decide.decide(index, clock())
    writer.append(dec)

    index = load_valid_run(run_dir, secrets)
    report = build_report(index, dec["id"])
    if out_path is None:
        text = render.render_text(report, index)
    else:
        render.render(report, index, out_path)
        with open(out_path, encoding="utf-8") as f:
            text = f.read()
    return Result(run_dir, dec["id"], text)
