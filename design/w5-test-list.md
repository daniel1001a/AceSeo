# W5 first test list (DRAFT v1, specification only)

Status: written by W5 (Sonnet tier). No product code, no test code, no API calls. Inputs read: PLAN.md (5, 7, 8, 10), design/w4-data-model.md (2 to 8), design/w3-facts-schema.md, design/boardflight.facts.sample.json, design/step0-prompts.md, research/w1-api-terms.md.

## 0. Ground rules for every test

- Python 3.9+, stdlib `unittest` only, run with `python3 -m unittest discover`. No pytest, no network, no API keys, no environment reads.
- Product code must take its collaborators as parameters so tests can inject them: the provider adapter (mock with a call counter), the HTTP fetcher (returns recorded bytes and headers), the clock (`now`), and the run directory (`tempfile.TemporaryDirectory`). This is a requirement on the design, not on the tests. Without it the tests below cannot run offline.
- Fixtures live under `tests/fixtures/`. Each fixture file is labeled in a sibling comment or name as one of: `RECORDED` (bytes from a real call, with date), `DERIVED` (computed from verified documents, with the document named), `SYNTHETIC` (invented by a test author to exercise logic; never presented as provider output).
- BoardFlight values come only from design/boardflight.facts.sample.json (domain www.boardflight.com; boardflight.app is a different product and only appears as a negative case).
- Provider response bodies (OpenAI, Anthropic, Perplexity) are NOT specified anywhere I read. No test below depends on a provider body shape except through a fixture marked `shape unverified, must be recorded from a real call in Step 0`. Tests W5-01 to W5-08 and W5-10 build capture records directly (post-adapter), so they do not need provider bodies.

## 1. The ten tests

### W5-01 id_replay_and_mismatch

- Module (proposed): ids / validator
- Asserts: a capture id is a pure function of its identity dict, changes when any identity field changes, and a record whose id hash part is altered is rejected.
- Fixture (DERIVED from W4 2.3 and 2.4, golden values computed with `sha256(b"geo-evidence/id/v1\n" + canonical_json(identity))[:16]`, canonical_json = `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`):
  - identity base: `kind=capture, run_id=run_20261019T210000Z_a1b2c3, engine=openai, model=gpt-5-mini, tool_version=test-fixture-1, prompt_id=p_09, prompt_sha256=af69ff9af7bde329e4aeb4827d0cebe6ec3ec37a997b4d9e9d21134d56b63545 (sha256 of NFC "How many US airports does BoardFlight cover?", prompt p09 text from step0-prompts.md), repeat_index=0, attempt=1`
  - expected id base: `cap_openai_fd2c4e200174c266`
  - `repeat_index=1`: `cap_openai_be5a6b9cda16f190`
  - `run_id=run_20261019T210001Z_a1b2c3`: `cap_openai_13adb7f1dc266d22`
  - mutated record: id `cap_openai_fd2c4e200174c260` (last hex digit changed) inside an otherwise valid capture record
- Pass: building base twice yields the same id; the three ids above are exactly as listed; all match RECORD_ID; the validator returns `E_ID_MISMATCH` for the mutated record and no other id-related code. Fail: any difference.
- Covers: W4 T1, T2; V4; F6 replay stability.
- Prevents: ids that drift between replays (breaks "same evidence id, same record") and records that cite an id they do not own.
- Note: the golden values also pin the canonical JSON function. If W4 changes the encoding, these values must be regenerated deliberately.

### W5-02 terms_gate_writer_and_validator

- Module (proposed): capture writer, validator
- Asserts: an engine whose terms are not `verified-allowed` cannot produce a capture, either at write time (no adapter call) or at validation time (hand-edited file).
- Fixture (SYNTHETIC engine snapshots; fields per W4 3.3):
  - Part A: engine snapshot `terms_status=unverified`, mock adapter with call counter, one slot (openai, p_09, repeat 0).
  - Part B: engine snapshot `terms_status=verified-restricted`, a captures.jsonl hand-edited to contain one otherwise valid `ok` capture for it.
  - Part C: engine `perplexity`, `opt_in=true`, run manifest without opt-in, adapter mock.
  - Part D (positive control): `terms_status=verified-allowed`, `terms_retrieved` within `TERMS_MAX_AGE_DAYS`; writer calls the adapter once.
