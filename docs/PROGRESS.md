# PROGRESS

Run tests: `python3 -m unittest discover -s tests -t .` (Python 3.9.6, stdlib only, offline).

## Step 1: geo core (done 2026-10-19)

Files: `geo/{canonical,ids,terms,number,runindex,render,cost,config,records,store,validate}.py`,
`tests/geo_fixtures.py`, `tests/test_geo_core.py`.

- ids: W5-01 golden ids match. A mutated id gives only `E_ID_MISMATCH`.
- Validator: V1 to V15, V25 (via the page-check registry, Step 2) and V27. Claims and decisions get the common fields only.
- Terms gate: only `verified-allowed` passes. Opt-in engines must be selected. W5-02 B gives `E_TERMS_GATE`.
- Number rule: W5-05 N1 to N6 each yield exactly one code. Together they are collected into one `RenderError` and no file is left behind.
- Renderer: W5-06 a to f pass. W5-04 renders `2/4` and `2/6` and lists the excluded ids.
- Cost: W5-10 expected values match: 0.01125, 0.01035 and 0.004.

Decisions applied:
- anthropic `max_uses=3`. This is the documented cap and is used only for the upper bound (0.03035 per call).
- OpenAI and Perplexity have no documented per-call search cap. The tool assumes 1 search per call and labels it `assumed_1_search_per_call_estimated`.
- The expected estimate always uses `token_assumptions.searches_per_call` = 1 (Estimated). This matches W5-10 and step0.

Deviations and extensions (open for review):
- A Number raises at construction. The renderer re-runs the same checks, so a bypassed object is still caught.
- `E_N_BELOW_MIN` is reported only when n is consistent and the evidence is non-empty, so N1 and N2 each yield exactly one code.
- Seal (V26) is deferred. A run renders only if `load_valid_run` returns no issues.
- `fact_value` is not in the statistic registry, because W4 gives it kind n/a.
- `failure_rate.engine` counts every attempt of the engine. Its hits must be exactly the non-ok attempts.
- New manifest fields: `opt_in_selected` and `transport` (live|fixture). New capture fields: `search_observed`, `cost_billed_usd` and `cost_billed_field`.
- `series_key` = sha256 of the identity without run_id and attempt, with no domain prefix.
- The forbidden header names (`authorization`, `x-api-key`) are checked in request bodies only. Secret values are checked in every file.
- `terms_last_updated` values come from research/w1-api-terms.md. `TERMS_MAX_AGE_DAYS` is still unset, so there is no staleness check.

## Step 2: page checks (done 2026-10-19)

Files: `geo/pagechecks.py`, `tests/test_pagechecks.py`, `tests/fixtures/boardflight-2026-10-19/`
(RECORDED bodies of `/`, `/airport/jfk` and `/llms.txt`, with `FIXTURES.json` giving their sha256).

- The fetcher is injected (`fetch(url, user_agent)`). `FixtureFetcher` serves dict routes. No network code exists yet.
- Registry `(check_name, version)`: `http-status`, `robots-ai`, `noindex`, `key-content` and `main-content` are blocking. `canonical` and `llms-txt` are reported only.
- Every record points at the raw body it was derived from. `robots.txt` is fetched once per origin and shared by all crawler profiles (`derived_from_raw`).
- The 3 BoardFlight key pages pass on the RECORDED bodies. The h1 and first-paragraph texts match PLAN 5.7.1. `/llms.txt` matches `Covers 33 US airports`.
- W5-09: R-A, H1 to H4, redirects of 1 and 5 hops, HTML-1/2 and timeout all pass. V25 negative cases yield exactly one code each.

Assumptions and open items:
- AI crawler tokens (GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot, PerplexityBot, Google-Extended) are from general knowledge. Each record has `crawler_token_status: "unverified"`.
- robots.txt uses `urllib.robotparser` semantics, not RFC 9309 longest-match (W5 Q5). A 4xx robots.txt means allow all. Any other non-200 is `not_checkable`.
- More than 5 redirects gives `not_checkable` (`too_many_redirects`). W5 Q7 is still open.
- `MIN_PARA_CHARS` = 40 is a placeholder and is labelled so in detail.
- `key_content` entries can also give `expected_pattern` (a regex matched per line), used for the `/llms.txt` rule. This extends W4 3.1.
- Status codes and headers for the recorded pages were not recorded. Tests wrap the bodies in a SYNTHETIC 200 response.
- W5-09 R-B (real robots.txt) is skipped until it is recorded.
- A real HTTP fetcher is not written yet, because nothing in Step 2 needs the network.

## Step 3: adapters and collector (done 2026-10-19)

Files: `geo/adapters.py`, `geo/collect.py`, `geo/cli.py`, `tests/test_adapters.py`.
The suite is 125 tests: all pass and 1 is skipped (R-B). No network calls were made and no real key was read. Tests use fake keys and SYNTHETIC response bodies.

- Dry run is the default. `collect()` and `python3 -m geo.cli collect` print the plan and its Estimated costs. They write nothing and never touch a transport.
  - Sending needs `send=True`, an injected transport and one key per engine.
  - Only `geo.cli --live` builds `UrllibTransport` (https only), and only that path reads `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` from the environment.
- The run is refused before the run dir exists, with zero transport calls, in these cases:
  - a send without a transport
  - a missing key
  - perplexity is selected (its adapter is an interface only, and its response shape is unverified)
  - the Estimated first attempts exceed `cap_usd`
- Terms gate (W5-02 A, C, D):
  - Every slot of an engine excluded for its terms (restricted, unverified, opt-in not selected) is logged as `skipped_slots` with reason `terms_gate`. It is never built or sent.
  - Before each send, `guard()` checks each snapshot again. If that check fails, the slot gets `terms_gate`, the transport gets 0 calls and nothing is written.
- Keys are passed to `RunWriter` as secrets. Only the request body is stored. Headers, including the auth header, are never stored.
  - A response that echoes the key raises `SecretError`.
- Retries: a failed slot is retried up to `max_attempts`. `ok` and `refused` are final.
- Budget:
  - `spent_estimate_usd` adds up the per-call Estimated cost (W5-10: openai 0.01125, anthropic 0.01035).
  - Before each attempt, the collector checks that the attempt still fits under the cap. If it does not, a first attempt gets `budget_cap`; for a retry, the collector stops.
- An interrupt (Ctrl-C) marks the slots that were not started as `user_abort`, and the manifest is still written.
- Tests cover these cases for both engines:
  - ok
  - no_search (ok, `search_observed` 0, no citations)
  - refused (not retried)
  - timeout (raw null), then ok
  - 429 and 500 (raw stored as `.bin`)
  - parse_error
  - empty_answer
  - incomplete
  - an Anthropic tool error inside a 200
  - a cache write that drops usage
  - UrllibTransport error mapping, tested with a fake opener
