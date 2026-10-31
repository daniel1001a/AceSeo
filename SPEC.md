# SPEC.md: AceSeo v0.2

Status: agreed 2026-10-30. P1 to P4 implemented 2026-10-30 (section 6); P5 and P6 added 2026-10-30 (section 7); API P0 is deferred under the owner’s subscription-only instruction. Supersedes nothing in docs/PLAN.md; it sets the next
work after the MVP (docs/PROGRESS.md Steps 1 to 13).

## 1. Decisions

| # | Question | Decision | Trade-off accepted |
|---|---|---|---|
| D1 | How the claim ledger becomes generic | Hybrid: rules decide what they can; an LLM may only propose claims, labelled `matcher: "llm"`, and they never enter a decision rule until the user confirms the fact | Two code paths to maintain; extra cost per run when the LLM path is on |
| D2 | Target user | Solo developers and indie site owners | No multi-site, team or client-report features |
| D3 | Distribution | pip package plus the Claude Code skill; MCP server later | Less reach in non-Claude agent tools for now |
| D4 | Order | Real-data validation (P0) before tuning the matcher or thresholds | Needs the owner's OpenAI credit; P1 starts meanwhile because it does not depend on data |

## 2. Why (findings, 2026-10-30)

1. The claim ledger is the stated differentiator (research/w2-competitors.md),
   but it decides 5 fact keys, 2 of them BoardFlight specific
   (`geo/facts.py: MATCHED_KEYS`). Code-extracted facts exist only as
   `build_boardflight()`. Other users hand-write facts.json and get almost no
   decided claims. The first live run gave 8 claims, all `needs_review`.
2. A first run ends in `insufficient_evidence` unless the user has two vendor
   keys and pays for `--repeats 3`. OpenAI has never returned a real answer;
   thresholds are uncalibrated.
3. Not installable: pyproject packages `geo*` only, while `geo/cli.py`
   imports `step0` and reads `step0/data` and `design/` by repo-relative
   paths. No console command. Missing `--facts`/`--prompts` silently uses
   BoardFlight inputs. No CI.
4. One run is a snapshot. Nothing compares runs, so nothing shows whether a
   fix changed what engines say, and R1/R3 hypotheses are never tested.

## 3. Workstreams

### P0. Real-data validation (owner action, about $2)

- Add OpenAI credit. Run `--repeats 3` with anthropic + openai, cap $2.
- Export fixtures; move every OpenAI field seen to `live` in `FIELD_STATUS`.
- Compare real per-engine n and rates against `geo/number.py`; change a
  threshold only with the run id as its source.
- Done when: an OpenAI success fixture replays in tests, and READY_FOR_LIVE
  section 6 records the calibration outcome (changed or kept, with reason).

### P1. Packaging and defaults

- Package `step0` with `step0/data/*.json`; resolve data paths from the
  package, not the repo root.
- Console command `aceseo` (`geo.cli:main`); argparse prog `aceseo`.
- `collect --prompts/--facts` and `import-manual --facts` required: no
  BoardFlight default. `--out` and `export-fixtures --dest` relative to the
  current directory.
- GitHub Actions: unittest on Python 3.9 and 3.13; build a wheel, install it
  in a clean venv, run a dry-run plan from outside the repo.
- Done when: `pip install .` then `aceseo collect ... ` (dry run) works from
  an unrelated directory; all tests pass.

### P2. Generic claim ledger (hybrid)

Rule path (deterministic, decides):
- Generic fact types the matcher understands without site-specific regexes:
  `site_status`, `offer.is_free`, `organization.same_as`, plus user-declared
  facts with `value_type` boolean, integer or enum and a `match` block:
  `{"subject_terms": [...], "positive": [phrases], "negative": [phrases]}` for
  booleans, `{"unit_terms": [...]}` for integers, `{"values": {value: [phrases]}}`
  for enums. Phrases are literal (escaped), not user regexes.
- BoardFlight topics move to the BoardFlight facts file as declared facts;
  the code keeps no site-specific pattern. `MATCHER_VERSION` bumps to 3.

LLM path (proposes, never decides):
- Opt-in `--llm-claims ENGINE`. One extra call per ok capture, through the
  same terms gate, cost estimate and cap. Output: (sentence span, fact key or
  null, asserted value). Code checks the span exists in the answer and
  compares the value with the fact.
