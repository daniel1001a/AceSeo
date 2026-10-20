#!/usr/bin/env python3
"""Rebuild the SYNTHETIC example run and report under examples/synthetic/.

  python3 examples/make_example.py [OUT_DIR]

Runs the same offline pipeline the tests use: page checks on the RECORDED
BoardFlight pages behind SYNTHETIC status lines, and SYNTHETIC OpenAI and
Anthropic response bodies in which every answer says "BoardFlight covers 40 US
airports." (the facts file says 33). Keys are fake and nothing is sent. The
output is deterministic: tests/test_example.py rebuilds it and compares.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from geo import pipeline  # noqa: E402
from geo.collect import FixtureTransport  # noqa: E402
from tests import geo_fixtures as fx  # noqa: E402
from tests.test_adapters import ANT, FACTS, KEYS, OAI, Clock, ant_body, oai_body, prompts  # noqa: E402
from tests.test_decide import C_TEXT, routes_pass  # noqa: E402
from tests.test_pagechecks import JFK_KEY  # noqa: E402

PROMPT_IDS = ("p_01", "p_02")
REPEATS = 3
DEFAULT_OUT = os.path.join(ROOT, "examples", "synthetic")


def build(out_dir):
    """-> pipeline.Result. out_dir may exist, but not its report.md or runs/."""
    for name in ("report.md", "runs"):
        if os.path.exists(os.path.join(out_dir, name)):
            raise FileExistsError(os.path.join(out_dir, name))
    slots = len(PROMPT_IDS) * REPEATS
    responses = {OAI: [(200, oai_body(text=C_TEXT))] * slots, ANT: [(200, ant_body(text=C_TEXT))] * slots}
    return pipeline.run_offline(
        fx.engines_doc({}), fx.load("prices.json"), prompts(PROMPT_IDS), FACTS,
        root=os.path.join(out_dir, "runs"), repeats=REPEATS, cap_usd="5",
        key_pages=fx.KEY_PAGES, mention_terms=fx.MENTION_TERMS, key_content=(JFK_KEY,),
        transport=FixtureTransport(responses), fetcher=pipeline.FixtureFetcher(routes_pass()),
        api_keys=KEYS, clock=Clock(), out_path=os.path.join(out_dir, "report.md"))


def main(argv):
    out = argv[1] if len(argv) > 1 else DEFAULT_OUT
    res = build(out)
    print("report: %s" % os.path.join(out, "report.md"))
    print("run directory: %s" % res.run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
