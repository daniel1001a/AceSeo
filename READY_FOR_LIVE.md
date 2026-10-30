# Ready for live: pre-flight checklist

Everything so far has run offline, with SYNTHETIC provider bodies and fake
keys. This file lists what to check before the first real `--live` run, which
sends real HTTP requests and spends real money. Nothing in this repo reads a
real key or sends a real request unless `--live` is passed on the command line.

Status (2026-10-20): first live run done, `run_20261020T142935Z_74e3cd`
(`--repeats 1`). Anthropic answered 10 of 10. OpenAI refused every request
with HTTP 429 `insufficient_quota` (the account had no credit), so no OpenAI
answer has been recorded. Fixtures are in `tests/fixtures/live/`. Results and
the changes they caused are in PROGRESS.md Step 13.

## 1. Environment variables

`geo/cli.py` reads keys only from the process environment, only for engines
that pass the terms gate (`terms_status` in step0/data/engines.json), and
only when `--live` is given:

| Engine | Environment variable | Called by default |
|---|---|---|
| anthropic | `ANTHROPIC_API_KEY` | yes |
| openai | `OPENAI_API_KEY` | yes |
| perplexity | `PERPLEXITY_API_KEY` | only with `--opt-in perplexity` |

xai has no entry in `KEY_ENV`: its `terms_status` and request shape are
`unverified`, so the terms gate skips it. If a required key is missing,
`--live` refuses before writing anything and names the variable.

## 2. Estimated cost (dry run)

From `python3 -m geo.cli collect --prompts step0/data/prompts.json --facts
design/boardflight.facts.sample.json --cap-usd 1 --mention-term BoardFlight
--repeats N` against the real `step0/data/{engines,prices}.json`, engines
anthropic + openai:

| Sendable slots | Prompts x repeats x engines | First attempts, expected | First attempts, upper search bound |
|---|---|---|---|
| 20 | 10 x 1 x 2 | $0.497 | $0.597 |
| 60 | 10 x 3 x 2 | $1.491 | $1.791 |

Both columns are Estimated (`geo/cost.py`). The per-call token counts
(22000 in, 800 out) and the search count (2) in
`step0/data/prices.json: token_assumptions` are the rounded-up means of the
ten Anthropic answers in the first live run; OpenAI's are not measured yet.
The old assumptions (1000 in, 500 out, 1 search) gave $0.1035 for those ten
calls against $0.1958 computed from their reported usage. The upper column
uses the documented maximum searches per call for anthropic (3), and never
less than the expected count for openai. Neither column includes retries: with
`--max-attempts 2` a failed slot is sent once more. `--cap-usd` refuses to
start if the expected first-attempt estimate exceeds it, and the collector
skips further slots once the running Estimated spend would pass the cap.

## 3. Running live

```
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
python3 -m geo.cli collect \
  --prompts step0/data/prompts.json --facts design/boardflight.facts.sample.json \
  --cap-usd 1 --repeats 1 \
  --mention-term BoardFlight --mention-term boardflight.com \
  --key-page https://www.boardflight.com/ \
  --key-page https://www.boardflight.com/airport/jfk \
  --key-page https://www.boardflight.com/llms.txt \
  --report-out runs/first-live-report.md \
  --live
```

Run it once without `--live` first: the dry run prints the engines, slots and
Estimated cost, and writes nothing.

`--live` runs `pipeline.run_live`, the same stages as the offline pipeline:

1. page checks on each `--key-page` through `geo/fetch.py: UrllibFetcher`
   (plain GET, no cookies, redirects recorded hop by hop, bodies cut at 5 MiB
   with an `x-geo-evidence-truncated` header),
2. captures through `collect.UrllibTransport`, with one progress line per
   attempt on stderr,
3. claims from the rule matcher,
4. the decision,
5. the report, printed to stdout or written to `--report-out`.

The run is validated after each stage. The run directory path is printed to
stderr at the end. `python3 -m geo.cli report RUN_DIR` re-renders it later,
and `python3 -m geo.cli ledger RUN_DIR` lists every capture and claim.

## 4. Recording fixtures from the first run

```
python3 -m geo.cli export-fixtures runs/<run_id>
```

This writes `tests/fixtures/live/<engine>/<sha256>.json` and `index.json`.
Identifier fields (`id`, `user`, `safety_identifier`, `prompt_cache_key`,
`metadata`, `previous_response_id`) are replaced with `"redacted"`, and the
export refuses if that changes how the adapter parses a body. Read every file
before committing. `tests/test_live_fixtures.py` then replays them on every
test run. It skips while `index.json` is absent.

Done for the first run. The redaction leaves `encrypted_content`, `signature`
and `tool_use_id` in the Anthropic bodies: opaque provider values, not account
identifiers, but check you are comfortable publishing them. The OpenAI entries
in `index.json` were edited by hand to expect `quota_exhausted`, because the
run itself recorded the old `rate_limited`; a fresh export of that run would
refuse. `FIELD_STATUS` marks every Anthropic field seen in the run as `live`.

## 5. Fields still labelled unverified or Estimated

These are not blockers. The first live run's output will still carry them as
caveats, and the report and manifest say so:

- `crawler_token_status: "unverified"` on every AI-crawler robots.txt check
  except the wildcard `*` rule (`geo/pagechecks.py`). The crawler token list
  (GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot, PerplexityBot,
  Google-Extended) is from general knowledge, not a verified source.
- `xai.terms_status = "unverified"` and `xai.request_shape.status =
  "unverified"` in `step0/data/engines.json`. xai is excluded from every run
  until both are resolved.
- Adapter fields marked `unverified` or `documented` in `FIELD_STATUS`
  (`geo/adapters.py`): every OpenAI success field (no OpenAI answer yet), all
  of Perplexity, and Anthropic's refusal, `pause_turn` and tool error shapes.
- Every per-call cost estimate carries `label: "Estimated"`. Prices are
  `label: "Published"` with a cited source URL, retrieved 2026-10-19.
- `number.THRESHOLDS["*"]["status"] = "provisional"` (PROGRESS.md
  "Threshold status").
- Recommendation text ends with "(draft wording, not yet reviewed against
  a live run)" (`report.PROVISIONAL_WORDING_NOTE`) for every outcome except
  `insufficient_evidence`, the only one a live run has produced so far.
- `min_para_chars_status: "placeholder"` (`MIN_PARA_CHARS` in
  `geo/pagechecks.py`), the minimum paragraph length used by the
  main-content check.

## 6. Recommended first live run

- Engines: anthropic and openai only. Add `--opt-in perplexity` (with
  `PERPLEXITY_API_KEY`) only for a second run, once the first has been read.
- Budget: `--repeats 1` (20 slots, $0.497 expected) fits `--cap-usd 1`.
  A `--repeats 1` run cannot get past R0: each per-prompt citation rate needs
  `N_MIN_REPEATS` (3) ok captures, so every engine's pooled rate is
  Insufficient and R0 fires with `engines_below_minimum` (unless R1 fires
  first on a page check). It still records real responses, page checks and
  claims. `--repeats 3` (60 slots, $1.491 expected, $1.791 upper) is the
  smallest run that can reach R2 to R4 and needs `--cap-usd 2` or more.
- Key pages: the three above, so page checks give R1 real evidence.
- Afterwards: read the report and the ledger, export fixtures (section 4),
  and compare the real n's and rates against the provisional thresholds
  before trusting an R0 or R3 outcome.