- Every run directory a test produces passes `validate_run`, and none of its files contains a key.

Assumptions and open items:
- No real provider response has been recorded. Each adapter's `FIELD_STATUS` labels fields as documented or unverified. These are unverified:
  - OpenAI: `usage.input_tokens/output_tokens`, `cached_tokens`, the `refusal` content part and the top-level `status`.
  - Anthropic: `stop_reason: "refusal"`.
- OpenAI `cached_input_tokens` is null, so `cost_from_usage_usd` is not computed for OpenAI, because we have not confirmed whether `input_tokens` includes cached tokens.
- Anthropic usage is set to null when `cache_creation_input_tokens` is not 0, because there is no price row for cache writes.
- New error classes, an extension of W4 3.3:
  - `incomplete`: anthropic `pause_turn`, or an openai status other than completed. Continuing the turn is not implemented.
  - `tool_error`: a `web_search_tool_result_error` other than `max_uses_exceeded` or `too_many_requests`. The first leaves the answer standing; the second maps to `rate_limited`.
- The retry backoff is a fixed `2 * attempt` seconds. It is a placeholder, not provider guidance.
- The budget check uses Estimated costs only, and the real bill can be higher. `upper_first_attempts_usd` is reported in the dry run, using anthropic `max_uses` 3 and the assumed 1 search per call for the others.
- The CLI env var names are a project choice and are not read from any doc.

## Step 4: facts loader and W5-08 (done 2026-10-19)

Files: `geo/facts.py`, `tests/test_facts.py`, `tests/fixtures/boardflight-repo-e17bc0d/structured-data.ts`.

- `validate_facts(doc, now, bodies=None, allow_sample=False)` implements the W3 rules 1 to 15 and returns every issue. W5-08 V0 to V11 each yield exactly the listed rule.
- `build_boardflight()` starts from the 8 sample facts and adds 3 facts derived from the RECORDED bodies: `llms.offer.is_free` (llms.txt line 3), `llms.data.uses_live_queue_data` (line 5) and `jsonld.organization.same_as` (the jfk page, JSON-LD block 0). The result is sorted, deterministic and valid with the recorded bodies.
- Every excerpt is checked against the recorded body when bodies are given (rule 14), and body hashes are rechecked (rule 8).

Assumptions and open items:
- The committed sample is already sorted, so W5-08 V6 uses the reversed order as its negative case.
- The `llms.tsa_check.passing_airports` excerpt was re-derived verbatim from line 7. The sample's shortened excerpt (with "...") is not a substring of the body.
- `same_as` comes from the jfk snapshot, because the home page body was not recorded.
- `same_as` has one prior value `[]` (no `sameAs` on the Organization node). Its source is the repo file at commit `e17bc0d` (`structured-data.ts`, stored under tests/fixtures). `valid_until` 2026-09-08T17:05:08Z is the time of commit `a37cde2`, the child of `e17bc0d`, which added `lib/seo/identity.ts` with the profile URLs. An empty list is allowed only as a prior value.
- The loader output keeps the sample notice and is still refused without `allow_sample` (rule 15), because the base facts are hand-assembled.
- The generator allowlist (`w3-hand-assembled-sample`, `geo.facts.boardflight_loader`) is a project choice. W3 Q6 is still open.

## Step 5: claim ledger and W5-03 (done 2026-10-19)

Files: `geo/claims.py`, `geo/validate.py` (V16 to V20), `tests/test_claims.py`, `tests/fixtures/claims/inactive-domain.json`.

- `claim_record()` builds a W4 3.5 claim. `fact_ref` is computed from `facts_sha256` and `fact_key`. The id uses the engine slug of the parent capture.
- `match_text()` is the rule matcher (`matcher` "rule", `matcher_version` 1). It splits the answer into sentences and makes at most one claim per sentence, so the span keeps claim ids unique.
- Verdicts: `matched` (exact for the airport count, normalized otherwise), `contradicted`/`value_mismatch`, `outdated`/`prior_value` (the asserted value equals a `prior_values` entry), `unsupported`/`no_fact`, `needs_review`/`undecided`.
- The validator checks V16 to V20: the capture must be ok, the span must cut the statement, the fact must resolve and its value snapshot must match type-strictly, the verdict and basis must be an allowed pair, and an llm matcher may not emit contradicted or outdated.
- W5-03 cases 1 to 5 each yield exactly one code. Case 6 gives contradicted for 40 and matched for 33. Case 7 ("dozens") gives needs_review.
- PLAN 6.2 fixture 1 (the inactive-domain quote) gives `site_status` contradicted, with both the sample facts and the loader facts.

Assumptions and open items:
- Anything uncertain goes to `needs_review` with no `fact_key`: a hedged or non-numeric count ("about 33", "dozens"), two topics in one sentence, conflicting status terms, no mention of the site, or a mention of another domain with the name stem (boardflight.app, the W3 3.3 wrong_entity case). Leaving `fact_key` empty keeps these out of `contradiction_rate`.
- A negative status phrase ("inactive", "no longer operating", 已停止營運) only contradicts a `live` fact. Against any other status it is needs_review, because the phrase does not say which non-live state.
- Topics with no fact in the facts file (founded, headquarters, mobile apps, employees) give `unsupported`. A topic whose fact is missing from this facts file (for example `is_free` in the W3 sample) also gives `unsupported`.
- `fact_value_snapshot` may be a list of strings, for `jsonld.organization.same_as`. This extends W4 3.5, which lists scalars only.
- The topic phrase lists (en and zh) are a project choice. Only ASCII digits count as numbers.
- The inactive-domain fixture is a second-hand quote, not a capture. It has `counts_in_rates: false` and is never written to a run.

## Step 6: decision engine and W5-07 (done 2026-10-19)

Files: `geo/decide.py`, `geo/number.py` (THRESHOLDS, two engine statistics, `to_dict`/`from_dict`), `geo/validate.py` (V21, V23, V24 on decisions), `geo/collect.py` (default thresholds), `tests/test_decide.py`, `tests/geo_fixtures.py` (`add_page_checks`, `add_decision` now calls `decide`).

