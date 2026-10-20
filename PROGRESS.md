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
