"""Command line entry: python3 -m geo.cli <command> ...

  collect          plan (default, writes nothing) or, with --live, run the full
                   pipeline: page checks, captures, claims, decision, report
  report RUN_DIR   render the latest decision of a run that validates
  ledger RUN_DIR   list the captures and claims of any run, manual runs included
  import-manual    store an answer copied by hand from a surface with no API
  export-fixtures  copy a live run's raw responses (redacted) into test fixtures
  propose-claims   store LLM-proposed claims beside a run (listed, never counted)
  confirm          turn a proposed claim into a match rule in your facts file
  init URL         draft facts.json and prompts.json from a site's public pages
  diff RUN_A RUN_B compare two runs: rates with n, verdicts, page checks

Only `collect --live` reads API keys (from the environment, only for engines
that pass the terms gate) and sends requests to AI engines. `init` fetches
two public pages of your site (home and /llms.txt). Everything else is offline.
"""

import argparse
import json
import os
import sys

from . import collect, diff, fixtures_export, manual, pipeline, proposals, render
from . import init as init_mod
from . import facts as facts_mod
from . import report as report_mod
from .canonical import StrictJSONError, canonical_bytes, strict_load_path
from .fetch import UrllibFetcher
from .validate import ValidationError, load_valid_run
from step0 import request_builder

DATA = os.path.join(os.path.dirname(os.path.abspath(request_builder.__file__)), "data")
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
           "perplexity": "PERPLEXITY_API_KEY"}