- Records carry `matcher: "llm"`, the model id and raw response hash. Their
  verdicts are listed in the report under a separate heading and excluded
  from R2 until the user runs `aceseo confirm CLAIM_ID`, which writes a
  confirmation record (never edits the claim).
- Done when: on the synthetic example plus one non-BoardFlight site, the rule
  path decides declared facts with zero site-specific code, and an LLM claim
  cannot change a decision without a confirmation record (test).

### P3. `aceseo init URL`

- Fetch the home page, `/llms.txt` and robots.txt; draft `facts.json` from
  HTTP status (site_status), JSON-LD (`Organization.name`, `sameAs`, `url`),
  `<title>`/`og:site_name`, and `llms.txt` lines, each fact with its source
  locator and snapshot hash (W3 schema). Draft `prompts.json` from 6 generic
  templates.
- Writes files only where they do not exist; prints which facts need review.
- Done when: running it against the BoardFlight fixtures reproduces the
  sample's code-extractable facts, and the output passes `runtime_problems`.

### P4. `aceseo diff RUN_A RUN_B`

- Per engine: mention and citation rate change with both n; per fact: verdict
  counts before and after; page-check result changes. Refuse when facts
  hashes or prompt sets differ unless `--allow-input-change`, then say so.
- No significance claim; below-minimum n is shown as insufficient, as in
  the report.
- Done when: diff of two synthetic runs is byte-stable and tested.

## 4. Non-goals (unchanged plus D2)

Composite scores, UI scraping, auto-editing sites, telemetry, hosted
service, multi-site or agency features, LLM-decided verdicts.

## 5. Order

P1 now. P0 when credit is available. Then P2 (largest), P3, P4. MCP server
after P4 if the skill sees use.

Actual: P1, P2, P3, P4 done 2026-10-30 (section 6), out of order relative to
D4 because they needed no credit. P5 and P6 (section 7) came from the first
ChatGPT import and need no credit. P0 is the only item blocked on the
owner adding OpenAI credit. MCP server remains undecided, pending use of the
skill.

## 6. Status and changes from the plan (2026-10-30)

- P1 done (commit 3fdd57a).
- P2 done with one change: the owner has a Claude subscription and no API
  credit, so the LLM path does not call an API. `--llm-claims` was replaced
  by `aceseo propose-claims RUN --from FILE`: the proposals are written by an
  assistant on the subscription (for example Claude Code) and imported. They
  are stored in `RUN_DIR/proposals.jsonl`, which decide never reads, so a
  proposal cannot change a decision (tested). `aceseo confirm` promotes a
  proposal by adding a phrase to the fact's `match` block in the user's facts
  file, refusing unless the rules would then decide the sentence; it takes
  effect from the next run, and no existing record is edited. The `model`
  field is validated but not stored (the claim schema allows no extra
  fields); no raw response hash exists because there is no API response.
  `MATCHER_VERSION` is 3; BoardFlight topics are declared in
  `design/boardflight.facts.sample.json`.
- P3 done, narrower than planned: `init` fetches the home page and
  `/llms.txt` only (no robots.txt; page checks already cover it) and drafts
  the minimal facts format, not the W3 schema with snapshot hashes. Facts a
  person must state are not guessed; the llms.txt summary is printed instead.
- P4 done as specified. `diff` reads the stored decision numbers, so it
  shows every statistic the decision recorded, not only mention and citation
  rates.
- Still needs API credit: `collect --live` and P0.

## 7. Remaining work

Current scope (owner instruction, 2026-10-31): subscription services only,
no API top-up and no paid API calls. This supersedes the API execution plan
below and the older section 3 P0 entry. API P0 is deferred, not complete;
do not request keys or credit unless the owner explicitly reopens it.
P5's facts and saved-answer import are implemented with the limitation below;
P6 is deployed (docs/PROGRESS.md Steps 16 and 17). Task B is verified complete.
Subscription observation and citation backfill are completed for ten prompts.
MCP server stays deferred.

### P5. Current BoardFlight facts and the first ChatGPT import (no credit)