- `decide(index, created_at)` evaluates R1, R0, R2, R3, R4 in that order and stops at the first rule that fires. Later rules are `not_evaluated` (reason `cascade_stopped`). There is no composite score.
- Each evaluation keeps `result`, `reason_code` and the ids it read. `input_ids` is their union. `why` has one entry per evaluated rule. `numbers` stores every Number or Insufficient the rules read, so each value has its n and evidence ids.
- `confidence_basis` groups the input ids by independence group: `site:<host>` for page checks, `vendor:<model_vendor>` for captures, and the parent capture's group for claims.
- `not_checked` always carries the 6 baseline items. It also lists excluded engines, skipped slots, not_checkable page checks, needs_review and unsupported claims, Insufficient statistics, and rules that were not evaluated.
- The validator rebuilds every stored number with `number.from_dict`, so a missing n or empty ids is E_SCHEMA. Any cited id that is not in this run is E_REF_UNRESOLVED. Cascade, outcome, hypothesis, assumption_refs and thresholds problems are E_DECISION. A missing baseline item is E_NOT_CHECKED.
- W5-07 A, A0, B and C give exactly the listed outcomes. The R2, R3 and R4 firing paths each have their own test (the W5-07 caveat).

Provisional thresholds (`number.THRESHOLDS`, all `status: provisional`, confirmed by the lead on 2026-10-20 for the first live run; see "Threshold status" below):

| Name | Value | Used by |
|---|---|---|
| N_MIN_REPEATS | 3 | per-prompt citation and mention rate |
| MIN_ENGINES | 2 | R0 (vendors with a sufficient engine rate), R3 (vendors that are low) |
| N_MIN_ENGINE | 6 | citation_rate.engine |
| N_MIN_CONTRADICTION | 3 | contradiction_rate.engine (reported only, no rule reads it) |
| K_CONTRA_REPRODUCE | 2 | R2 (distinct ok captures with a contradicted or outdated claim on one fact_key) |
| T_LOW_PERCENT | 20 | R3 (rate below 20 percent) |

`decide` refuses with E_THRESHOLDS when manifest.thresholds is not exactly this table. The collector now writes the table by default. `RULE_SET_VERSION` is 1.

Assumptions and open items:
- Site host: the shared host of the key pages, with a leading `www.` removed. A citation counts when its host is that host or a subdomain. Mentions are case-insensitive whole-word matches on `mention_terms`.
- `citation_rate.engine` pools only the prompts whose per-prompt rate reached N_MIN_REPEATS (D2). Failed or refused attempts are listed in `excluded`, never counted.
- R0 counts vendors, not engines, so two engines from one vendor count once (D10).
- R1: a blocking fail on a key page fires R1 even when another key check is not_checkable. With no fail and some not_checkable, R1 is `unknown` and R0 fires with `page_checks_incomplete` (D5).
- R2 reads only `rule` matcher claims that have a fact_key. needs_review and unsupported claims never count.
- R3: a vendor is low only when every sufficient engine of that vendor is low.
- R4 fires as `no_rule_fired` when nothing else fires, and cites the union of the earlier evaluations.
- hypothesis is true for R1 and R3. assumption_refs is `[A6, A7]` for R1, otherwise `[A7]`.
- A run with no blocking key-page checks is refused (E_NO_PAGE_CHECKS) instead of guessing R1.
- Not implemented yet: a count of contributing prompts, repeat agreement, and confidence groups for `fct_` and `src_` refs without a URL (decide raises E_DECISION if one is ever cited).
- The validator checks a decision for internal consistency but does not re-run `decide`, so it cannot catch a decision computed before later records were added.

## Step 7: report builder and offline end-to-end dry run (done 2026-10-19)

Files: `geo/report.py`, `geo/pipeline.py`, `geo/cli.py` (`report` subcommand), `geo/collect.py` (`start_run`, `on_start`), `geo/render.py` (scope in number formatting), `tests/test_pipeline.py`.

Behavior:
- `report.build_report(index, decision_id)` turns one decision record into a `render.Report`. It has these blocks: Recommendation, Rule evaluations, Measurements, Independence groups, and, when present, Failing blocking checks and Contradicted or outdated claims. The renderer then adds Excluded and skipped, Not checked and the A7 footer.
- Every number in the report is rebuilt from `decision.numbers` with `number.from_dict`. A missing n, a non-int n, empty evidence ids or a missing numbers list raises ReportError E_SCHEMA before rendering. The renderer still re-checks every id, status and window against the run.
- Rule ids and prompt ids contain digits, so prose names rules in words (`report.RULE_NAMES`). The ids stay in the decision record, which the report cites with an EvidenceRef.
- `render._fmt_scope` prints a number's scope (for example engine and prompt_id) inside the braces, after the statistic id, so two numbers with the same statistic are told apart.
- `collect.start_run` creates the run directory and writer. `collect.collect(on_start=...)` calls `on_start(writer)` before the first slot is sent.
- `pipeline.run_offline` runs page checks (in on_start), then captures, claims, decision and report. It validates the run after each stage and renders only from a run that validates. It accepts only a transport with kind `fixture` and a `FixtureFetcher`, and refuses anything else before a run directory is created.
- `python3 -m geo.cli report RUN_DIR [--out PATH]` renders the latest decision (by created_at, then id). It reads no keys and sends nothing. It refuses, with exit code 2, a run that does not validate, a run with no decision, or an existing output path.

Tests (all offline: SYNTHETIC provider bodies, RECORDED pages behind SYNTHETIC status lines, fake keys): each of the four outcomes seo_first, geo_fix_facts, geo_content and no_action end to end; the footer and every baseline not_checked item; every measurement line shows n and evidence ids; byte-identical output across two runs; no key bytes in any written file; prose has no digits outside ids and URLs; refusals for missing n, empty ids, an unknown id, an unknown decision, a live transport and a non-fixture fetcher; CLI output, overwrite refusal and invalid-run refusal.

Assumptions and open items:
- Recommendation sentences (`report.OUTCOME_TEXT`) are draft wording, confirmed by the lead on 2026-10-20 for the first live run. Every recommendation ends with "(provisional wording)" so the report itself says so; this suffix is removed once the lead signs off on final copy.
- The report says the thresholds are provisional, not calibrated. This changes once the lead reviews the first live run and either locks or adjusts `number.THRESHOLDS`.
- The report reads the latest decision only. Comparing decisions across runs is not implemented.
- insufficient_evidence is not covered end to end in test_pipeline. The decide unit tests cover it.
- No live run has been made. See READY_FOR_LIVE.md for the checklist.

## Threshold status (2026-10-20)

The lead confirmed the Step 6 placeholder values for the first live run; `number.THRESHOLDS["*"]["status"]` is now `"provisional"` (was `"placeholder"`). The values are unchanged:

| Name | Value |
|---|---|
| N_MIN_REPEATS | 3 |
| MIN_ENGINES | 2 |
| N_MIN_ENGINE | 6 |
| N_MIN_CONTRADICTION | 3 |
| K_CONTRA_REPRODUCE | 2 |
| T_LOW_PERCENT | 20 |

