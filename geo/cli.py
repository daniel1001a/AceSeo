"""Command line entry: python3 -m geo.cli collect [--live] ... | report RUN_DIR [--out PATH]

Without --live it prints the dry-run plan (Estimated costs) and writes nothing.
With --live it reads API keys from the environment, only for the engines that
pass the terms gate, and sends real requests through UrllibTransport.
report renders the latest decision of a run that validates; it reads no keys
and sends nothing.
"""

import argparse
import json
import os
import sys

from . import collect, render
from . import report as report_mod
from .canonical import canonical_bytes, strict_load_path
from .validate import ValidationError, load_valid_run
from step0 import request_builder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "step0", "data")
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def main(argv=None, environ=None):
    p = argparse.ArgumentParser(prog="geo")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="plan (default) or send capture slots")
    c.add_argument("--engines", default=os.path.join(DATA, "engines.json"))
    c.add_argument("--prices", default=os.path.join(DATA, "prices.json"))
    c.add_argument("--prompts", default=os.path.join(DATA, "prompts.json"))
    c.add_argument("--facts", default=os.path.join(ROOT, "design", "boardflight.facts.sample.json"))
    c.add_argument("--out", default=os.path.join(ROOT, "runs"))
    c.add_argument("--repeats", type=int, default=3)
    c.add_argument("--max-attempts", type=int, default=2)
    c.add_argument("--cap-usd", required=True)
    c.add_argument("--opt-in", action="append", default=[])
    c.add_argument("--key-page", action="append", default=[])
    c.add_argument("--mention-term", action="append", required=True)
    c.add_argument("--live", action="store_true", help="send real requests (costs money)")
    r = sub.add_parser("report", help="render the latest decision of a run directory")
    r.add_argument("run_dir")
    r.add_argument("--out", help="write the report here (must not exist); default stdout")
    a = p.parse_args(argv)
    if a.cmd == "report":
        return report(a.run_dir, a.out)
    env = os.environ if environ is None else environ

    prompts = [{"prompt_id": x["prompt_id"], "text": x["text"]}
               for x in request_builder.load_prompts(strict_load_path(a.prompts))]
    engines_doc, prices = strict_load_path(a.engines), strict_load_path(a.prices)
    common = dict(root=a.out, repeats=a.repeats, cap_usd=a.cap_usd, key_pages=a.key_page,
                  mention_terms=a.mention_term, opt_in_selected=a.opt_in, max_attempts=a.max_attempts)
    facts = canonical_bytes(strict_load_path(a.facts))
    try:
        if not a.live:
            out = collect.collect(engines_doc, prices, prompts, facts, **common)
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0
        plan = collect.build_plan(engines_doc, prices, prompts, a.repeats, a.opt_in)
        keys = {}
        for s in plan.snapshots:
            name = KEY_ENV.get(s["engine"])
            if not name or not env.get(name):
                raise collect.CollectError("set %s for %s" % (name, s["engine"]))
            keys[s["engine"]] = env[name]
        run_dir = collect.collect(engines_doc, prices, prompts, facts, send=True,
                                  transport=collect.UrllibTransport(), api_keys=keys, **common)
        print(run_dir)
        return 0
    except collect.CollectError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


def report(run_dir, out):
    try:
        index = load_valid_run(run_dir)
        rep = report_mod.build_report(index, report_mod.latest_decision_id(index))
        if out:
            render.render(rep, index, out)
            print(out)
        else:
            sys.stdout.write(render.render_text(rep, index))
        return 0
    except ValidationError as e:
        print("refused: run does not validate: %s" % e, file=sys.stderr)
    except report_mod.ReportError as e:
        print("refused: %s" % e, file=sys.stderr)
    except render.RenderError as e:
        print("refused: %s" % e, file=sys.stderr)
    except FileExistsError as e:
        print("refused: %s exists" % e, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