Source: on 2026-10-30 the owner asked ChatGPT (app, search on) the 5
questions in `design/manual/chatgpt-app-2026-10-30.query.txt`; the cleaned
answer is `design/manual/chatgpt-app-2026-10-30.answer.txt` (copy noise such
as `&#x20;`, `\.` and favicon lines removed, wording unchanged; citations it
showed: home, /methodology, /airports, /how-it-works, /terms and
github.com/daniel1001a/boardflight-airport-wait-data). Checked by hand
against the live llms.txt and /methodology the same day: every checkable
statement was correct (live site, free with no account, 61 airports, no
live queue data, 16 of 61 pass the TSA check, 28 profiled since the last
check unscored). Imported with the sample facts it gave 7 claims, 0 decided
(6 `needs_review`, 1 `unsupported`).

Why 0 decided, and what to change:
- `design/boardflight.facts.sample.json` is dated 2026-10-19 and says 33
  airports; the site now says 61 (33 is now the TSA-check count). The sample
  is tied to the recorded fixtures and `tests/geo_fixtures.py: FACTS_PATH`,
  so do not edit it. Add a new file, `design/boardflight.facts.json`,
  drafted with `aceseo init https://www.boardflight.com/` and then completed
  by hand, for live and manual runs from now on.
- Facts the new file must declare, each with a `match` block (README
  "Declaring facts"): `llms.coverage.airport_count` = 61 with subject_terms
  including "lists" and "profiled" as well as "cover/covers"; the free,
  no-account offer (built-in `llms.offer.is_free` = true); and a boolean
  `llms.data.uses_live_queue_data` = false whose negative phrases include
  "no live queue data", "not live measurements", "no real-time checkpoint
  queue lengths".
- Re-import the saved answer with the new facts file (`import-manual`,
  `--surface chatgpt-app --vendor openai --observed-at 2026-10-30T16:40:00Z`,
  the query file's text as `--query`, mention terms BoardFlight,
  www.boardflight.com, boardflight.com, the six URLs above as `--cite`).
  For sentences still undecided, run the Step 7 workflow in
  `skills/aceseo/SKILL.md` (`propose-claims`, then `confirm` only for what
  the owner agrees with).
- Done when: the re-import decides the airport count, the free offer and
  live-queue-data sentences as `matched`; the run directory is outside the
  repo or committed under `examples/`, the owner decides which; full suite
  passes; a docs/PROGRESS.md step records the run id and the before/after counts.

### P6. BoardFlight llms.txt wording (other repo: ~/Projects/boardflight)

The owner wants the site to say the prediction is computed live. True: the
flight, terminal and departure time are looked up live per request (home
page already says "Computed live for this flight"), and hourly curves use
live schedule data when available. Not true: the security wait is modeled
from historical and scheduled patterns; /methodology says "no real-time
checkpoint queue lengths". Do not call the prediction or wait times
"real-time"; that would contradict /methodology and is what engines would
then report as inconsistent.

- Change only the second paragraph built in `lib/seo/llms-txt.ts`
  (`buildLlmsTxt`) to: "Each plan is computed for your flight when you ask:
  BoardFlight looks up the flight, terminal and departure time live, then
  adds curb-to-check-in time, bag drop if you have a bag, a modeled security
  wait for that airport and hour (read at the ${percentile} percentile, so it
  plans for a slower-than-usual day), and the walk to the gate. The security
  wait is modeled from historical and scheduled patterns; it uses no live
  queue data. Airline check-in and boarding deadlines always come first."
- Leave /methodology and the home page as they are.
- Run that repo's tests and lint; update any test that pins the old text.
  Show the owner the diff; commit only when asked (that repo's own rules
  apply, read its AGENTS.md and CLAUDE.md first).
- After it is deployed, add a `llms.data.flight_lookup_is_live` = true fact
  to `design/boardflight.facts.json` if the owner wants it checked.

### Task B. Site-status collision (verified complete 2026-10-31)

Matcher v4 excludes "not live" followed by a word from site-status negatives,
except predicate endings "yet", "anymore" and "now". Generic regression tests
cover "not live measurements/data" and "the site is not live". This is a
conservative lexical rule: predicates with other following words may be missed.
No site-specific matcher terms or entity-rule changes were made.
The saved answer still yields 9 claims: 2 matched, 7 needs_review. In particular,
"its security wait times..." lacks an explicit site mention, so removing the
collision does not decide that sentence. P5's original three-match acceptance
criterion remains unmet for that answer. Full suite: 341 tests, OK, 1 skipped;
the deterministic synthetic example matches its rebuild byte for byte.