- Pass: A and C: adapter call count 0, captures.jsonl has no line, manifest `skipped_slots` holds the slot with reason `terms_gate`, engine in `engines_excluded`. B: validator returns `E_TERMS_GATE`. D: call count 1, one line written. Fail: any adapter call in A or C, any line written, or B validating clean.
- Covers: W4 T3, T4; V12; PLAN promise "terms-unverified engines cannot write captures".
- Prevents: spending money or collecting data from an engine whose terms do not allow it, and a hand-edited file laundering such data into a report.
- Open: `TERMS_MAX_AGE_DAYS` has no value. Part D uses a `terms_retrieved` equal to the capture date to stay independent of that value. A stale-terms case is deferred until the value exists.

### W5-03 claim_refs_and_verdict_downgrade

- Module (proposed): claims / validator
- Asserts: a claim must reference an `ok` capture, an existing fact, and the exact answer span; verdict and basis must be a legal pair; an LLM matcher may only emit `needs_review`; a claim the rule matcher cannot decide becomes `needs_review`.
- Fixture (SYNTHETIC answer texts; facts from the BoardFlight sample, `llms.coverage.airport_count = 33`):
  - capture C_ok: `status=ok`, `answer_text="BoardFlight covers 40 US airports."`
  - capture C_failed: `status=failed`, `error_class=timeout`, `answer_text=""`
  - Case 1: claim `capture_id=C_failed` -> `E_REF_CAPTURE`.
  - Case 2: claim `fact_key=llms.coverage.airport_count_typo` -> `E_REF_FACT`.
  - Case 3: claim `statement="BoardFlight covers 41 US airports."` vs span text -> `E_CLAIM_SPAN`.
  - Case 4: `verdict=matched, verdict_basis=undecided` -> `E_VERDICT`.
  - Case 5: `matcher=llm, verdict=contradicted, verdict_basis=value_mismatch` -> `E_VERDICT_LLM`.
  - Case 6 (rule matcher, positive): span "covers 40 US airports" vs 33 -> `contradicted` / `value_mismatch`; span "covers 33 US airports" -> `matched` / `exact`.
  - Case 7 (downgrade): answer "BoardFlight covers dozens of US airports." (no parseable number) -> `needs_review` / `undecided`, `fact_key` may be absent.
- Pass: cases 1 to 5 return exactly the listed code; case 6 and 7 return exactly the listed verdict and basis. Fail: Case 7 returning anything but `needs_review`, or any case returning an extra code.
- Covers: W4 T6, T7; V16, V17, V18, V19, V20; PLAN promise "unsure verdicts downgrade to needs_review".
- Prevents: verdicts attached to failed responses, to facts that do not exist, to text the model never wrote; and a guessed verdict presented as decided.
- Caveat: case 7 is the only assertion about matcher behavior; W4 states the pair rule but not when the rule matcher must give up. Treat case 7 as provisional until the lead confirms the rule (see Q3).

### W5-04 failed_excluded_and_exposed

- Module (proposed): aggregation, renderer
- Asserts: failed and refused attempts are out of the rate denominator, are listed on the number, and appear in the rendered report and in `failure_rate`.
- Fixture (SYNTHETIC captures built directly, one engine `openai`, one prompt `p_09`, `repeats=6`, `min_n=3`):
  - slots 0 to 3: `ok`, citations include host `www.boardflight.com` in slots 0 and 1 only
  - slot 4: `failed`, `error_class=timeout`, raw null
  - slot 5: `refused`
