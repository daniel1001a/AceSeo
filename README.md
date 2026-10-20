# AceSeo

Check what AI answer engines say about your site, and get a recommendation you
can trace back to the evidence.

AceSeo asks the official APIs of AI models with web search (OpenAI,
Anthropic, and Perplexity if you opt in) a set of questions about your site,
checks your key pages the way a crawler would, and compares every answer
against a facts file you control. It then applies a fixed cascade of rules and
writes a report in which every number shows its sample size and the ids of the
records it was computed from.

What makes it different:

- **Official APIs only.** No scraping of consumer apps, no logged-in surfaces.
  An engine is called only if its API terms were read and recorded as allowing
  this use (`step0/data/engines.json`). Surfaces with no API, such as Google AI
  Overviews, can be recorded by hand and are kept out of every rate.
- **Facts come from code and files, not from a model.** A claim is matched to
  a fact by rules (`geo/claims.py`), and the verdict says which rule decided it.
- **A traceable claim ledger.** Every raw response is stored by its SHA-256.
  Every capture, claim and decision record has a deterministic id, and the run
  is re-validated after each stage.
- **Rules first, no score.** The recommendation comes from a fixed rule cascade
  (R1, R0, R2, R3, R4). Below-minimum samples are reported as insufficient and
  never decide anything.
- **Python standard library only.** No dependencies to install.

It does not change your site, does not produce a visibility score, and does not
need an account anywhere except the API keys you already have.

Status (2026-10-20): the pipeline has run once against real Anthropic API
responses (`--repeats 1`, one site), covered by tests replaying those
responses as fixtures. OpenAI has not been verified against a real response
yet (the account had no credit; see `PROGRESS.md` Step 13). Perplexity is
still offline-only. Thresholds remain `provisional`. See `READY_FOR_LIVE.md`
for what is still `unverified` or `Estimated`.

## Install

Python 3.9 or newer. Nothing else.

```
git clone <this repo> aceseo
cd aceseo
python3 -m unittest discover -s tests -q
```

## See a complete example first

`examples/synthetic/` holds a SYNTHETIC run and its report, built offline with
fake keys. Read `examples/synthetic/README.md` for what is in a run directory,
then:

```
python3 -m geo.cli ledger examples/synthetic/runs/run_20261019T210001Z_6f7d91
python3 -m geo.cli report examples/synthetic/runs/run_20261019T210001Z_6f7d91
```

## Your inputs

You need two files. Templates for a site called "Example Co" are in
`examples/minimal/`. Without `--prompts` and `--facts` the tool uses the
BoardFlight files it was built with, which are not about your site.

### prompts.json

The questions to ask. `{BRAND}` and `{DOMAIN}` are filled from
`substitutions`. `prompt_id` is `p_` plus lowercase letters, digits or `_`.

```json
{
  "schema_version": "step0-prompts/v1",
  "source": "my prompts",
  "substitutions": {"BRAND": "Example Co", "DOMAIN": "www.example.com"},
  "prompts": [
    {"prompt_id": "p_01", "type": "B", "lang": "en", "template": "What is {BRAND}?"},
    {"prompt_id": "p_02", "type": "B", "lang": "en", "template": "Is {DOMAIN} a legitimate and active website?"},
    {"prompt_id": "p_03", "type": "B", "lang": "en", "template": "Is {BRAND} free to use?"}
  ]
}
```

### facts.json

What is true about your site. The minimum the tool needs is the site name, its
hostnames, and a list of facts with unique keys:

```json
{
  "schema_version": "1.0.0",
  "site": {
    "name": "Example Co",
    "canonical_origin": "https://www.example.com",
    "hosts": ["example.com", "www.example.com"]
  },
  "facts": [
    {"key": "jsonld.organization.same_as", "value": ["https://github.com/example"], "value_type": "string_list"},
    {"key": "llms.offer.is_free", "value": true, "value_type": "boolean"},
    {"key": "site_status", "value": "live", "value_type": "enum"}
  ]
}
```

The rule matcher (version 1) compares answers against these fact keys only:

| Fact key | Value | Matches sentences like |
|---|---|---|
| `site_status` | `"live"`, `"redirect_only"`, `"error"` or `"unreachable"` | "X is no longer operating", "X is live" |
| `llms.offer.is_free` | `true` or `false` | "X is free to use", "X requires a paid subscription" |
| `jsonld.organization.same_as` | list of profile URLs (`[]` for none) | "X has no social media profiles", "X has a GitHub" |
| `llms.coverage.airport_count` | integer | "X covers 33 US airports" (BoardFlight specific) |
| `llms.data.uses_live_queue_data` | `true` or `false` | "X uses real-time TSA wait times" (BoardFlight specific) |

A sentence is decided only when it names the site (by `site.name` or a host in
`site.hosts`) and hits exactly one topic. Anything else becomes `needs_review`
or `unsupported` and is listed in the report, not counted. Other fact keys are
kept in the run's copy of the facts file but no claim refers to them yet.

Add `"prior_values": [{"value": ..., "valid_until": "...", "source": {...}}]`
to a fact if an old value is still quoted; an answer repeating it is then
`outdated` instead of `contradicted`. `design/w3-facts-schema.md` describes
the full schema (sources, snapshots, hashes) that `geo.facts.validate_facts`
checks; the collect command only checks the minimum above.

## Plan a run (free, nothing sent)

```
python3 -m geo.cli collect \
  --prompts examples/minimal/prompts.json --facts examples/minimal/facts.json \
  --mention-term "Example Co" --mention-term example.com \
  --key-page https://www.example.com/ \
  --repeats 3 --cap-usd 1
```