"Provisional" means: fixed so the first live run's numbers are comparable and reproducible, not yet checked against real captures, and expected to change once the lead sees real citation and contradiction rates. `decide.threshold_problems` still refuses any manifest whose thresholds differ from this table (E_THRESHOLDS), so a later recalibration is a deliberate code change, not silent drift. After the first live run, revisit these values against the observed n's before trusting R0/R3 outcomes on a second run.

## Step 8: Perplexity adapter (done 2026-10-20)

Files: `geo/adapters.py` (`PerplexityAdapter`), `step0/request_builder.py`, `geo/cli.py` (`PERPLEXITY_API_KEY`), `tests/test_adapters.py`, `tests/test_step0.py`.

- Response mapping read from docs.perplexity.ai (Agent API, `POST /v1/agent`) on 2026-10-20: `output[]` items of type `search_results` (results with `id`, `url`, `title`) and `message` (`content[].type == "output_text"`); usage `input_tokens`, `output_tokens`, `input_tokens_details.cached_tokens`, `tool_calls_details.search_web.invocation`. Every field the parser reads is listed in `PerplexityAdapter.FIELD_STATUS` with its status.
- Citation rule: a result counts as a citation only when the answer text contains its `[n]` marker (n = result id). Retrieved but unmarked results are not citations. This matches the OpenAI and Anthropic adapters, which count only cited sources, not everything searched.
- The request now sends the documented format-only instruction `request_builder.PERPLEXITY_CITATION_INSTRUCTION` ("Cite your sources inline using bracketed markers ..."), so markers are present. It does not mention any brand or steer the answer.
- A nonzero `cached_tokens` count has no price row, so `cost_from_usage` stays null for that capture rather than guessing.
- Perplexity is still opt-in only (`--opt-in perplexity`).

Unverified (no real Perplexity response has been recorded): any top-level `status` other than `completed`, and whether a refusal arrives as a distinct content part. Both are marked `unverified` in FIELD_STATUS; a non-completed status maps to `failed/incomplete`.

## Step 9: live pipeline, fixture export, manual import (done 2026-10-20)

Files: `geo/fetch.py`, `geo/pipeline.py`, `geo/collect.py`, `geo/cli.py`, `geo/fixtures_export.py`, `geo/manual.py`, `geo/records.py`, `geo/validate.py`, `geo/decide.py`, `tests/test_live_path.py`, `tests/test_live_fixtures.py`, `tests/test_adapters.py`, `tests/fixtures/live/README.md`, `READY_FOR_LIVE.md`.

- Gap found: `collect --live` wrote captures only, so `report` refused the run (no page checks, claims or decision). Now `--live` calls `pipeline.run_live`, the same stages as `run_offline` with `UrllibTransport` and the new `UrllibFetcher` (stdlib urllib, redirects followed one hop at a time and recorded, bodies cut at 5 MiB with a visible `x-geo-evidence-truncated` header). `run_live` refuses a non-live transport; `run_offline` still refuses a live one.
- Progress: the collector and pipeline emit events (page_checks, capture, skip, claims, decision); the CLI prints one line per event on stderr, with the Estimated spend so far.
- Dry run is now human-readable (engines, why others are not called, slots, Estimated cost per call and in total against the cap, the env vars `--live` needs). `--json` keeps the old output. New `--key-content URL TEXT` and `--report-out`.
- `geo export-fixtures RUN_DIR` copies a live run's JSON provider bodies to `tests/fixtures/live/<engine>/<sha256>.json` with identifier fields replaced by `"redacted"`, refuses fixture runs, refuses if redaction changes the parse, and writes `index.json` with the expected outcome. `tests/test_live_fixtures.py` replays them and skips while there is no index.
- Manual import (`geo import-manual ANSWER.txt --surface google-aio --query ... --observed-at ... [--screenshot PNG] [--cite URL]`): a run with `run_kind` and `transport` "manual" holding one capture with `access: "manual"`. The raw file is the answer bytes (the validator checks they equal `answer_text`), the screenshot is a `bin` attachment, cited URLs carry `provider_field: "manual"`, terms and price fields are null/empty and the cost is "0". Claims come from the same rule matcher, so they get evidence ids. `decide` refuses non-collect runs (E_RUN_KIND) and `report` points to `geo ledger`, so manual observations never enter a rate or a decision.
- `geo ledger RUN_DIR` prints every capture (access, status, raw and attachment paths, citations) and its claims with verdict, fact key, fact value and fact ref.

Tests: 285 run, 3 skipped (the live replay pair until a real export exists, plus the earlier skip). Not verified: `UrllibFetcher` against a real server (tests use a fake opener), and every live-only path, because no key was available in this session.

## Step 10: README, LICENSE, examples, facts input check (done 2026-10-20)

Files: `README.md`, `LICENSE` (MIT), `.gitignore` (`/runs/`), `examples/minimal/{prompts,facts}.json`, `examples/make_example.py`, `examples/synthetic/` (README, report.md, one run directory), `geo/facts.py` (`MATCHED_KEYS`, `runtime_problems`), `geo/cli.py` (`load_facts`), `tests/test_example.py`.

- README covers positioning, install (Python 3.9+, stdlib), input formats with the matcher's fact keys and its limits, dry run, live run with env vars, cost and budget (cap semantics read from `collect.py`), the rule cascade, other commands, layout and license.
- `examples/synthetic/` is a SYNTHETIC run built offline with fake keys; `tests/test_example.py` rebuilds it and compares byte for byte, so it cannot drift from the code. `geo report` on it reproduces `report.md`.
- `collect` and `import-manual` now refuse a facts file missing what the runtime reads (site.name, site.hosts, a list of facts with unique keys and values) with `refused: <path>: <problems>`, exit 2, instead of failing later inside the matcher. The full W3 schema check (`validate_facts`) is not applied to user files: it requires generator provenance a hand-written file cannot have.
- Honest limit stated in the README: matcher v1 decides only five fact keys, two of them BoardFlight specific. Other keys are stored but no claim refers to them.

Tests: 293 run, OK, 3 skipped.

## Step 11: Claude Code skill (done 2026-10-20)

Files: `skills/geo-evidence/SKILL.md`, `skills/geo-evidence/references/{inputs,live-run,reading-the-report}.md`, `tests/test_skill.py`, README section "Use it from Claude Code".