- Expected: `citation_rate.engine_prompt` Number `value=2, n=4`, `evidence_ids` = the 4 ok ids sorted, `hit_ids` = slots 0 and 1, `excluded` = slot 4 id (failed) and slot 5 id (refused); `failure_rate.engine` Number `value=2, n=6`; rendered text contains both excluded ids, the string `2/4`, and the string `2/6`; the "Excluded and skipped" section lists both ids.
- Pass: all of the above exactly. Fail: `n=6`, or an excluded id missing from the output, or the section missing.
- Covers: W4 T8; 5.4; 6.1 principle 3; 6.2 rows `citation_rate.engine_prompt`, `failure_rate.engine`; PLAN promise "failed responses excluded from denominators but shown".
- Prevents: a flattering rate computed on survivors only, and failures hidden from the reader.
- Note: Q1 (do refusals stay out of denominators) is assumed answered "yes, excluded and exposed", W4's default.

### W5-05 number_rejects_bad_inputs

- Module (proposed): renderer Number value object
- Asserts: a `Number` without valid n and evidence cannot be built or rendered, and no report file is left behind.
- Fixture (SYNTHETIC; ids from the id function; registry `min_n=3` for `citation_rate.engine_prompt`):
  - N1: `evidence_ids=()` -> `E_EVIDENCE_EMPTY`
  - N2: `n=2`, 3 ids -> `E_N_MISMATCH`
  - N3: `n=2`, 2 ids, `min_n=3` as a `Number` -> `E_N_BELOW_MIN`
  - N4: one id that does not resolve in the sealed run -> `E_EVIDENCE_UNRESOLVED`
  - N5: `min_n=1` where registry says 3 -> `E_MIN_N_OVERRIDE`
  - N6 (positive control): `n=3`, 3 resolving ids, `value=2`, `hit_ids` of size 2 -> renders `2/3`.
- Pass: each of N1 to N5 yields exactly its code, collected in one `RenderError` when rendered together; the output path does not exist after the failure; N6 renders. Fail: any report file exists after a failure, or only the first error is reported.
- Covers: W4 T9; 5.1, 5.3; PLAN promise "every number carries n and evidence ids".
- Prevents: a bare percentage reaching the reader; a threshold quietly lowered by the caller.

### W5-06 renderer_types_labels_footer

- Module (proposed): renderer
- Asserts: label and evidence kind must be compatible, digits cannot enter through free text or raw Python values, and the footer and `not_checked` baseline are emitted by code.
- Fixture (SYNTHETIC):
  - a: `Measured` Number whose evidence id is `src_<16hex>` -> `E_LABEL_MIXED`
  - b: `Estimated` Number with empty `basis_labels` -> `E_LABEL_MIXED`
  - c: `Text("3 of 5 engines")` -> `E_STRAY_DIGIT`
  - d: a bare `int` in a fragment position -> `E_TYPE`
  - e: valid report model with no footer and no `not_checked` supplied by the caller
  - f: same as e but the decision block carries an empty `not_checked`
- Pass: a to d yield exactly their codes. e renders and the output contains the fixed API-model footer constant (assert by importing the constant from the module and checking `in`, not by retyping the sentence) and every baseline `not_checked` item (import the baseline list from code). f fails with `E_NOT_CHECKED_MISSING`. Fail: any caller-supplied footer accepted, or a digit-bearing `Text` rendered.
- Covers: W4 T10, T11; 5.1, 5.2, 5.5; PLAN A7.
- Prevents: unlabeled or mislabeled numbers, hand-typed statistics, and a report that reads as consumer-UI truth because the footer was dropped.

### W5-07 decision_cascade_r1_before_r0

- Module (proposed): decision engine
- Asserts: the cascade evaluates R1 first, so a hard SEO failure wins even with too few captures; thin captures with passing pages give `insufficient_evidence`; an uncheckable blocking page stops the cascade.
- Fixture (SYNTHETIC records; thresholds `N_MIN_REPEATS=3`, `MIN_ENGINES=2`, other placeholders set to any legal values and recorded in `thresholds_snapshot`; key page `https://www.boardflight.com/airport/jfk`):
  - A: page_check `noindex` result `fail`, `blocking_on_fail=true`, `url_role=key`; plus a contradicted claim; captures with 2 ok repeats per prompt.
  - A0: same page_check as A but zero captures.
  - B: all key page checks `pass`; 2 ok repeats per prompt on two engines from different vendors.
  - C: key page check `not_checkable` (reason `timeout`), blocking.
