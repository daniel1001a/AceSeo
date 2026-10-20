"""Offline end-to-end dry run (PLAN Step 7).

page checks -> captures -> claims -> decision -> report, all in one run
directory. Only a fixture transport and a FixtureFetcher are accepted, so this
module never opens a socket. The run is validated after every stage; the
report is rendered only from a run that validates.
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
    held = {}

    def on_start(writer):
        held["writer"] = writer
        PageCheckRunner(writer, fetcher, clock).run()

    run_dir = collect.collect(
        engines_doc, prices_doc, prompts, facts_bytes, root=root, repeats=repeats, cap_usd=cap_usd,
        key_pages=key_pages, mention_terms=mention_terms, key_content=key_content, thresholds=thresholds,
        opt_in_selected=opt_in_selected, max_attempts=max_attempts, send=True, transport=transport,
        api_keys=api_keys, clock=clock, sleep=sleep, on_start=on_start)
    writer = held["writer"]
    secrets = tuple(v for v in (api_keys or {}).values() if v)

    index = load_valid_run(run_dir, secrets)
    facts_doc = strict_load_path(os.path.join(run_dir, "inputs", "facts.json"))
    for rec in claims_for_run(index.manifest, index.of_kind("capture"), facts_doc, clock()):
        writer.append(rec)

    index = load_valid_run(run_dir, secrets)
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