- The skill walks an agent through gathering inputs, writing prompts and facts, a free dry-run plan, a live run only after an explicit yes with keys the user exports, explaining the report with evidence ids, and manual import. Ground rules: numbers only from the run, keys never in chat or files, terms gate respected, hypotheses kept as hypotheses, drafts only, no site changes.
- `tests/test_skill.py` applies the check_skills format rules (frontmatter name equals folder, description length, under 500 lines, referenced files exist, no CJK, emoji or em dash) and checks that every `python3 -m geo.cli X` and repo path the skill mentions exists.

Tests: 298 run, OK, 3 skipped.

## Step 12: threshold review, recommendation copy, final checks (done 2026-10-20)

- Thresholds (`geo/number.py`): kept unchanged and still `provisional`. There is no real run yet, so any new value would be as unsourced as the current one. The values are the smallest that make each rule mean something: 3 repeats per prompt for a rate, 6 ok answers per engine, 2 vendors so one vendor cannot decide alone, 2 reproductions for a contradiction, under 20% for "low citation". Recalibrate after the first `--repeats 3` live run by comparing the real per-engine n and rates against them (READY_FOR_LIVE section 6).
- Recommendation copy (`report.OUTCOME_TEXT`): each outcome now states what it does not prove. R1 and R3 say hypothesis, R0 says it is not a clean result, R4 says unchecked claims are in the ledger. Thresholds are described in words, because the report prose test forbids bare numbers. The suffix is now " (draft wording, not yet reviewed against a live run)". The old "(provisional wording)" did not say what would end the provisional status.
- `examples/make_example.py` refuses only when `report.md` or `runs/` already exist, so the example README can sit beside them. Regenerated; byte-for-byte test still passes.
- Final checks: no key-like strings in the repo apart from the two fake test sentinels; no personal email; every price in `step0/data/prices.json` has a source URL and a retrieval date (2026-10-19); every engine in `step0/data/engines.json` has a terms URL, a last-updated date and a retrieval date.

Not done (needs real API keys): the Phase 1 live run, real fixtures in `tests/fixtures/live/`, adapter fixes driven by real responses, and the measured cost. The command is in READY_FOR_LIVE section 3.

Tests: 298 run, OK, 3 skipped.

## Step 13: first live run and the fixes it drove (done 2026-10-20)

Run: `run_20261020T142935Z_74e3cd`, `--repeats 1`, anthropic + openai, 10 prompts, 3 key pages. Report: `runs/first-live-report.md` (as produced) and `runs/first-live-report.v2.md` (re-rendered offline with the new copy; no request sent).

What it showed:

- Outcome `insufficient_evidence`, R0 `engines_below_minimum`, as expected for `--repeats 1`. Page checks: 0 blocking failures, n=29.
- Anthropic (claude-haiku-5-5): 10 of 10 ok, `stop_reason` `end_turn`. Content blocks seen: `thinking`, `server_tool_use`, `web_search_tool_result`, `text` with `web_search_result_location` citations. The adapter parsed every one correctly; citation counts match the structured citations. Site cited in 4 of 10 answers (p_04, p_07, p_09, p_10), mentioned in 7 (p_04 to p_10). One vendor and n=1 per prompt: a smoke test, not a measurement to act on.
- OpenAI: 0 of 10. All 20 attempts were HTTP 429 with `error.type` `insufficient_quota` (code `credit_balance_exhausted`): the account had no credit. The collector classed it `rate_limited` and retried each slot once, wasting 10 requests.
- Claims: 8, all `needs_review`. Causes: Markdown bold around the value (p_09), pronoun subjects (by design, the site must be named), one Chinese sentence, and p_08 describing a different app with the same name.
- Cost: the old assumptions (1000 in, 500 out, 1 search) gave $0.1035 for the ten Anthropic calls; their reported usage priced at the Published prices gives $0.1958 (about 1.9x). Measured means: 21987 input tokens (range 12644 to 36190), 762 output, 1.7 searches. Both figures are Estimated; the provider bill is the real cost.
- p_01 has six inline Markdown links in the answer text that are not structured citations, so they do not count under the current rule. Left unchanged pending a decision.

Changes:

- `quota_exhausted` (records, adapters, collect): OpenAI 429 with `insufficient_quota` is a failed capture with that error class, not retried, and the engine's remaining slots are skipped with the same reason. `tests/fixtures/live/index.json` OpenAI entries edited by hand to expect it, so a fresh export of this run would refuse (the run recorded `rate_limited`).
- `FIELD_STATUS`: every Anthropic field seen in the run is now `live`; `pause_turn` and tool errors stay `documented`, refusal stays `unverified`. OpenAI success fields and all of Perplexity stay unverified: no real answer yet.
- Matcher v2 (`claims.MATCHER_VERSION = 2`): `**`, `__` and backticks are stripped before reading a sentence; spans still point into the original text.
- `token_assumptions`: 22000 in, 800 out, 2 searches (rounded-up Anthropic means, still `Estimated`). The upper search count is never below the expected one; when that raises it, `upper_basis` is `expected_searches_per_call_estimated`. New totals for anthropic + openai: `--repeats 1` $0.497 expected, $0.597 upper; `--repeats 3` $1.491 / $1.791, so `--cap-usd 1` no longer fits a repeats-3 run. W5-10 tests stay pinned to the old planning inputs through `fx.w5_10_prices()`.
- Report copy: the `insufficient_evidence` text now depends on the R0 reason (`report.INSUFFICIENT_TEXT`) and, being the one outcome reviewed against a live report, drops the draft marker. Other outcomes keep it. "Not checked" collapses repeated `insufficient` lines per statistic and n ("x10, listed under Measurements"); the live report had 40 near-identical lines.
- Docs: README cost table, READY_FOR_LIVE status and sections 2, 4, 5, 6, skill references (`quota_exhausted`, draft-marker rule). `examples/synthetic/` regenerated.

Real-data scope: one vendor, one model, one repeat, 10 prompts, one site. Nothing from OpenAI or Perplexity. Thresholds unchanged and still provisional: n=1 per prompt says nothing about whether 3 repeats or 6 answers per engine are the right minimums.

Open: add OpenAI credit; decide whether inline Markdown links count as citations; first `--repeats 3` run (cap $2 or more) to calibrate thresholds; fixtures keep `encrypted_content`, `signature` and `tool_use_id` (opaque provider values) and need a read before publishing.

Tests: 304 run, OK, 1 skipped (the live replay now runs).

## Step 14: v0.2 spec and P1 packaging (done 2026-10-30)

Files: `SPEC.md`, `pyproject.toml`, `geo/cli.py`, `geo/manual.py`, `.github/workflows/test.yml`, `.gitignore`, `README.md`, `READY_FOR_LIVE.md`, `skills/aceseo/SKILL.md`, `tests/test_adapters.py`, `tests/test_example.py`, `tests/test_live_path.py`.

