# Ready for live: pre-flight checklist

Everything up to this point has run offline, with SYNTHETIC provider bodies
and fake keys (PROGRESS.md Steps 1 to 7). This file is what to check before
the first real `--live` run, which sends real HTTP requests and spends real
money. Nothing in this repo reads a real key or sends a real request unless
`--live` is passed explicitly on the command line.

## 1. Environment variables

`geo/cli.py` reads keys only from the process environment, only for engines
that pass the terms gate (`terms_status` in step0/data/engines.json), and
only when `--live` is given:

| Engine | Environment variable |
|---|---|
| anthropic | `ANTHROPIC_API_KEY` |
| openai | `OPENAI_API_KEY` |

perplexity and xai have no entry in `KEY_ENV` (`geo/cli.py`): xai's
`terms_status` is `unverified` (its request shape is also unverified, so it
cannot be sent at all) and perplexity requires `--opt-in perplexity` even
once verified-allowed. Do not add either to the first live run.

## 2. Estimated cost (dry run, SYNTHETIC token assumptions)

Computed by `collect.collect(send=False)` against the real
`step0/data/{engines,prices}.json`, engines anthropic + openai only (xai and
perplexity skipped by the terms gate), `max_attempts=2`:

| Sendable slots | Prompts x repeats x engines | First-attempt estimate | Upper bound (with one retry each) |
|---|---|---|---|
| 60 | 10 x 3 x 2 | $0.648 | $1.248 |
| 90 | 9 x 5 x 2 | $0.972 | $1.872 |

These numbers carry the "Estimated" label from `geo/cost.py`: token counts
per call (1000 in, 500 out, 1 search) are planning assumptions
(`step0/data/prices.json: token_assumptions`, PLAN A8), not measured from a
real call. Real cost can differ once real answers come back. `--cap-usd`
refuses to send if the first-attempt estimate exceeds it; it does not cap
the upper bound, so leave headroom for retries.

## 3. How to start with `--live`

```
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
python3 -m geo.cli collect \
  --cap-usd 1 \
  --mention-term BoardFlight --mention-term boardflight.com \
  --key-page https://www.boardflight.com/ \
  --repeats 1 \
  --live
```

Without `--live` (the default) the same command only prints the dry-run plan
and writes nothing. `--live` builds the plan first, refuses if any required
key is missing from the environment, refuses if the estimate exceeds
`--cap-usd`, and only then opens `UrllibTransport` and writes a run
directory under `--out` (default `runs/`).

After a live run finishes, render its decision with:

```
python3 -m geo.cli report RUN_DIR
```

This reads no key and sends nothing; it refuses (exit code 2) if the run
does not validate or has no decision yet.

## 4. Fields still labelled unverified or Estimated

These are not blockers; they are things the first live run's output will
still carry as caveats, and the report and manifest say so:

- `crawler_token_status: "unverified"` on every AI-crawler robots.txt check
  except the wildcard `*` rule (`geo/pagechecks.py`). The crawler token list
  (GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot, PerplexityBot,
  Google-Extended) is from general knowledge, not a verified source.
- `xai.terms_status = "unverified"` and `xai.request_shape.status =
  "unverified"` in `step0/data/engines.json`. xai is excluded from every run
  until both are resolved.
- Every per-call cost estimate carries `label: "Estimated"`
  (`geo/cost.py`): the token and search-count assumptions are planning
  inputs, not measured. Prices themselves are `label: "Published"` with a
  cited source URL, retrieved 2026-10-19.
- `number.THRESHOLDS["*"]["status"] = "provisional"` (all six thresholds;
  PROGRESS.md "Threshold status"). The decision record and every report
  state this; see item 5.
- `report.OUTCOME_TEXT` recommendation sentences: draft wording, each one
  followed by "(provisional wording)" in the rendered report
  (`geo/report.py`).
- `min_para_chars_status: "placeholder"` (`MIN_PARA_CHARS` in
  `geo/pagechecks.py`), unrelated to the decision thresholds above: the
  minimum paragraph length used by the main-content check.

## 5. Recommended first live run

- Engines: anthropic and openai only (the only two with a verified terms
  status and a verified request shape). Do not pass `--opt-in` for
  perplexity or xai.
- Budget: `--cap-usd 1`, which at `--repeats 1` with the 10 BoardFlight
  prompts (10 x 1 x 2 = 20 sendable slots) stays well under the 60-slot
  estimate above.
- Key pages: the BoardFlight home page and the JFK airport page
  (`tests/geo_fixtures.py: KEY_PAGES`), so page checks and the decision
  have real evidence for R1.
- After it finishes: run `python3 -m geo.cli report RUN_DIR`, read the
  recommendation and the Measurements block, and compare the real n's and
  citation rates against the provisional thresholds in PROGRESS.md before
  trusting an R0 or R3 outcome on a second run.
- Do not raise the cap or add more engines until this first run's output
  has been read end to end by the lead.