This prints the engines that will be called, the ones the terms gate skips and
why, the number of requests, and the Estimated cost. It writes nothing. Add
`--json` for a machine-readable plan.

Options you will use:

- `--mention-term` (repeatable, required): brand names and domains that count
  as a mention of your site.
- `--key-page URL` (repeatable): pages to check for status, redirects,
  `noindex`, robots.txt rules for AI crawlers, and a main-content heuristic.
- `--key-content URL TEXT` (repeatable): text that must appear in the raw HTML
  of URL.
- `--repeats N`: how often each prompt is asked per engine. Rates need at
  least 3 ok answers per prompt, so `--repeats 1` can only ever end in
  "insufficient evidence".
- `--opt-in perplexity`: also call Perplexity.
- `--report-out FILE`: write the report to FILE as well.

## Run it live (costs money)

Keys are read from the environment only, only for engines that pass the terms
gate, and only when `--live` is given. They are never written to disk; the run
writer refuses any file that contains one.

| Engine | Model (`step0/data/engines.json`) | Environment variable | Called |
|---|---|---|---|
| OpenAI | gpt-5-mini | `OPENAI_API_KEY` | by default |
| Anthropic | claude-haiku-5-5 | `ANTHROPIC_API_KEY` | by default |
| Perplexity | perplexity/sonar | `PERPLEXITY_API_KEY` | with `--opt-in perplexity` |

```
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
python3 -m geo.cli collect <same options as the plan> --report-out runs/report.md --live
```

Progress is printed per request on stderr. The run directory goes under
`runs/` (ignored by git) and its path is printed at the end.

## Cost and budget

Prices are copied from the providers' pricing pages into
`step0/data/prices.json`, each with its source URL and retrieval date, and
labelled `Published`. Every cost the tool computes is labelled `Estimated`: it
assumes 22000 input and 800 output tokens and two searches per call. Those
are the rounded-up means of the ten Anthropic answers in the first live run
(2026-10-20); OpenAI and Perplexity token counts have not been measured yet.

With the shipped prices (retrieved 2026-10-19), OpenAI and Anthropic, 10
prompts:

| Repeats | Requests | Expected | Upper search bound |
|---|---|---|---|
| 1 | 20 | $0.497 | $0.597 |
| 3 | 60 | $1.491 | $1.791 |

`--cap-usd` is required. The run refuses to start if the expected cost of the
first attempts exceeds it. While running, every attempt (retries included,
`--max-attempts`, default 2) adds its expected per-call estimate to a running
total, and a request that would push the total past the cap is not sent and is
recorded as skipped (`budget_cap`). The upper search bound is not used by the
cap, so set the cap with it in mind. Your provider's bill is the real number;
compare it after the first run.

## What the report says

The rules run in this order, and the first that fires decides:

| Rule | Fires when | Recommendation |
|---|---|---|
| R1 | a blocking check failed on a key page | SEO first |
| R0 | a key page could not be checked, or fewer than 2 vendors have an engine with at least 6 ok answers | Insufficient evidence |
| R2 | the same fact is contradicted (or outdated) in at least 2 answers | GEO first: fix facts |
| R3 | in at least 2 vendors, every engine cites the site in under 20% of its ok answers | GEO first: content |
| R4 | none of the above | No action |

All thresholds are in `geo/number.py`, are labelled provisional, and are copied
into every run's manifest and decision record. R1 and R3 are reported as
hypotheses to test, not as proven causes.

The report lists: the recommendation and the rule that fired, every rule's
result with the ids it read, every measurement with its `n` and evidence ids,
independence groups (answers from one vendor are not independent of each
other), contradicted claims with the fact they contradict, everything excluded
or skipped, and what was not checked. Results describe API-model behaviour,
not what users of consumer apps see.

## Other commands

```
python3 -m geo.cli report RUN_DIR        # re-render the report of a run
python3 -m geo.cli ledger RUN_DIR        # every capture and claim, with ids
python3 -m geo.cli import-manual ANSWER.txt --surface google-aio \
  --query "what is example co" --observed-at 2026-10-20T09:30:00Z \
  --mention-term "Example Co" --facts examples/minimal/facts.json \
  [--screenshot shot.png] [--cite https://www.example.com/]
python3 -m geo.cli export-fixtures RUN_DIR   # live run -> redacted test fixtures
```

`import-manual` stores an answer you copied by hand from a surface with no API
as its own run. Its claims get evidence ids like any other, but a manual run
never enters a rate or a decision.

Every command refuses with `refused: <reason>` and exit code 2 when an input
is wrong, a run does not validate, or a file it would write already exists.

## Use it from Claude Code

`skills/aceseo/` is a Claude Code skill that walks an agent through
writing the inputs, planning, running (only after you confirm the cost) and
explaining the report. Copy the folder into `.claude/skills/` of this
repository, or into `~/.claude/skills/` to have it everywhere, then ask
Claude Code something like "check what AI search says about my site". The
skill runs the commands above; it never asks for your keys in the chat.

## Layout

- `geo/`: the pipeline (`cli.py` is the entry point).
- `step0/data/`: engines with their terms status, prices with sources, the
  BoardFlight prompts.
- `design/`, `research/`: the data model, facts schema, API terms research and
  test plan the code follows.
- `examples/`: input templates and the SYNTHETIC example run.
- `skills/aceseo/`: a Claude Code skill that drives this tool.
- `PROGRESS.md`, `READY_FOR_LIVE.md`: build log and live-run checklist.

## License

MIT. See `LICENSE`.