- `SPEC.md` records decisions D1 to D4 (hybrid claim ledger, solo-developer user, pip plus skill, real data before tuning) and workstreams P0 to P4.
- `step0` and `step0/data/*.json` are now packaged; `geo/cli.py` finds the data next to `step0`, not via the repo root. Console command `aceseo`.
- `collect --prompts/--facts` and `import-manual --facts` are required: no BoardFlight default. `--out` and `export-fixtures --dest` are relative to the current directory (same paths as before when run from the repo root).
- CI: unit tests on Python 3.9 and 3.13, then a wheel installed in a clean venv plans a run from outside the repo.

Verified locally: wheel built with `uv build`, installed into a Python 3.9 venv, `aceseo collect` dry run with `examples/minimal` from a directory outside the repo; missing `--prompts/--facts` gives an argparse error. The CI workflow itself has not run yet.

Tests: 304 run, OK, 1 skipped.

## Step 15: P2 to P4 without API credit (done 2026-10-30)

Files: `geo/{claims,facts,proposals,init,diff,store,validate,runindex,render,cli}.py`, `design/boardflight.facts.sample.json`, `examples/synthetic/`, `tests/test_{declared_match,proposals,init_diff,claims,example}.py`, `README.md`, `SPEC.md`, `skills/aceseo/`.

- Matcher v3 (`claims.MATCHER_VERSION = 3`): built-in topics are `site_status`, `llms.offer.is_free`, `jsonld.organization.same_as`. Any boolean, integer or enum fact can declare a `match` block of literal phrases; `facts.runtime_problems` checks it. The BoardFlight airport-count and live-queue topics moved into the sample facts file; no site-specific pattern is left in the code.
- P2 on the subscription: `propose-claims` imports proposals written by an assistant outside the tool into `RUN_DIR/proposals.jsonl` (`matcher: "llm"`, `needs_review`). The validator checks that file; decide never reads it. `confirm` adds a phrase to the fact's `match` block in the user's facts file, only when the rules would then decide the sentence. The report and `ledger` list proposals as not counted.
- P3 `init URL`: two GETs (home, `/llms.txt`), drafts name, hosts, `site_status`, JSON-LD `sameAs` and 6 generic prompts; never overwrites a file.
- P4 `diff RUN_A RUN_B`: decision numbers as stored (k/n), rule-claim verdict counts per fact, page-check results; refuses on different facts or prompts files unless `--allow-input-change`. Output is byte-stable (tested).
- SPEC section 6 records where the build differs from the plan and why.

No API call was made. `collect --live` and P0 still need API credit.

Tests: 339 run, OK, 1 skipped.

## Step 16: P5, re-import BoardFlight with declared facts (done 2026-10-30)

Files: `design/boardflight.facts.json` (new), `runs/p5-before/`, `runs/p5-after/` (gitignored, not committed).

- `design/boardflight.facts.json` drafted with `aceseo init https://www.boardflight.com/` and completed by hand: `site_status`, `llms.offer.is_free`, `jsonld.organization.same_as`, plus declared `match` blocks for `llms.coverage.airport_count` and `llms.data.uses_live_queue_data`. `design/boardflight.facts.sample.json` (fixtures depend on it) was not touched.
- Re-imported `design/manual/chatgpt-app-2026-10-30.answer.txt` twice with `import-manual`, same flags, only the facts file changed.
  - Before (`design/boardflight.facts.sample.json`, run `run_20261030T164000Z_4a1a4e` under `runs/p5-before/`): 7 claims, 0 matched (6 needs_review, 1 unsupported).
  - After (`design/boardflight.facts.json`, run `run_20261030T164000Z_4a1a4e` under `runs/p5-after/`): 9 claims, 2 matched directly by the rule matcher (`llms.offer.is_free=true` normalized, `llms.coverage.airport_count=61` exact), 7 needs_review.
- Step 7 (SKILL.md): wrote two proposals for the remaining undecided sentences (live-queue-data sentence, airport-count table row), imported them with `propose-claims` (both listed, not counted). Tested `confirm` on a scratch copy only; both refused by the tool before any write:
  - Table row: fails the entity check (`_entity()`), not fixable by a facts-file phrase.
  - Live-queue-data sentence: collides with the built-in `site_status` topic (`_STATUS_NEG` in `geo/claims.py` matches bare "not live" as a substring), a two-topic hit the matcher always sends to needs_review. Code-level, not a facts-file fix; left as a finding, not acted on.
  - No facts file was ever written by `confirm`; the real `design/boardflight.facts.json` is unchanged since its initial draft.
- `runs/p5-before/` and `runs/p5-after/` stay under the gitignored `runs/`, not under `examples/` (that directory holds only the synthetic, deterministic demo checked byte-for-byte by `tests/test_example.py`).

Of the three facts P5 targeted, 2 are now matched directly from this answer; the third (`llms.data.uses_live_queue_data`) stays needs_review for this particular answer, with the root cause above.

Tests: 339 run, OK, 1 skipped.

## Step 17: P6 deployed, flight-lookup fact added (done 2026-10-30)

Files: `design/boardflight.facts.json`.

- P6 merged in the BoardFlight repo as PR #116 (squash commit `2e86470`): the second llms.txt paragraph now says the flight, terminal and departure time are looked up live and the security wait is modeled with no live queue data. Confirmed on the production `/llms.txt` with a plain GET.
- Added `llms.data.flight_lookup_is_live` = true with a declared boolean `match` block (positive phrases such as "departure time live", "live flight data"; negative phrases such as "no live flight data"). Checked with `match_text`: the production llms.txt sentence is matched, "no live flight data" is contradicted, a sentence that also states the queue-data fact goes to needs_review (two topics). The 2026-10-30 ChatGPT answer predates the change and has no sentence for this fact.

Tests: 339 run, OK, 1 skipped.

## Step 18: API P0 deferred; site-status collision verified (2026-10-31)