- Expected: A and A0: `outcome=seo_first, fired_rule_id=R1, hypothesis=true`, `A6` and `A7` in `assumption_refs`, `evaluations` in order R1 first. B: `outcome=insufficient_evidence, fired_rule_id=R0, hypothesis=false`. C: `outcome=insufficient_evidence`, R1 evaluation `result=unknown, reason_code=page_checks_incomplete`, R2 to R4 `not_evaluated`.
- Pass: exactly the above, including the `evaluations` order. Fail: A0 returning R0.
- Covers: W4 T12 (A and B), D1, D5, D10; PLAN section on R0 to R4.
- Prevents: "insufficient evidence" masking a real indexing block, and "no action" or "geo" advice given while a key page cannot be fetched.
- Caveat: R2 to R4 firing paths are not tested here (placeholders `K_CONTRA_REPRODUCE`, `T_LOW`, `N_MIN_ENGINE` have no values). They need a second test once the lead picks values.

### W5-08 facts_json_validation

- Module (proposed): facts validator
- Asserts: the validator accepts a well-formed facts file and rejects each broken variant for the intended rule.
- Fixture (DERIVED from design/boardflight.facts.sample.json, copied at test time; `now` injected as `2026-10-19T21:00:00Z`):
  - V0: the sample with `facts` re-sorted by `key` in plain code-point order (see Q1: the committed sample is not sorted), validated with `allow_sample=True` -> valid.
  - V1: V0 validated without `allow_sample` -> refused (rule 15).
  - V2: `site_status` fact `content_hash` changed by one hex digit -> rule 7.
  - V3: a fact `source.locator` host `boardflight.app` -> rule 12.
  - V4: `site_status.value = "inactive"` (not in `enum_values`) -> rule 6.
  - V5: `llms.coverage.airport_count.value = true` -> rule 3 (bool is not integer).
  - V6: facts list left unsorted (the sample's own order) -> rule 4.
  - V7: the JSON text with a duplicated `"key"` member -> rule 1.
  - V8: unknown top-level field `"extra": 1` -> rule 2.
  - V9: `snap-home-200.status_code = 404` while `site_status.value = "live"` -> rule 10.
  - V10: `generated_at` earlier than a fact's `derived_at` -> rule 9.
  - V11: `generator` removed -> rejected (hand-written file).
- Pass: V0 returns no errors; V1 to V11 each return a non-empty error list that names the expected rule number (see Q2: W3 defines rules, not error codes) and nothing for unrelated rules. Fail: any variant validating clean, or V0 failing.
- Covers: W3 section 4 rules 1 to 4, 6, 7, 9, 10, 12, 15 and the reject list; PLAN promise "facts.json validation"; PLAN section 7 facts.json target.
- Prevents: ground truth for the Claim Ledger being a hand-typed, stale, mis-hashed, or wrong-domain file (the exact boardflight.app confusion that motivated W3).

### W5-09 page_check_parsing

- Module (proposed): page checks
- Asserts: robots.txt is evaluated per AI crawler, noindex is detected from header and meta (and only from there), redirect chains are recorded, and key content is checked in the raw HTML without JS.
- Fixture (mix; each labeled):
  - R-A (SYNTHETIC robots.txt): `User-agent: GPTBot` / `Disallow: /`, then `User-agent: *` / `Disallow: /api/`, `Disallow: /?f=`, then `Sitemap: https://www.boardflight.com/sitemap.xml`. The `/api/` and `/?f=` lines and the Sitemap URL mirror what W3 V5 observed on boardflight.com; the GPTBot group is invented.
  - Expected on R-A for `https://www.boardflight.com/airport/jfk`: GPTBot blocked; every other listed crawler allowed; for `/api/x` all other crawlers blocked; sitemap list equals the one URL.
  - R-B (RECORDED in Step 0): the real `https://www.boardflight.com/robots.txt` body with its sha256. Expected: no AI crawler blocked on `/airport/jfk` unless the recorded file says otherwise (the expectation is written after recording, not guessed now).
  - H1 (SYNTHETIC): response header `X-Robots-Tag: noindex` -> `fail`. H2: meta `<meta name="robots" content="NoIndex, follow">` -> `fail` (case-insensitive). H3: `<meta name="robots" content="index, follow">` -> `pass`. H4: body text `<p>add noindex to private pages</p>` and no meta/header -> `pass` (false-positive guard).
  - Redirect: DERIVED from sample snapshot `snap-home-200`: request `https://boardflight.com/`, one hop `308 -> https://www.boardflight.com/`, final 200. Expected: `redirect_chain` has exactly that one entry, `final_url=https://www.boardflight.com/`, `result=pass`. Chain of 5 hops all 3xx then 200 -> recorded, pass.
  - Raw HTML content (SYNTHETIC): `key_content` expected string `John F. Kennedy International` (this string occurs on llms.txt line 21 per the sample, not verified for the HTML page). HTML-1 contains it in server HTML -> `pass`. HTML-2 is an empty shell `<div id="root"></div><script src="/app.js"></script>` -> `fail`.
  - Fetch failure: fetcher raises timeout -> `result=not_checkable`, `not_checkable_reason` non-empty, `raw_sha256=null`.
- Pass: every expectation above. Fail: H4 flagged noindex, a `*` group applied to GPTBot when a GPTBot group exists, or a timeout recorded as `pass`.
- Covers: PLAN section 6 page checks list (robots per AI crawler, noindex, redirect chain, key content in raw HTML) and section 7 target; R1 inputs; W4 3.4.
- Prevents: R1 firing wrongly (false SEO block) or silently missing a real block, and a failed fetch being scored as healthy.
- Note: assertions are on the check result, not on the parsing mechanism. Avoid precedence-dependent robots.txt rules (Allow versus Disallow overlap, wildcards) in this test; their semantics differ between `urllib.robotparser` and RFC 9309 and I did not verify the difference (Q5).

### W5-10 cost_estimate_vs_w1_prices

- Module (proposed): cost estimator
- Asserts: the dry-run estimate equals the W1 price table arithmetic in Decimal, and a run over the cap is flagged before any call.
- Fixture (DERIVED from research/w1-api-terms.md price table; token counts and 1 search per call are SYNTHETIC planning inputs, because assumption A8 is unmeasured). Per 1M tokens:
  - `gpt-5-mini`: input 0.25, output 2.00, search 10 per 1k
  - `claude-haiku-5-5`: input 0.10, output 0.50, search 10 per 1k
  - `perplexity/sonar`: input 0.25, output 2.50, search 2.50 per 1k (standard preset)
- Inputs per call: 1000 input tokens, 500 output tokens, 1 search.
- Expected per call: openai 0.01125, anthropic 0.01035, perplexity 0.00400. Per engine for 30 calls (10 prompts x 3 repeats): 0.3375, 0.3105, 0.12. Search fees alone for 30 calls: 0.30, 0.30, 0.075. OpenAI plus Anthropic 0.648; all three 0.768. Cap case: cap_usd `0.30` with openai 30 calls -> over cap (0.3375 > 0.30), flagged before any adapter call (adapter mock call count 0). Cap `1.00` with all three -> within cap.
- Pass: Decimal results equal exactly (compare as Decimal, not float; the stored form is a decimal string like `"0.01125"`); over-cap case raises or returns `over_budget` with zero adapter calls. Fail: any float in the output, any adapter call before the cap check.
- Covers: PLAN cost estimate and $1 cap; W4 V15, `budget`; W1 price table.
- Prevents: surprise spend on the first paid run and a price table that drifts from the cited source without the test noticing.
- Caveat: if the W1 table changes, this test must be edited on purpose. The 1-search-per-call assumption and the token counts are unverified (see section 5).

## 2. W4 invariant mapping

| Invariant | Covered by | Note |
|---|---|---|
| T1 id_replay_stable | W5-01 | golden ids included |
| T2 id_mismatch_rejected | W5-01 | |
| T3 terms_gate_writer | W5-02 part A, C | |
| T4 terms_gate_validator | W5-02 part B | |
| T5 raw_hash_tamper | deferred | Needs seal and `E_SEAL_MISMATCH`; PLAN section 9 defers seal. Cheap partial add if the raw writer exists in Step 1: flip one byte of a raw file and expect `E_RAW_HASH` (V7) with no seal involved. |
| T6 claim_refs | W5-03 cases 1 to 3 | |
| T7 verdict_downgrade | W5-03 cases 4, 5, 7 | |
| T8 failed_excluded_and_exposed | W5-04 | |
| T9 renderer_rejects_bad_numbers | W5-05 | |
| T10 renderer_label_and_type | W5-06 a to d | |
| T11 footer_and_not_checked | W5-06 e, f | |
| T12 decision_cascade | W5-07 A and B (plus A0, C) | |

PLAN-only promises covered outside the T list: facts.json validation W5-08, page-check parsing W5-09, cost estimate W5-10.

## 3. Recommended implementation order

Lowest dependencies and highest leverage first. "PLAN step" is from PLAN section 8 for the T invariants only; W5-08 to W5-10 are not mapped in my notes.

1. W5-01 ids (PLAN step 1). Pure functions; everything else cites ids.
2. W5-05 Number rejects (step 1). Defines the value object.
3. W5-06 renderer types, labels, footer (step 1).
4. W5-08 facts validation. Independent module; unblocks claim fixtures and Step 0 prompts p04, p06, p09, p10.
5. W5-10 cost estimate. Needed before the first paid call (Step 0 dry run).
6. W5-02 terms gate (step 3). Must pass before any adapter touches the network.
7. W5-09 page checks. Feeds R1.
8. W5-03 claims (step 5).
9. W5-04 aggregation (step 6).
10. W5-07 decision cascade (step 6). Last because it consumes page checks, aggregation and Numbers.

Rough size: W5-01, 05, 10 small; W5-02, 04, 06, 07 medium; W5-03, 08, 09 medium to large (many cases, small each).

## 4. Fixtures that must be recorded in Step 0

Everything here is RECORDED from real calls or fetches and stored with date, request URL and sha256. None exists yet.

| Fixture | Used by | Why it cannot be invented |
|---|---|---|
| OpenAI response body for p09 (shape unverified, must be recorded from a real call in Step 0) | adapter tests (not in the ten) | Body, citation field and `usage` fields are not documented in my inputs |
| Anthropic response body for p09 (shape unverified, must be recorded from a real call in Step 0) | same | same |
| Perplexity response body for p09 (shape unverified, must be recorded from a real call in Step 0) | same | same |
| A refusal or empty-answer body from any engine (shape unverified, must be recorded from a real call in Step 0) | `refused` mapping (Q5 in W4) | no documented refusal field |
| A provider error body (rate limit or auth) | `failed` mapping | no documented error shape |
| Billed-cost field, if any provider returns one | W5-10 follow-up (U2) | unknown whether it exists |
| Real `https://www.boardflight.com/robots.txt` body | W5-09 R-B | W3 recorded only three facts about it (disallows `/api/` and `/?f=`, one sitemap line) |
| Raw HTML of `https://www.boardflight.com/airport/jfk` | W5-09 key content | Whether any candidate `key_content` string is in the raw HTML is unverified |
| Headers of `/airport/jfk` (any `X-Robots-Tag`) | W5-09 | not in the sample |
| The original AI Overview text claiming the site is inactive, if the user has it | W5-03 first real claim fixture | step0-prompts.md notes nobody on the project has seen it |

## 5. Unverified assumptions

1. A8: token counts for the cost test are invented; the 1 search per call may not hold (a provider may run several searches per call).
2. Canonical JSON in W5-01 matches W4 2.1 exactly; golden values were computed by me from W4's text, not from product code.
3. Prompt ids: W4 3.3 requires `^p_[a-z0-9_]{1,40}$` but step0-prompts.md uses `p01` to `p10`. W5-01 uses `p_09`. This is a spec conflict, not a test choice (Q4).
4. The AI crawler name list for W5-09 (for example GPTBot, ClaudeBot, PerplexityBot, Google-Extended) is from general knowledge, not from a document in this project. The registry list must be verified against each vendor's published crawler documentation before the test pins it.
5. The stdlib robots.txt parser handled case-insensitive `GPTBot`, fallback to the `*` group and `Sitemap` lines in a quick local check; wildcard and precedence behavior was not checked.
6. The price table in W5-10 is the W1 table as I read it; I did not re-fetch vendor pages.
7. `TERMS_MAX_AGE_DAYS`, `N_MIN_ENGINE`, `K_CONTRA_REPRODUCE`, `T_LOW` have no values; tests avoid depending on them.
8. Module names and the injected-collaborator design are proposals; PLAN does not fix them in the sections I read.
9. Case 7 of W5-03 and the BoardFlight `key_pages` / `key_content` values are test-author choices, not specified behavior.

## 6. Open questions for the lead

- Q1. design/boardflight.facts.sample.json violates W3 rule 4 (facts sorted by `key`): it lists `site_status` before `site.canonical_host` and `llms.*`, `jsonld.*` after. Under code-point order `.` (0x2E) sorts before `_` (0x5F) and `j` before `l` before `s`, so the file is unsorted. Either fix the sample, or W3 states a different sort rule. W5-08 V0 re-sorts at test time; V6 uses the committed order as the negative case.
- Q2. W3 section 4 defines rules by number but no error codes. W5-08 asserts on rule numbers. Should W3 assign codes (as W4 does)?
- Q3. When must the rule matcher emit `needs_review`? Needed to make W5-03 case 7 non-provisional. Also: W3 3.3 mentions a `wrong_entity` outcome for claims about other domains; W4 has five verdicts and no `wrong_entity`. Which wins?
- Q4. `prompt_id` grammar (`p_..`) versus step0-prompts.md (`p01`..`p10`).
- Q5. Which robots.txt semantics are authoritative: stdlib `urllib.robotparser` or RFC 9309 longest-match? Decides whether precedence cases can be added to W5-09.
- Q6. BoardFlight `manifest.key_pages` and `key_content` values (D4). W5-07 and W5-09 use `/airport/jfk` as a placeholder.
- Q7. Redirect chain longer than 5 (W3 fetch limit): `fail` or `not_checkable`? Not tested until decided.
- Q8. Step 0 repeats versus `N_MIN_REPEATS` (D3). W5-07 case B encodes the answer "2 repeats with min 3 gives R0", which holds under either option but changes what Step 0 can show.

## 7. Fallback if the list is too heavy

Cut to six tests, keeping the promises that cannot be recovered by inspection:

1. W5-05 (every number carries n and evidence ids) with the N3 and N5 cases dropped.
2. W5-02 parts A and B only (terms gate).
3. W5-04 (failures excluded and exposed).
4. W5-03 cases 4, 5, 7 only (verdict downgrade, no span or ref checks).
5. W5-07 cases A, A0, B only (R1 before R0).
6. W5-10 per-call values only (three Decimal equalities, no cap case).

Defer W5-01 (golden ids; replace by one assertion that the same inputs give the same id), W5-06, W5-08 and W5-09 until their modules exist; each of those can be started with a single positive and a single negative case. If even that is too much, run only items 1, 2 and 3 first, since they guard the user-facing trust claims (numbers, terms, failures).
