# SPEC.md: AceSeo v0.2

Status: agreed 2026-10-30. Supersedes nothing in PLAN.md; it sets the next
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