Task A (P0) is incomplete. The owner confirmed OpenAI credit and approved the
dry-run plan: 10 prompts x 3 repeats x anthropic + openai, 60 calls, $1.491
expected / $1.791 upper estimate, `--cap-usd 2`, current
`design/boardflight.facts.json`. Key pages: home, /llms.txt, /methodology.
The live command refused before sending requests or creating a run because
both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` were absent from the process
environment. Run id: none. Actual cost: $0. No fixtures were exported and no
OpenAI success replay test or `FIELD_STATUS` changes were made: there is no
new provider response to verify. `FIELD_STATUS` is in `geo/adapters.py`, not
`geo/facts.py`. All thresholds remain unchanged and provisional because no
new per-engine n or rates exist. READY_FOR_LIVE.md section 6 records this
blocker. The owner's subsequent instruction supersedes the API plan: no API
top-up, subscription services only. P0 API validation is now deferred by scope,
not waiting for keys. No further paid API calls will be attempted. Subscription
answers can use `import-manual` and stay excluded from API rates, thresholds
and field verification. Opened ChatGPT in ego-browser space 2 for this path;
it was logged out, so the login page is being handed to the owner. No new
subscription answer has been collected yet.

Task B (owner authorized): `geo/claims.py` no longer reads "not live" followed
by a word as a site-status negative, except common predicate endings "yet",
"anymore" and "now". Thus "estimates, not live measurements/data" can match
its declared data fact without a second site-status topic, while "the site
is not live" still contradicts. This is a conservative lexical check, not a
general grammar parser. No site-specific words were added to code.
`MATCHER_VERSION` bumped from 3 to 4 to distinguish changed claim semantics,
following SPEC.md's versioned matcher precedent. Two generic regression tests
cover adjective and predicate uses. Regenerated the deterministic synthetic
example's claims, decision references and report for the new claim ids.
The sample facts file was not edited. No commit or push.

Tests: `python3 -m unittest discover -s tests`: 341 run, OK, 1 skipped.

Continuation review (2026-10-31): Task B verified complete without further code
changes. Full suite rerun: 341 tests, OK, 1 skipped, including the byte-for-byte
synthetic rebuild test (`run_20261019T210001Z_6f7d91`, synthetic evidence only).
Saved-answer matcher check remains 9 claims: 2 matched, 7 needs_review. The
"its security wait times..." sentence still lacks an explicit site mention;
the entity rule was preserved. The lexical fix may miss site-status predicates
with following words other than yet/anymore/now; it is not a grammar parser.

The browser tool refused inspection because workspace 2 remains under user
control after handoff. No login state was verified and no new consumer answer
was collected. Subscription observation run ids: none. Await owner continuation
confirmation, then verify login and collect the ten prompts as manual evidence.
API spend in the refused attempt and continuation: $0. FIELD_STATUS changes:
none. Threshold decision: unchanged, provisional; manual evidence cannot
calibrate API thresholds. SPEC section 7 now records this scope separately.
No commit, push, branch switch or merge; main was not touched.

## Step 19: subscription-only consumer observations (2026-10-31)

The owner confirmed login and authorized continuation. Resumed ego-browser
workspace 2, verified a logged-in Plus session, and used ten fresh conversations,
one per prompt in `step0/data/prompts.json`. GPT-6 was selected in the initial
model menu, Instant effort was visible throughout, and Web search was selected
before every prompt. The backend model identifier is unknown; the manual CLI
snapshot keeps model unknown, with the observed menu label in evidence JSON.
Fresh conversations do not control personalization or location.
Workspace 2 was finished after saving observations. This supersedes Step 18's
pending-handoff state. No browser upgrade was performed.

Evidence type: manual consumer browser UI, not API responses. Exact prompts,
rendered answer text, assistant HTML, observation timestamps, conversation URLs,
visible citation labels and viewport screenshots are under gitignored
`runs/subscription-20261031/evidence/`. `import-manual` used the current
`design/boardflight.facts.json`; every resulting run validated. The three-digit
browser timestamp fraction was padded to six digits without changing its value.
`index.json` maps original prompt ids to runs; each run itself uses p_manual.

| Original prompt | Manual run id |
| --- | --- |
| p_01 | `run_20261031T124757Z_34c1ce` |
| p_02 | `run_20261031T124908Z_54ced6` |
| p_03 | `run_20261031T124922Z_57f67f` |
| p_04 | `run_20261031T124957Z_08b8e3` |
| p_05 | `run_20261031T125013Z_0374d0` |
| p_06 | `run_20261031T125026Z_1e51a3` |
| p_07 | `run_20261031T125047Z_3cef73` |
| p_08 | `run_20261031T125055Z_55b712` |
| p_09 | `run_20261031T125104Z_c1d07f` |
| p_10 | `run_20261031T125120Z_645e2a` |

Read all ten ledgers, saved as `runs/subscription-20261031/p_*.ledger.md`.
There are 4 rule claims: 2 matched and 2 needs_review, with no contradicted,
outdated or unsupported claims. These are ledger counts, not API rates.

- p_09: `clm_chatgpt-web_3a616a2caa104b38` matches airport_count=61 exactly
  (`fct_e9620e441c918ee7`), with an actual .com link.
- p_08: `clm_chatgpt-web_4045f4a7b31a3455` mechanically matches free=true
  (`fct_c48d07d3d8d47a73`), but its surrounding answer is about boardflight.app
  games. Treat it as an entity false positive requiring human review, not a
  correct statement about the airport site. The entity rule reads each sentence;
  this sentence uses only the ambiguous brand. Record retained, code unchanged.
- p_04: `clm_chatgpt-web_b2f55f3ba51819f6` needs_review: its 61-airport
  sentence says "Its website" without naming the site.
- p_10: `clm_chatgpt-web_fdb832d64938a853` needs_review: the status sentence
  "目前狀態：仍在營運。" lacks an explicit site mention.
- p_01 to p_03 do not mention BoardFlight. p_05 describes boardflight.app.
  p_06 describes the .com site as apparently active, and p_07 describes modeled
  waits/no live security queue data; these produce no rule claim because of
  current topic phrases and sentence entity checks. No claim is not validation.

Citation limitation: some grouped source-card URLs could not be reliably
expanded through the UI. Visible labels are preserved, URLs remain explicitly
unknown, and only shown answer links or successfully opened source-card targets
were imported. Imported URL counts are incomplete and must not be interpreted
as citation absence. Screenshots show the viewport, not every part of an answer;
rendered text and HTML preserve the full captured assistant content.

No proposals or confirmations were made, no declared facts or sample facts were
changed, and no API fixtures were exported. FIELD_STATUS changes: none.
Threshold decision: unchanged and provisional; these manual observations cannot
calibrate API thresholds or verify API fields. Actual added API spend: $0.
API P0 remains deferred under the owner's subscription-only instruction.

Task B remains verified complete, with the conservative lexical limitation in
Step 18. Full suite rerun after import: 341 tests, OK, 1 skipped, including the
byte-for-byte deterministic synthetic rebuild. All ten manual runs validate,
match the original prompts and saved answer text, and have no page checks or
decisions. No commit, push, branch switch or merge; main was not touched.

## Step 20: conservative entity guard and saved-evidence recheck (2026-10-31)

The owner asked to finish the remaining work. Fixed p_08's false positive in
matcher v5: same-name other domains elsewhere in the answer or cited hostnames
make brand-only statements needs_review. Explicit allowed-host sentences can
still be decided unless the sentence also names the other entity. No pronoun
resolution, no site-specific patterns, no facts or phrase changes. Normalize
spaces/hyphens for same-name host detection; ignore citation paths/titles.
This deliberately may downgrade correct brand-only statements in comparisons.
It cannot detect an other entity whose domain is absent from saved evidence.

`geo/proposals.py` confirms against the capture's full answer and citations,
so a quote cannot bypass the new guard. Synthetic tests cover ambiguity in
text/citations, contradicted as well as matched values, explicit hosts,
pronouns, unrelated hosts/URL paths, and refused confirmation without writes.
No actual proposals or confirmations were made.

Reimported the exact ten Step 19 observations under
`runs/subscription-20261031/rechecked-v5/`; original `imports/` is intact.
Run ids are the same ten ids in Step 19, because these are the same observations
with original observed_at, not ten additional samples. Captures differ only in
new import created_at; prompts, answers, screenshots and citations are unchanged.
`index-v5.json` maps original/rechecked directories and new claim ids;
`p_*.v5.ledger.md` and `summary-v5.md` explain the result.

Current manual ledger total: 4 claims, 1 matched, 3 needs_review. In
`run_20261031T125055Z_55b712`, former free=true match becomes needs_review
(`clm_chatgpt-web_a59f8b9c1102a076`) because the actual cited host is .app.
In `run_20261031T125104Z_c1d07f`, airport_count=61 remains matched
(`clm_chatgpt-web_6bc0073d442c8daf`). The other two claims retain needs_review;
no original record was edited. All ten reimports validate as manual and contain
no decision. These counts do not enter API rates.

Task B remains complete. The October 30 saved answer still gives 9 claims,
2 matched and 7 needs_review, with its unnamed queue-data sentence undecided.
Regenerated only the deterministic synthetic claims, decision references and
report for matcher v5. Full suite: 346 tests, OK, 1 skipped, including the
byte-for-byte synthetic rebuild check. `git diff --check` passed.

Citation backfill is pending: workspace 2 was finished in Step 19 and is no
longer in the browser inventory. The ego-browser skill requires one space per
goal and no bypass through another space, so the owner was asked whether to
create a replacement space solely to reopen the saved conversations. No new
space was created and no new question was sent while awaiting that choice.
Unknown citation URLs remain unknown; no inferred URLs were added.

API spend: $0. FIELD_STATUS changes: none. Threshold decision: unchanged and
provisional; manual evidence cannot verify API fields or calibrate thresholds.
API P0 remains deferred by the owner's subscription-only scope. Current facts
and sample facts untouched. No commit, push, merge or branch switch; main
untouched. Browser upgrade not performed.

## Step 21: complete citation backfill and final manual imports (2026-10-31)

The owner explicitly allowed a replacement browser workspace. Applied the
ego-browser skill; created workspace 5, reopened the ten stored conversation
URLs, and submitted no new prompts or regenerations. Each full rendered answer
matched the saved answer after normalizing layout whitespace. Cursor position
surviving navigation had prevented hover entry; moving away before hovering,
then using keyboard activation and reloading between source cards, resolved
that UI issue without guessing URLs or reading hidden application state.

All 17 originally saved prose citation groups were expanded, giving 29 opened
source-card occurrences. Each group's count matched its visible +N label.
Actual opened source URLs, labels, original observation times and separate later
backfill timestamps are in `runs/subscription-20261031/citation-backfill/`.
This resolves the citation limitation and workspace blocker in Steps 19 and 20.
Workspace 5 was finished; no browser upgrade was performed.

Imported the same saved answers with the union of original shown links and
backfilled source-card URLs via `import-manual`, current facts, under
`runs/subscription-20261031/complete-v5/`. Original `imports/`, `rechecked-v5/`
and all original evidence remain intact. The final run ids are the same ten
observation ids listed in Step 19, not new samples. `index-final.json` maps all
versions; `p_*.final.ledger.md` and `summary-final.md` are the current review.
Original answer observation timestamps are preserved; later citation expansion
times are supplementary evidence, not falsely assigned to the original capture.

All ten final imports validate as manual with no page checks or decisions.
Captures differ from the first v5 recheck only in citations and import created_at;
claim ids/verdicts are unchanged: 4 total, 1 matched, 3 needs_review. The p_08
privacy citation confirms the answer concerns boardflight.app; its claim remains
needs_review (`clm_chatgpt-web_a59f8b9c1102a076`,
`run_20261031T125055Z_55b712`). The 61-airport answer remains matched
(`clm_chatgpt-web_6bc0073d442c8daf`, `run_20261031T125104Z_c1d07f`).
These are manual ledger counts, not API rates or decisions. Consumer brand
confusion remains a finding; the matcher fix prevents a false positive, it does
not change consumer answers. No real proposals or confirmations were made.

Task B remains complete. Full suite rerun after final import: 346 tests, OK,
1 skipped, including the byte-for-byte deterministic synthetic rebuild. No
further code change was needed for citation backfill. `git diff --check` passed.
API spend: $0. FIELD_STATUS changes: none. Threshold decision: unchanged and
provisional. Current facts and sample facts untouched. No API fixtures exported.
API P0 remains deferred by subscription-only scope, not completed by this work.
No commit, push, merge or branch switch; main untouched. The authorized code,
manual observations and citation backfill are complete; release actions still
require the owner's explicit instruction.

## Step 22: release authorization and integration validation (2026-10-31)

The owner explicitly authorized committing, pushing v0.2, creating a pull
request and merging into main after validation. This supersedes the earlier
no-commit/no-push/no-merge state; subscription-only and no-paid-API scope remain.
Task B and the entity guard are separate commits, each with the requested
ChatGPT co-author trailer. Consumer evidence stays under ignored runs/.

Fetched origin before release: main includes repository-polish changes that
overlap v0.2 in README, packaging metadata and CI, plus moves the build logs
to docs/. Integrated those changes on v0.2, retaining packaged step0 data,
main metadata and the wheel-install smoke test. CI covers Python 3.9, 3.12
and 3.13. The combined offline suite passed: 346 tests, OK, 1 skipped,
including the byte-identical synthetic rebuild. Built the wheel, installed it
in a separate venv and successfully planned a minimal run from outside the
repository without sending requests. Build succeeded with existing setuptools
license-metadata deprecation warnings. README and CHANGELOG reflect v0.2.
The PR records the final CI and merge result. API P0 remains deferred;
API spend $0, FIELD_STATUS unchanged, thresholds unchanged and provisional.