### Subscription observation (separate from API P0)

Use the owner's ChatGPT subscription browser UI and the ten prompts in
`step0/data/prompts.json`, with fresh conversations where practical. Preserve
exact prompts, answers, actually shown citations and observation times under
gitignored `runs/`. Record visible model/search settings or explicitly unknown.
Import with `import-manual` and `design/boardflight.facts.json`; inspect the
ledger. Manual observations never enter API rates or decisions. Do not export
API fixtures, promote `FIELD_STATUS`, calibrate API thresholds or silently
confirm proposals from these observations.

Completed 2026-10-31 after the owner confirmed login: ten fresh ChatGPT web
conversations, one per existing prompt, imported as ten manual runs under
`runs/subscription-20261031/imports/`. Evidence and run-id mapping:
`runs/subscription-20261031/index.json`; reviewed summary:
`runs/subscription-20261031/summary.md`. Visible initial model selection was
GPT-6 with Instant effort; the backend identifier is unknown. Web search was
selected for every prompt. Workspace 2 was finished after capture.

The original v4 ledgers recorded 4 claims, 2 matched and 2 needs_review.
Follow-up matcher v5 corrects the contextual false positive: same-name other
hosts in the answer or citations make brand-only sentences needs_review;
explicit allowed hosts still disambiguate. Pronouns still do not name the site.
This is conservative and can also downgrade brand-only comparison statements.
Citation hostnames count; URL paths and titles do not. Proposal confirmation
uses the same full-capture context and cannot bypass this check.

The same saved observations were reimported under
`runs/subscription-20261031/rechecked-v5/`, with unchanged run ids and original
observation times, not new samples. The original v4 runs remain intact.
`index-v5.json` maps both versions; `summary-v5.md` explains the result:
4 claims, 1 matched (61 airports), 3 needs_review. The .app free=true answer
now stays needs_review. No facts or match phrases were changed. Full suite:
346 tests, OK, 1 skipped, including the deterministic synthetic rebuild.

Citation backfill completed after the owner explicitly allowed a replacement
workspace. Workspace 5 reopened the same saved conversations without new prompts
or regeneration; all ten answers matched saved content after normalizing layout
whitespace. All 17 saved prose citation groups (29 source-card occurrences)
were resolved through their actual UI targets. Later backfill timestamps are
stored separately under `citation-backfill/`; original evidence is intact.

Final manual imports are under `runs/subscription-20261031/complete-v5/`.
`index-final.json` maps all versions and run ids; `summary-final.md` is the
current review. The same ten run ids and original observation times are reused,
not new samples. All ten final imports validate; v5 claim ids and verdicts
remain unchanged at 1 matched, 3 needs_review. Workspaces are finished.
Personalization and location were not controlled; fresh conversations do not
prove statistical independence. Source claims were not independently verified.
See docs/PROGRESS.md Steps 19 to 21 for the observation and recheck history.

### P0. API real-data validation (deferred by owner)

The 2026-10-31 attempt refused before sending requests or creating a run.
Actual API spend for that attempt and this continuation: $0. No new fixtures,
OpenAI success replay test or field verification exists. `FIELD_STATUS` is in
`geo/adapters.py`, not `geo/facts.py`; it is unchanged. Thresholds in
`geo/number.py` remain unchanged and provisional because no new API per-engine
n or rates exist. Subscription observation does not complete API P0.

If the owner explicitly reopens API P0, confirm new spending authorization and
credit, re-read CLI flags, and show a dry-run plan before execution. Historical
inputs were ten prompts, current facts, three repeats, anthropic + openai,
`--cap-usd 2`; $1.491 expected / $1.791 upper were estimates, not a guaranteed
bill ceiling. Export to new empty destinations, verify byte-identical exports,
promote only actually observed API fields, add a real OpenAI success replay,
and review thresholds using adequate per-engine evidence and the run id.
Release authorization (2026-10-31): the owner subsequently authorized commits,
push of v0.2, a pull request and merge into main after validation. This does
not authorize paid API work or complete API P0.

MCP server: no action until the Claude Code skill (`skills/aceseo/`) has
seen real use; revisit D3 then.