def _parser():
    p = argparse.ArgumentParser(prog="aceseo", description="Evidence-first AI answer checks for one site.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="plan (default) or run live (--live)")
    c.add_argument("--engines", default=os.path.join(DATA, "engines.json"))
    c.add_argument("--prices", default=os.path.join(DATA, "prices.json"))
    c.add_argument("--prompts", required=True, help="prompts.json (see examples/minimal)")
    c.add_argument("--facts", required=True, help="facts.json (see examples/minimal)")
    c.add_argument("--out", default="runs", help="runs root directory")
    c.add_argument("--repeats", type=int, default=3)
    c.add_argument("--max-attempts", type=int, default=2)
    c.add_argument("--cap-usd", required=True, help="refuse to start if the Estimated first-attempt cost exceeds this")
    c.add_argument("--opt-in", action="append", default=[], help="enable an opt-in engine (e.g. perplexity)")
    c.add_argument("--key-page", action="append", default=[], help="a page URL to check (repeatable)")
    c.add_argument("--key-content", nargs=2, action="append", default=[], metavar=("URL", "TEXT"),
                   help="text that must appear in the raw HTML of URL (repeatable)")
    c.add_argument("--mention-term", action="append", required=True, help="brand name or domain (repeatable)")
    c.add_argument("--json", action="store_true", help="print the dry-run plan as JSON")
    c.add_argument("--live", action="store_true", help="send real requests (costs money)")
    c.add_argument("--report-out", help="also write the report to this file (must not exist)")

    r = sub.add_parser("report", help="render the latest decision of a run directory")
    r.add_argument("run_dir")
    r.add_argument("--out", help="write the report here (must not exist); default stdout")

    lg = sub.add_parser("ledger", help="list the captures and claims of a run")
    lg.add_argument("run_dir")

    m = sub.add_parser("import-manual", help="store a hand-copied answer (e.g. Google AI Overviews) as evidence")
    m.add_argument("answer_file", help="UTF-8 text file holding the answer as shown")
    m.add_argument("--surface", required=True, help="slug for where it was seen, e.g. google-aio")
    m.add_argument("--query", required=True, help="the exact text that was typed into the surface")
    m.add_argument("--observed-at", required=True, help="when it was seen, UTC, e.g. 2026-10-20T09:30:00Z")
    m.add_argument("--screenshot", help="optional screenshot file, stored byte for byte")
    m.add_argument("--cite", action="append", default=[], help="a source URL the surface showed (repeatable)")
    m.add_argument("--vendor", help="vendor slug (default: first part of --surface)")
    m.add_argument("--facts", required=True)
    m.add_argument("--mention-term", action="append", required=True)
    m.add_argument("--out", default="runs")

    e = sub.add_parser("export-fixtures", help="copy a live run's raw responses into regression fixtures")
    e.add_argument("run_dir")
    e.add_argument("--dest", default=os.path.join("tests", "fixtures", "live"))

    pc = sub.add_parser("propose-claims", help="store LLM-proposed claims beside a run (never counted)")
    pc.add_argument("run_dir")
    pc.add_argument("--from", dest="from_file", required=True, help="proposals JSON (see geo/proposals.py)")

    cf = sub.add_parser("confirm", help="turn a proposed claim into a match rule in your facts file")
    cf.add_argument("run_dir")
    cf.add_argument("claim_id")
    cf.add_argument("--facts", required=True, help="your facts.json; edited in place")
    cf.add_argument("--phrase", required=True, help="words from the claim that assert the value")
    cf.add_argument("--value", help="boolean: true or false; enum: the value the phrase asserts")

    i = sub.add_parser("init", help="draft facts.json and prompts.json from a site's home page and llms.txt")
    i.add_argument("url")
    i.add_argument("--dir", default=".", help="where to write the drafts (existing files are kept)")

    d = sub.add_parser("diff", help="compare two runs: numbers, rule-claim verdicts, page checks")
    d.add_argument("run_a")
    d.add_argument("run_b")
    d.add_argument("--allow-input-change", action="store_true",
                   help="compare even if the facts or prompts files differ")
    return p


def main(argv=None, environ=None, clock=None, fetcher=None):
    a = _parser().parse_args(argv)
    env = os.environ if environ is None else environ
    try:
        if a.cmd == "report":
            return report(a.run_dir, a.out)
        if a.cmd == "ledger":
            return ledger(a.run_dir)
        if a.cmd == "import-manual":
            return import_manual(a, clock or collect.utc_now)
        if a.cmd == "propose-claims":
            return propose_claims(a, clock or collect.utc_now)
        if a.cmd == "confirm":
            return confirm(a)
        if a.cmd == "init":
            return init_cmd(a, fetcher)
        if a.cmd == "diff":
            sys.stdout.write(diff.diff_text(load_valid_run(a.run_a), load_valid_run(a.run_b),
                                            a.allow_input_change))
            return 0
        if a.cmd == "export-fixtures":
            entries = fixtures_export.export_fixtures(a.run_dir, a.dest)
            print("wrote %d fixtures and index.json to %s; read them before committing" % (len(entries), a.dest))
            return 0
        return collect_cmd(a, env)
    except (OSError, StrictJSONError, request_builder.ConfigError) as e:
        return _refuse(e)
    except (collect.CollectError, manual.ManualError, fixtures_export.ExportError, pipeline.PipelineError,
            proposals.ProposalError, init_mod.InitError, diff.DiffError, report_mod.ReportError) as e:
        return _refuse(e)
    except ValidationError as e:
        return _refuse("run does not validate: %s" % e)


def init_cmd(a, fetcher=None):
    facts_doc, prompts_doc, notes = init_mod.draft(a.url, fetcher or UrllibFetcher())
    for path, written in init_mod.write_drafts(a.dir, facts_doc, prompts_doc):
        print("%s %s" % ("wrote" if written else "kept existing", path))
    for n in notes:
        print("review: %s" % n)
    host = facts_doc["site"]["hosts"][0]
    print("next: aceseo collect --facts %s --prompts %s --mention-term %s --mention-term %s "
          "--key-page %s/ --cap-usd 1" % (os.path.join(a.dir, "facts.json"), os.path.join(a.dir, "prompts.json"),
                                            json.dumps(facts_doc["site"]["name"]), host,
                                            facts_doc["site"]["canonical_origin"]), file=sys.stderr)
    return 0


def _refuse(msg):
    print("refused: %s" % msg, file=sys.stderr)
    return 2


def load_facts(path):
    doc = strict_load_path(path)
    problems = facts_mod.runtime_problems(doc)
    if problems:
        raise collect.CollectError("%s: %s" % (path, "; ".join(problems)))
    return canonical_bytes(doc)


def _key_content(pairs):
    return [{"url": url, "expected": text, "fact_key": None} for url, text in pairs]


def collect_cmd(a, env):
    prompts = [{"prompt_id": x["prompt_id"], "text": x["text"]}
               for x in request_builder.load_prompts(strict_load_path(a.prompts))]
    engines_doc, prices = strict_load_path(a.engines), strict_load_path(a.prices)
    facts = load_facts(a.facts)
    common = dict(root=a.out, repeats=a.repeats, cap_usd=a.cap_usd, key_pages=a.key_page,
                  key_content=_key_content(a.key_content), mention_terms=a.mention_term,
                  opt_in_selected=a.opt_in, max_attempts=a.max_attempts)
    if not a.live:
        out = collect.collect(engines_doc, prices, prompts, facts, **common)
        if a.json:
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            sys.stdout.write(format_plan(out, a))
        return 0
    plan = collect.build_plan(engines_doc, prices, prompts, a.repeats, a.opt_in)
    keys = {}
    missing = [KEY_ENV.get(s["engine"], "a key for " + s["engine"]) for s in plan.snapshots
               if not env.get(KEY_ENV.get(s["engine"], ""))]
    if missing:
        raise collect.CollectError("set %s in the environment (keys are read only from env)" % ", ".join(missing))
    for s in plan.snapshots:
        keys[s["engine"]] = env[KEY_ENV[s["engine"]]]
    res = pipeline.run_live(engines_doc, prices, prompts, facts, transport=collect.UrllibTransport(),
                            fetcher=UrllibFetcher(), api_keys=keys, clock=collect.utc_now,
                            out_path=a.report_out, progress=print_progress, **common)
    if a.report_out:
        print("report: %s" % a.report_out)
    else:
        sys.stdout.write(res.text)
    print("run directory: %s" % res.run_dir, file=sys.stderr)
    return 0


def print_progress(ev):
    kind = ev["event"]
    if kind == "page_checks":
        line = "run %s: checking %d key page(s)" % (os.path.basename(ev["run_dir"]), ev["urls"])
    elif kind == "capture":
        line = "[%d/%d] %s %s r%d attempt %d: %s%s (spent, Estimated: $%s)" % (
            ev["done"], ev["total"], ev["engine"], ev["prompt_id"], ev["repeat_index"], ev["attempt"],
            ev["status"], " (%s)" % ev["error_class"] if ev.get("error_class") else "", ev["spent_estimate_usd"])
    elif kind == "skip":
        line = "skipped %s" % ", ".join("%s=%s" % (k, v) for k, v in sorted(ev.items()) if k != "event")
    elif kind == "claims":
        line = "matching claims against facts"
    elif kind == "decision":
        line = "applying decision rules"
    else:
        line = kind
    print(line, file=sys.stderr, flush=True)


def format_plan(out, a):
    est = out["estimate"]
    lines = ["Dry run: nothing is sent and nothing is written.", ""]
    lines.append("Engines that will be called: %s" % (", ".join(out["engines"]) or "none"))
    for x in out["engines_excluded"]:
        hint = "  (add --opt-in %s)" % x["engine"] if x["reason"] == "opt_in_not_selected" else ""
        lines.append("Not called: %s, %s (terms: %s)%s" % (x["engine"], x["reason"], x["terms_status"], hint))
    lines.append("Slots: %d to send (%d prompts x %d repeats x %d engines), %d skipped by the terms gate"
                 % (out["sendable_slots"], len({r["prompt_id"] for r in out["requests"]}) or 0, a.repeats,
                    len(out["engines"]), len(out["skipped_slots"])))
    lines.append("Retries: up to %d attempts per slot" % out["max_attempts"])
    lines.append("")
    lines.append("Cost (Estimated, from Published prices in the prices file):")
    for eng, pc in sorted(est["per_call"].items()):
        lines.append("  %s: $%s per call expected, up to $%s (%s)"
                     % (eng, pc["expected_usd"], pc["upper_usd"], pc["upper_basis"]))
    lines.append("  first attempts: $%s expected, up to $%s; cap $%s: %s"
                 % (est["first_attempts_usd"], est["upper_first_attempts_usd"], est["cap_usd"],
                    "within cap" if est["within_cap"] else "OVER CAP, --live would refuse"))
    lines.append("")
    lines.append("Key pages: %s" % (", ".join(a.key_page) or "none (page checks will be empty)"))
    lines.append("Mention terms: %s" % ", ".join(a.mention_term))
    lines.append("")
    lines.append("To send: add --live and export %s." % " and ".join(
        sorted(KEY_ENV[e] for e in out["engines"] if e in KEY_ENV)) if out["engines"] else "No engine can be called.")
    lines.append("Machine-readable plan: add --json.")
    return "\n".join(lines) + "\n"


def report(run_dir, out):
    try:
        index = load_valid_run(run_dir)
        if index.manifest["run_kind"] == "manual":
            return _refuse("%s is a manual run; it has no decision. Use: aceseo ledger %s" % (run_dir, run_dir))
        rep = report_mod.build_report(index, report_mod.latest_decision_id(index))
        if out:
            render.render(rep, index, out)
            print(out)
        else:
            sys.stdout.write(render.render_text(rep, index))
        return 0
    except ValidationError as e:
        return _refuse("run does not validate: %s" % e)
    except report_mod.ReportError as e:
        return _refuse(e)
    except render.RenderError as e:
        return _refuse(e)
    except FileExistsError as e:
        return _refuse("%s exists" % e)


def ledger(run_dir):
    index = load_valid_run(run_dir)
    m = index.manifest
    caps = sorted(index.of_kind("capture"), key=lambda c: (c["engine"], c["prompt_id"], c["repeat_index"], c["attempt"]))
    claims = index.of_kind("claim")
    lines = ["# Claim ledger: %s" % m["run_id"], "",
             "run_kind %s, transport %s, facts_sha256 %s" % (m["run_kind"], m["transport"], m["facts_sha256"]), ""]
    if m["run_kind"] == "manual":
        lines += ["Manual observations: copied by a person, not fetched through an API. They are listed here",
                  "and never counted in a rate or a decision.", ""]
    for cap in caps:
        lines.append("## %s" % cap["id"])
        lines.append("%s %s r%d attempt %d, access %s, status %s%s, completed %s" % (
            cap["engine"], cap["prompt_id"], cap["repeat_index"], cap["attempt"], cap["access"], cap["status"],
            " (%s)" % cap["error_class"] if cap["error_class"] else "", cap["completed_at"]))
        lines.append("prompt: %s" % cap["prompt_text"])
        lines.append("raw: %s" % cap["raw_path"])
        for att in cap["attachments"]:
            lines.append("%s: %s" % (att["role"], att["raw_path"]))
        for cit in cap["citations"]:
            lines.append("cited: %s" % cit["url"])
        mine = sorted((c for c in claims if c["capture_id"] == cap["id"]), key=lambda c: c["span_start"])
        for c in mine:
            fact = "" if c["fact_key"] is None else " fact %s=%s (%s)" % (
                c["fact_key"], json.dumps(c["fact_value_snapshot"], ensure_ascii=False), c["fact_ref"])
            lines.append("- %s %s [%s]%s: %s" % (c["id"], c["verdict"], c["verdict_basis"], fact, c["statement"]))
        if not mine and cap["status"] == "ok":
            lines.append("- no claim matched a fact")
        for c in sorted((c for c in index.proposals if c["capture_id"] == cap["id"]), key=lambda c: c["span_start"]):
            lines.append("- %s llm proposal, not counted%s: %s" % (
                c["id"], "" if c["fact_key"] is None else " (fact %s)" % c["fact_key"], c["statement"]))
        lines.append("")
    lines.append("%d capture(s), %d claim(s)%s." % (
        len(caps), len(claims), ", %d llm proposal(s)" % len(index.proposals) if index.proposals else ""))
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def import_manual(a, clock):
    with open(a.answer_file, "rb") as f:
        text = f.read()
    shot = None
    if a.screenshot:
        with open(a.screenshot, "rb") as f:
            shot = f.read()
    observed = a.observed_at
    if observed.endswith("Z") and "." not in observed:
        observed = observed[:-1] + ".000000Z"
    run_dir = manual.import_manual(
        a.out, text_bytes=text, surface=a.surface, query=a.query,
        facts_bytes=load_facts(a.facts), mention_terms=a.mention_term,
        observed_at=observed, created_at=clock(), screenshot_bytes=shot, source_urls=a.cite, vendor=a.vendor)
    print(run_dir)
    print("next: aceseo ledger %s" % run_dir, file=sys.stderr)
    return 0


def propose_claims(a, clock):
    doc = strict_load_path(a.from_file)
    built = proposals.import_proposals(a.run_dir, doc, clock())
    for rec, _, cmp in built:
        print("%s %s: %s" % (rec["id"], rec["fact_key"] or "no fact", rec["statement"]))
        print("  against the fact: %s" % cmp)
    print("%d proposal(s) stored in %s; they are listed, never counted." % (
        len(built), os.path.join(a.run_dir, "proposals.jsonl")))
    print("next: aceseo confirm %s CLAIM_ID --facts FACTS --phrase TEXT" % a.run_dir, file=sys.stderr)
    return 0


def confirm(a):
    spec, _ = proposals.confirm_proposal(a.run_dir, a.claim_id, a.facts, a.phrase, a.value)
    print("added %r to the match block of %s in %s" % (a.phrase, spec.fact_key, a.facts))
    print("the rule matcher now reads the statement as: %s (%s)" % (spec.verdict, spec.verdict_basis))
    print("this takes effect in the next run; the existing run is unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
