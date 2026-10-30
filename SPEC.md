# SPEC.md: AceSeo v0.2

Status: agreed 2026-10-30. P1 to P4 implemented 2026-10-30 (section 6); P0 waits for OpenAI credit. Supersedes nothing in PLAN.md; it sets the next
work after the MVP (PROGRESS.md Steps 1 to 13).

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
D4 because they needed no credit. P0 is the only item still blocked on the
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

Only P0 is open, and it is gated on the owner adding OpenAI credit
(the account has none; `PROGRESS.md` Step 13). Nothing else in this spec is
blocked. When credit is available:

1. Export fixtures from a BoardFlight run (`--prompts step0/data/boardflight.prompts.json
   --facts design/boardflight.facts.sample.json --repeats 3`, engines
   anthropic + openai, `--cap-usd 2`), live.
2. Move every OpenAI field the run actually returns from `unverified` to
   `live` in `geo/facts.py: FIELD_STATUS` (follow the pattern used for
   Anthropic in PROGRESS.md Step 13).
3. Compare the real per-engine n and rates against the thresholds in
   `geo/number.py`; change a threshold only when the run's own numbers show
   it is wrong, citing the run id as the source. Do not change a threshold
   on the OpenAI run's say alone if repeats or sample size do not support it.
4. Record the outcome (changed or kept, with reason) in `READY_FOR_LIVE.md`
   section 6, and add a PROGRESS.md step.
5. Re-run the full suite and `export-fixtures`; commit the new fixtures and
   docs.

MCP server: no action until the Claude Code skill (`skills/aceseo/`) has
seen real use; revisit D3 then.
