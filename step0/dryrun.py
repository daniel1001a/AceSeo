"""Step 0 dry run: build requests and a cost estimate, send nothing.

    python3 -m step0.dryrun [--opt-in perplexity] [--cap-usd 1.00] [--out DIR]

Without --out it prints the summary only. With --out it writes plan.json and
requests/<sha256>.json into DIR, which must not exist yet. Nothing is written
when the estimate is over the cap or no engine can be built.
"""

import argparse
import os
import sys

from . import cost, request_builder
from .canonical import canonical_bytes, strict_load_path

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

EXIT_OK = 0
EXIT_OVER_BUDGET = 2
EXIT_NO_ENGINE = 3
EXIT_OUT_EXISTS = 4


def run(data_dir=DATA_DIR, opt_in=(), cap_usd="1.00", out_dir=None, stdout=None):
    stdout = stdout or sys.stdout
    engines_doc = strict_load_path(os.path.join(data_dir, "engines.json"))
    prices_doc = strict_load_path(os.path.join(data_dir, "prices.json"))
    prompts_doc = strict_load_path(os.path.join(data_dir, "prompts.json"))

    prompts = request_builder.load_prompts(prompts_doc)
    plan, request_files = request_builder.build_plan(
        engines_doc, prompts, prompts_doc["repeats"], opt_in)
    estimate = cost.estimate(plan["slots"], engines_doc, prices_doc, cap_usd)
    plan["prompts"] = [{k: p[k] for k in ("prompt_id", "type", "lang", "text", "prompt_sha256")}
                       for p in prompts]
    plan["cost_estimate"] = estimate
    plan["sent"] = 0

    _print_summary(plan, stdout)

    if not plan["slots"]:
        print("no engine is buildable; nothing written", file=stdout)
        return EXIT_NO_ENGINE
    if estimate["status"] == "over_budget":
        print("over budget; nothing written", file=stdout)
        return EXIT_OVER_BUDGET
    if out_dir is not None:
        if os.path.exists(out_dir):
            print("output directory already exists: %s; nothing written" % out_dir, file=stdout)
            return EXIT_OUT_EXISTS
        req_dir = os.path.join(out_dir, "requests")
        os.makedirs(req_dir)
        for digest in sorted(request_files):
            with open(os.path.join(req_dir, digest + ".json"), "wb") as f:
                f.write(request_files[digest])
        with open(os.path.join(out_dir, "plan.json"), "wb") as f:
            f.write(canonical_bytes(plan) + b"\n")
        print("wrote %d request files and plan.json to %s" % (len(request_files), out_dir), file=stdout)
    return EXIT_OK


def _print_summary(plan, out):
    for e in plan["engines"]:
        n = sum(1 for s in plan["slots"] if s["engine"] == e["engine"])
        print("engine %-11s %-26s slots=%d" % (e["engine"], e["status"], n), file=out)
    est = plan["cost_estimate"]
    for row in est["engines"]:
        print("cost   %-11s n=%d per_call=%s search=%s total=%s upper_search=%s" % (
            row["engine"], row["n_slots"], row["per_call_total_usd"], row["search_fee_usd"],
            row["total_usd"], row["search_fee_upper_usd"] or "unbounded"), file=out)
    print("total  %s USD (Estimated tokens, Published prices), cap %s: %s" % (
        est["total_usd"], est["cap_usd"], est["status"]), file=out)
    if est["search_fee_unbounded_engines"]:
        print("note   no documented per-call search cap for: %s; the cap check assumes %d search(es) per call" % (
            ", ".join(est["search_fee_unbounded_engines"]),
            est["token_assumptions"]["searches_per_call"]), file=out)
    print("sent   0 requests (dry run; no network, no API keys read)", file=out)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m step0.dryrun", description=__doc__.splitlines()[0])
    parser.add_argument("--opt-in", action="append", default=[], metavar="ENGINE")
    parser.add_argument("--cap-usd", default="1.00")
    parser.add_argument("--out", default=None)
    parser.add_argument("--data-dir", default=DATA_DIR)
    args = parser.parse_args(argv)
    return run(args.data_dir, args.opt_in, args.cap_usd, args.out)


if __name__ == "__main__":
    sys.exit(main())
