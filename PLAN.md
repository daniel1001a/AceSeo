# PLAN.md (DRAFT v0.3)

Status: draft. No product code exists. Lead decisions 1 to 5 of 2026-10-19 are applied (section 0.2). Step 0 tooling (dry-run, cost estimator, request builder) may start; product modules A to D may not.

Working name: `geo-evidence`.

## 0. Changes since v0

Lead decisions applied: Anthropic default `claude-haiku-5-5` (`claude-haiku-4-5-20251001` legacy); Perplexity via Agent API with explicit `model: "perplexity/sonar"`, opt-in; MVP defaults enable only OpenAI and Anthropic; "mcp-geo" is AKzar1el/mcp-geo; W3 and W4 started, W5 waits for this draft.

New in v0.1:
- W3 result: facts.json schema, 8-fact BoardFlight sample, export-flow recommendation (`design/w3-facts-schema.md`, `design/boardflight.facts.sample.json`).
- W4 result: data model, evidence id grammar, renderer contract, aggregation rules, decision record, 12 test invariants (`design/w4-data-model.md`).
- Step 0 prompt list v1 (section 6 and `design/step0-prompts.md`).
- Correction: the BoardFlight domain is `www.boardflight.com`. I had written `boardflight.app` as a likely domain in the W3 brief without verifying it; W3 found it is an unrelated product, and I confirmed with curl.
- Sections 4.4, 4.5, 4.6 and 5 revised; section 9 carries the open decisions.

## 0.1 Changes in v0.2 (W5 and lead decisions)

- Lead decisions: Step 0 uses 3 repeats; BoardFlight facts come from live URLs only (D4a).
- W5 (Sonnet worker) delivered `design/w5-test-list.md`: 10 test specs (W5-01 to W5-10, stdlib unittest, offline fixtures), a mapping of all 12 W4 invariants (T5, raw hash tamper with seal, is deferred because the seal is deferred), implementation order W5-01, 05, 06, 08, 10, 02, 09, 03, 04, 07, a 6-test fallback cut, and a list of fixtures to record in Step 0. Specification only, no code. I read the report and checked two of its claims against the files (below); I have not read the full 26 KB spec line by line.
- Fixed by me after W5 found them: `design/boardflight.facts.sample.json` violated W3's own rule 4 (facts sorted by key), now sorted (still 8 facts). Prompt ids renamed `p01..p10` to `p_01..p_10` to match W4's grammar `^p_[a-z0-9_]{1,40}$`.
- Still open from W5: W3 mentions a `wrong_entity` outcome that W4's five verdicts do not have; W4 does not say when the rule matcher must give up (so the "dozens" to `needs_review` case is provisional); the AI crawler user-agent list (GPTBot, ClaudeBot and similar) comes from general knowledge, not a project document; the test code needs the adapter, HTTP fetcher, clock and run directory passed in as parameters (a design requirement); no provider response shape is documented, so those fixtures must be recorded from real calls in Step 0; thresholds `TERMS_MAX_AGE_DAYS`, `N_MIN_ENGINE`, `K_CONTRA_REPRODUCE`, `T_LOW` have no values, so the R2 to R4 firing paths and stale-terms case are untested; cost-test token counts are invented planning inputs (A8).

## 0.2 Changes in v0.3 (lead decisions of 2026-10-19)

1. Inactive-domain source located: `~/Projects/boardflight/docs/SEARCH-ENTITY-RECOVERY.md`, "Measured: 2026-09-08", last commit `cc93f59` on 2026-09-08. I read sections 0 to 3 Step 2. Quote (section 1, live SERP for query `boardflight.com`): Google's AI Overview stated that "Boardflight.com is an inactive domain … currently has no active live service or verified platform." Same day, `boardflight.app` held results #1 and #3 for that query. See 3.5 and 6.2.
2. W3 follow-up approved, capped at 3 facts, plus an optional `prior_values` field (5.6.1).
3. `key_pages` and `key_content` defined (5.7.1). I checked on 2026-10-19 around 21:18Z that all three pages return 200 and that the content rule passes on the live raw HTML with a stdlib parser.
4. p_04 wording unchanged until Step 0 results are in (6.1 note).
5. W4 build scope cut to a minimal subset (5.4.1); everything else is deferred.
6. Correction to D4 and A9: a local clone of the BoardFlight repo exists at `~/Projects/boardflight`, so repo-derived facts are readable read-only. I have read only `docs/SEARCH-ENTITY-RECOVERY.md`; no `lib/` file.

## 1. Worker tiers and review depth

| Work | Tier | What I verified |
|---|---|---|
| W1 API terms, W2 competitors | strong-reasoning workers (v0) | Read both reports in full; did not re-verify their sources. |
| W3 facts schema and sample | Sonnet worker | Read schema lines 1-35 only. Spot-checked the sample against the live site and confirmed it parses with 8 facts (308 to www, airport count 33, JFK worst wait 30). Not checked: the other facts, hashes, the 15 validation rules. |
| W4 data model | Opus worker | Read lines 331-528 (renderer contract, aggregation, decision mapping, invariants, open questions, required PLAN changes). Not read line by line: sections 1 to 4 (storage, id hashing, field tables, validator rules). |
| Step 0 prompts, this document | Sonnet 5.5, main thread | Lead draft, not reviewed by anyone else. |
| W5 test list | Sonnet worker | Read its hand-back report; checked sample sort order and prompt id grammar against files. Spec not read line by line. |

## 2. Goal and non-goals

A local-first, open-source, rule-first CLI that:
1. Runs basic traditional SEO and AI-crawler-access checks on a site.
2. Captures answers and citations from AI engines through official APIs only.
3. Compares AI claims about the site with facts generated by code (Claim Ledger).
4. Recommends whether to prioritize traditional SEO or AI/GEO work, citing evidence ids.

Non-goals: black-box scores or predictions, scraping consumer chat UIs, auto-editing the site, composite "GEO scores" with invented weights, becoming an all-in-one suite, default-on telemetry.

Constraints (from brief): Python 3.9+ standard library only, new standalone repo, every number traceable to evidence ids, unclear terms mean `unverified` and writing stops.

## 3. Verified facts (with source)

Full detail, quotes and URLs: `research/w1-api-terms.md`, `research/w2-competitors.md`, `design/w3-facts-schema.md`.

### 3.1 Engine terms (W1, retrieved 2026-10-19)

| Engine | Classification | Basis |
|---|---|---|
| OpenAI Responses API + `web_search`, `gpt-5-mini` | VERIFIED-ALLOWED | Services Agreement 4.1, customer owns Output. No storage or analysis restriction found. Citations must be clearly visible and clickable when shown to end users. |
| Anthropic Messages API + `web_search` | VERIFIED-ALLOWED | Commercial Terms, customer owns Outputs. Citations must accompany displayed outputs. AUP (effective 2026-11-12) bars manipulating sources AI systems draw answers from. |
| Perplexity Agent API (`POST /v1/agent`) | VERIFIED-ALLOWED with caveats | API Terms 2.3.1, customer owns Output. AUP "competitive/similar" and "service bureau" clauses are a judgment call. Third-party model terms stack. Do not use `/search` (customer does not own that Output). |
| xAI (Grok) | UNVERIFIED, OFF | AUP bans "harvesting" Input or Output; undefined for systematic storage. |
| Gemini grounding with Google Search | VERIFIED-RESTRICTED, EXCLUDED | Terms forbid caching, analyzing or learning from Grounded Results. |

Nuance: for OpenAI, Anthropic and Perplexity no clause expressly permits storing or analyzing Output. "ALLOWED" rests on Output ownership plus absence of a restricting clause (A1).

### 3.2 Model and API changes versus the brief

- Anthropic `claude-haiku-4-5-20251001` is Active but its retirement window opened 2026-10-15. Default: `claude-haiku-5-5` ($0.10 in / $0.50 out per 1M tokens, retirement not before 2027-10-07); 4.5 stays as a legacy option.
- Perplexity Sonar Chat Completions support ended 2026-09-27. Sonar maps to the Agent API `fast` preset, which runs `openai/gpt-6-luna` (OpenAI terms stack, and it is not independent of OpenAI). Call the Agent API with explicit `model: "perplexity/sonar"` plus `web_search`. Sonar carries the Meta Llama license as a third-party term.
- `gpt-5-mini` is still listed and supported (snapshot `gpt-5-mini-2025-08-07`) although OpenAI recommends newer models.

### 3.3 Pricing (W1)

Search calls: OpenAI $10 per 1k, Anthropic $10 per 1k, Perplexity $2.50 per 1k (standard) or $1 per 1k (fast), plus tokens. Tokens per 1M: gpt-5-mini $0.25 in / $2.00 out; claude-haiku-5-5 $0.10 / $0.50; perplexity/sonar $0.25 / $2.50.

### 3.4 Competitive position (W2)

Repos checked: elmohq/elmo, oneglanse/oneglanse, AKzar1el/mcp-geo, ansvisor/ansvisor, codextde/autoseo. None of the five differentiators is unique alone. Not found in any of the five: facts extracted by code from the site itself, plus a per-run machine-emitted "not checked" list. The combination (official APIs only, n enforced in code, code-extracted site facts, per-run not-checked list, explicit SEO-vs-GEO call, local-first, no account) is the defensible position.

Borrow: Elmo number labels (Measured / First-party / Published / Estimated) and "rates not ranks"; mcp-geo failed-response handling; AutoSEO verdict taxonomy and downgrade of unsure verdicts to `needs_review`; Ansvisor "Why this priority?" and independent-evidence confidence. Avoid: composite scores, UI scraping, mixing simulated with measured data, suite scope creep.

### 3.5 BoardFlight observations (W3, live GET on 2026-10-19 around 20:45Z)

- Real site: `https://www.boardflight.com`. Apex `boardflight.com` returns 308 to www, then 200 (108119 bytes). I confirmed this with curl.
- `https://boardflight.app` is an unrelated product (W3 V8, V9). W3 hypothesises the AI Overview "inactive" claim comes from this name collision. The claim text is now available second-hand from the BoardFlight recovery doc (0.2 item 1), which also records that `boardflight.app` held #1 and #3 for the query `boardflight.com` and that the `Organization` node had no `sameAs` at the time. This supports A10 but does not prove the cause.
- Live 2026-10-19: `Organization.sameAs` on `/` and `/airport/jfk` lists `https://www.linkedin.com/company/boardflight-fly` and `https://github.com/daniel1001a/boardflight-airport-wait-data`.
- `/llms.txt` (2964 bytes) says: covers 33 US airports; security wait at the 88th percentile; 16 airports pass the TSA shape check; JFK worst wait about 30 min; "Free, no account".
- `/airport/jfk` has two JSON-LD blocks; `iataCode` JFK; `dateModified` 2026-08-25.
- Repo `daniel1001a/boardflight` is private; W3 could not read it. A public repo `daniel1001a/boardflight-airport-wait-data` exists but was not read. `/llms.txt` line 30 says "12 airports" for that dataset while other lines say 33 (or 8), an unresolved inconsistency inside the site's own file.

## 4. Unverified assumptions

| # | Assumption | How to settle |
|---|---|---|
| A1 | Storage and analysis are allowed where Output is customer-owned and no restricting clause exists | Counsel or provider confirmation; re-check monthly |
| A2 | Perplexity use for a GEO evidence tool is not "competitive/similar" | Judgment call; stays opt-in |
| A3 | Each user's own API key makes them the Customer, so distributing an open-source tool does not make us a reseller | Structural inference, not a quoted term |
| A4 | Citation display rules apply only when answers are shown to end users | Render URLs in all reports as a precaution |
| A5 | Anthropic 30-day retention status of Haiku | Not checked |
| A6 | Basic indexability is a prerequisite for AI citation, so SEO-first is right when it fails | Hypothesis; label as hypothesis in output |
| A7 | API answers approximate what users see | Known weak (W2 cites 21.3% to 31.6% brand overlap between API and UI); label as API-model behaviour |
| A8 | Token cost per search call is small enough for the budget | Measure in Step 0 |
| A9 | BoardFlight facts can be exported by a read-only script | Local clone exists (0.2 item 6); W3 export flow still unread against `lib/` |
| A10 | The "inactive" claim comes from the boardflight.app collision | Claim text now quoted from the recovery doc (second-hand; no screenshot or raw capture). Cause stays a hypothesis; p_04, p_06, p_10 test whether API models repeat it |
| A11 | W3 stability classes (static / changes_daily / changes_per_deploy) are right | W3 assigned them without reading code |

## 5. MVP scope

### 5.1 Modules

| Module | Input | Output | Depends on |
|---|---|---|---|
| A. Page checks | URL list from config (`key_pages`, `key_content`) | `page_check` records with raw HTTP status, headers, body hash, parsed fields | none |
| B. Capture | prompt list + engine config | `capture` records with raw response, model, tool version | engine terms status |
| C. Claim Ledger | captures + `facts.json` | `claim` records with verdict | A, B, facts |
| D. Decision | A, B, C aggregates | `decision` record: outcome + rule id + evidence ids | A, B, C |

### 5.2 Page checks (first set)

HTTP status and redirect chain, robots.txt rules per AI crawler, `noindex`/`nosnippet`, canonical, title/meta description presence, key content present in raw HTML (no JS), `llms.txt` presence (reported, not scored), JSON-LD parse validity, sitemap reachability. Every check stores the raw response it derives from. A check that cannot run is `not_checkable` with a reason.

### 5.3 Engine config (revised per W4)

Per engine: `enabled`, `opt_in`, `model_vendor` (for independence grouping; Perplexity `perplexity/sonar` vendor is open question Q8), `terms_status` (verified-allowed / verified-restricted / unverified), `terms_url`, `terms_last_updated`, `terms_retrieved`, a maximum terms age (value to be decided), `model`, `tool_version`, `price_snapshot` with sources. Engines that are `unverified` or `restricted` cannot produce captures; enforced twice: by the writer before the adapter runs, and by the validator. Defaults: OpenAI and Anthropic on; Perplexity opt-in; xAI off; Gemini grounding not implemented.

### 5.4 Data model (summary; `design/w4-data-model.md` is authoritative)

- Storage: one directory per run, append-only JSONL, raw responses as files named by their own sha256, run closed by `SEAL.json` holding the hash of every file. Reports render only from sealed runs. No floats, NaN or duplicate keys; money as decimal strings. A sqlite index may be added later as a rebuildable cache.
- Evidence ids replace the v0 timestamp ids: `^(cap|pc|clm|dec)_<slug>_[0-9a-f]{16}$`, the hash taken over a fixed identity field set per kind (for captures: run_id, engine, model, prompt hash, repeat_index, attempt). Replaying a run reproduces ids; a new run produces new ids; a collision is a hard error. Reference-only kinds: `fct_` (facts.json entries) and `src_` (published sources), so First-party and Published numbers also cite evidence.
- `capture`: adds `run_id`, `identity_sha256`, `schema_version`, `attempt`, `repeat_index` (replaces `run_index`), engine snapshot, prompt/request/raw hashes, usage, `error_class`; cost split into `cost_estimate_usd`, `cost_from_usage_usd`, `cost_billed_usd`.
- `page_check`: adds check version, URL role, agent profile, final URL, HTTP status, redirect chain, headers, raw hash, `blocking_on_fail`, `not_checkable_reason`.
- `claim`: span offsets (stored statement must equal that slice of the answer), `fact_ref`, snapshot of the fact value, `facts_sha256`, `verdict_basis`, matcher version. An LLM matcher can only emit `needs_review`; `outdated` needs prior values in facts.json, otherwise such cases are `contradicted`.
- `decision`: no decision-level n or label. Instead: outcome, fired rule, `evaluations[]`, `numbers[]` (each with its own n and label), `hypothesis`, `assumption_refs`, `confidence_basis`, `thresholds_snapshot`.

### 5.4.1 W4 minimal build subset (decision 5)

Build now:
- Four record kinds, JSONL, one directory per run: `capture`, `page_check`, `claim`, `decision`. Raw responses stored as files named by sha256, because every number must trace back to the raw bytes.
- Evidence id grammar `^(cap|pc|clm|dec)_<slug>_[0-9a-f]{16}$` with identity hashing as in W4, plus reference-only `fct_` ids. Collision is a hard error. Replay gives the same ids.
- One enforced constraint for numbers: an aggregate can only be built as a frozen `Number` with `value`, `n`, and a non-empty `evidence_ids` list whose ids all exist in the run. Missing n, empty evidence, an unknown id, or n below `min_n` raises; below `min_n` renders as `Insufficient (n=k)`. Report text with a bare digit outside a `Number` is rejected (`E_STRAY_DIGIT`).
- Terms gate: an engine whose `terms_status` is not `verified-allowed` cannot produce a capture, and the writer stops. Same rule for any unclear term: mark `unverified`, write nothing.

Deferred: `SEAL.json` and tamper test T5, salvage mode, the other W4 error codes, the full typed-fragment set (only `Text`, `Number`, `Insufficient`, `EvidenceRef`, `Url` now), `src_` ids, independence groups other than `vendor:` and `site:`, sqlite index, three-way cost split (keep `cost_estimate_usd` and `cost_from_usage_usd`).

### 5.5 Aggregation and renderer (summary of W4 sections 5 and 6)

- Unit is the slot (engine, prompt_id, repeat_index). Only `ok` captures count. Failed, refused and skipped slots are excluded from denominators but always listed. Statistics are rates, never ranks; below `min_n` becomes `Insufficient`.
- Independence groups: `vendor:` for captures, `site:` for page checks and URL facts, `repo:` for repo facts, `published:` for sources. Perplexity `fast` is not independent of OpenAI.
- The renderer accepts only typed fragments (`Text`, `Number`, `Insufficient`, `EvidenceRef`, `Quote`, `Url`, `ConfigLiteral`, `Timestamp`). Digits reach output only through a frozen `Number` (statistic id, kind, value, n, min_n, evidence ids, hit ids, excluded, label, basis labels, window, scope); a stray digit in `Text` is an error (`E_STRAY_DIGIT`). 14 error codes, no warnings, no force flag; a failed render writes no file. The renderer itself appends `not_checked[]`, the excluded responses, and the footer "API-model behaviour, not consumer app users".

### 5.6 facts.json (summary of `design/w3-facts-schema.md`)

Versioned JSON: header (schema version, site and allowed hosts, generator, generated_at, source snapshots with sha256 and byte counts) plus facts. Each fact: stable dotted key, value, value type, source (kind, locator, line or JSON path), derived_at, derivation rule, content hash, verification, stability class. 15 validation rules, including rejecting facts about hosts outside `site.hosts`. Generated by code, never hand-written.

Sample (`design/boardflight.facts.sample.json`, hand-assembled and labelled so, 8 facts): `site_status` = live (GET apex, 308 then 200), `site.canonical_host` = www.boardflight.com, `llms.coverage.airport_count` = 33, `llms.security_wait.percentile` = 88, `llms.tsa_check.passing_airports` (16 airports), `llms.data_study.jfk.worst_wait_minutes` = 30, `jsonld.airport.jfk.iata_code` = JFK, `jsonld.airport.jfk.page_date_modified` = 2026-08-25.

W3 export-flow recommendation exists in section 6 of its document; not yet checked against the local clone. Gaps before the follow-up: no pricing, account or data-source facts (p_07 and p_08 have nothing to score against); no prior values for `outdated`.

### 5.6.1 W3 follow-up (approved, max 3 facts)

Candidates, each traced to a line I read on 2026-10-19 (`/llms.txt`, 200, 2964 bytes, same size as W3's fetch):

| key | value | source | prompts |
|---|---|---|---|
| `llms.offer.is_free` | true | `/llms.txt` line 3: "Free, no account." | p_08 |
| `llms.data.uses_live_queue_data` | false | `/llms.txt` line 5: "It uses no live queue data." | p_07 |
| `jsonld.organization.same_as` | the two URLs in 3.5 | JSON-LD `Organization.sameAs` on `/` | p_04, p_06, p_10 |

Left out to stay within 3: `llms.offer.account_required` = false (same line 3; first one to add if the cap is lifted).

`prior_values` (optional, per fact): list of `{value, valid_until, source}`. A source is required; a prior value without one is invalid. Claim verdict `outdated` only when the claim equals a sourced prior value; otherwise a disagreeing claim stays `contradicted`. This replaces W3's history-directory idea for the MVP. Candidate first use: `jsonld.organization.same_as` prior value "absent", per the recovery doc section 2 ("`BRAND_PROFILE_URLS` began empty"). To verify before use: the git history of `lib/seo/identity.ts` in the local clone (not read yet). If it cannot be verified from code, the fact ships without `prior_values`.

### 5.7 Decision rules (revised per W4 D1 to D10; thresholds are placeholders)

Evaluation order: R1 first (needs no captures), then R0 as the gate for R2 to R4.

| Rule | Condition | Outcome |
|---|---|---|
| R1 | A blocking failure among `manifest.key_pages` checks (non-200, noindex, robots block, `key_content` absent from raw HTML). If a blocking check is `not_checkable` the result is unknown and the cascade stops with `insufficient_evidence` (`page_checks_incomplete`). | SEO first, labelled hypothesis (A6, A7) |
| R0 | Fewer than `MIN_ENGINES` (2) independent vendor groups have a sufficient engine-level rate | `insufficient_evidence` |
| R2 | Page checks pass and a rule-matched `contradicted` or `outdated` claim tied to a `fact_key` reproduces in at least `K_CONTRA_REPRODUCE` ok captures (placeholder) | GEO: fix source-of-truth pages and structured facts |
| R3 | Page checks pass, R2 not fired, `citation_rate.engine` below `T_LOW` (placeholder) in at least 2 distinct vendor groups, each with n at least `N_MIN_ENGINE`; mention rate reported, not decisive | GEO content work, labelled hypothesis |
| R4 | R0 not fired, R1 not unknown, none of R1 to R3 fired | No action; monitor |

Every outcome lists evaluated rules, ids read, `not_checked[]`, and a "Why this rule fired" section generated from fields only. No composite score. Confidence is the list of independent evidence groups, not a number.

### 5.7.1 BoardFlight `key_pages` and `key_content` (decision 3)

| page | key_content rule (raw HTML, no JS) | live result 2026-10-19 |
|---|---|---|
| `/` | Exactly one `<h1>` with non-empty text, and the first `<p>` after it with at least `MIN_PARA_CHARS` characters of whitespace-collapsed text | h1 "Know exactly when to be at the airport"; first paragraph starts "Every airport runs differently…" |
| `/airport/jfk` | Same rule | h1 "How early should you arrive at John F. Kennedy International?"; first paragraph starts "For a typical domestic flight out of JFK, plan to reach the airport 84–103 minutes…" |
| `/llms.txt` | HTTP 200 and a line matching `Covers <digits> US airports` | line 3 "Covers 33 US airports." |

`MIN_PARA_CHARS` is a placeholder; I used 40 in the spot check. A naive regex for "first `<p>`" picked up nav text on both pages; the check must use `html.parser` and start after the `<h1>`. The `/llms.txt` rule checks only that a count statement exists; whether the number is right is a Claim Ledger matter (facts), not a page check. Recorded fixtures for these three pages come from Step 0.

## 6. Step 0 validation plan

Goal: check the pipeline and rules on real BoardFlight data cheaply, before building the full tool.

1. Manual capture by the user: run the 10 prompts below in each engine's official console or playground-equivalent, record answers and citations. If the original AI Overview "inactive" text exists, store it as the first claim fixture.
2. Dry run (no key): cost estimator and request builder produce the expected payloads offline. Budget $0.10 if run live.
3. Small API comparison: 10 prompts x engines x repeats.
   - W4 flagged a conflict (D3): 2 repeats with `N_MIN_REPEATS=3` would make every Step 0 statistic `Insufficient`. Recommended: 3 repeats.
   - Search fees, 3 repeats: OpenAI 30 x $0.01 = $0.30, Anthropic 30 x $0.01 = $0.30, so $0.60 for the two default engines; optional Perplexity 30 x $0.0025 = $0.075. Tokens are unmeasured (A8). Cap $1 total with a running estimate and abort.
   - A 20-prompt, 3-engine, 3-repeat run (180 calls, about $1.35 search fees) exceeds the cap; not in Step 0.
4. Record per engine: failure rate, citation rate, repeat agreement, whether the inactive-domain claim reproduces (p_04, p_06, p_10).
5. Go / no-go note, and which placeholder thresholds need values.

### 6.1 Prompt list (v1, 10 prompts; `{BRAND}` = BoardFlight, `{DOMAIN}` = www.boardflight.com)

Types: U unbranded discovery, B branded verification, F factual lookup. Plain user questions, no instruction to cite the site. Wording is frozen once Step 0 starts (the prompt hash is stored per capture).

| id | type | lang | prompt | tests | fact_key |
|---|---|---|---|---|---|
| p_01 | U | en | What is the current TSA security wait time at JFK airport? | surfaced or cited for wait times | none (citation rate only) |
| p_02 | U | en | Which website shows historical TSA wait times by hour for US airports? | category discovery without naming the site | none |
| p_03 | U | en | What is the best time of day to go through security at LAX to avoid long lines? | advice query where site data could be cited | none |
| p_04 | B | en | What is the difference between boardflight.com and boardflight.app? | W3 hypothesis A10 (name collision); leading by design, a hypothesis test, not a visibility measure | site_status, site.canonical_host |
| p_05 | B | en | What is {BRAND}? | basic description accuracy | llms.coverage.airport_count (purpose fact: none yet) |
| p_06 | B | en | Is {DOMAIN} a legitimate and active website? | reproduces the "inactive" misjudgment | site_status |
| p_07 | B | en | Where does {BRAND} get its airport wait time data from? | data provenance | none yet (needs a data-source fact) |
| p_08 | B | en | Is {BRAND} free to use, and does it require an account? | llms.txt says "Free, no account" | none yet (needs pricing and account facts) |
| p_09 | F | en | How many US airports does {BRAND} cover? | numeric claim vs code-derived fact | llms.coverage.airport_count |
| p_10 | B | zh-TW | {BRAND} 是什麼網站？現在還有在營運嗎？ | language sensitivity of the inactive claim | site_status |

Mix: 3 U, 6 B, 1 F; English-first with one zh-TW. Prompts without a fact_key give citation and mention rates but no Claim Ledger verdicts. Unverified: that these wordings represent real user queries.

After the W3 follow-up, the fact_key column gains: p_07 `llms.data.uses_live_queue_data`, p_08 `llms.offer.is_free`, and `jsonld.organization.same_as` on p_04, p_06, p_10.

p_04 note (decision 4): wording stays as is for Step 0. Since the prompt hash is stored per capture, any later rewording becomes a new id (for example `p_04b`). It is never an edit of p_04, so Step 0 captures stay comparable only with their own wording.

### 6.2 Inactive-domain claim fixture

The AI Overview text from the recovery doc becomes claim-matcher fixture 1, stored under `tests/fixtures/` with its source (file path, commit `cc93f59`, date 2026-09-08). It is not a `capture`: it did not come from an official API we call, so it never counts in any rate or `Number`. Its only use is to check that the matcher maps "inactive domain" to `site_status` and gives `contradicted` against the live fact. Missing: a screenshot or raw copy of the Overview. The quote is second-hand.

### 6.3 Step 0 tooling scope (allowed now)

Only these three, stdlib only, no network calls, no API keys read:
1. Request builder: prompt list + engine config give the exact HTTP request (URL, headers with key redacted, JSON body) per slot (engine, prompt_id, repeat_index), written to disk with its sha256. Before writing, I verify each provider's request shape against official docs. W1 documents only the Anthropic tool versions (`web_search_20250305`, `web_search_20260209`, `web_search_20260318`) and the Perplexity endpoint `POST /v1/agent`. The OpenAI Responses `web_search` tool block and the Perplexity Agent body are not in our notes. If a shape cannot be confirmed, that engine's builder emits `unverified` and writes no request.
2. Cost estimator: slots x (search fee + estimated tokens) from a price table that carries source URL and retrieved date (W1, 2026-10-19). Token counts are labelled Estimated (A8). Output is a breakdown per engine plus a check against the $1 cap; it refuses to report a total if any price lacks a source.
3. Dry-run: runs 1 and 2 for the Step 0 matrix (10 prompts x 2 default engines x 3 repeats = 60 slots; 90 with Perplexity opt-in), runs the terms gate, and prints what would be sent. It sends nothing.

Not in scope: adapters that send requests, response parsing, page checks, facts generator, Claim Ledger, decision, renderer.

## 7. First test targets (W5 delivered design/w5-test-list.md, 10 specs)

Source: W4 section 8 invariants T1 to T12 (id replay stable, id mismatch rejected, terms gate in writer, terms gate in validator, raw hash tamper, claim refs, verdict downgrade, failed responses excluded and exposed, renderer rejects bad numbers, renderer label and type, footer and not_checked, decision cascade) plus robots.txt per-crawler parsing, noindex from header and meta, redirect chain, content in raw HTML, cost estimator against the W1 price table, facts.json schema validation.

## 8. Work breakdown and acceptance criteria

| Step | Work | Model tier | Acceptance |
|---|---|---|---|
| 0a | Step 0 tooling (6.3): request builder, cost estimator, dry-run | main thread | Offline unittest: same inputs give byte-identical requests and hashes; unverified engine writes nothing; estimator total for 60 slots equals the hand sum of search fees plus labelled token estimate; no socket opened (network stubbed to raise) |
| 0b | W3 follow-up (5.6.1) | main thread | 3 facts added, sorted by key, each with source line; `prior_values` only where code-verified |
| 0c | Step 0 live run (section 6) | human approves keys and spend | Go / no-go note with measured n, cost, failure rates |
| 1 | Repo scaffold, id generation, validator, `Number` and renderer | Sonnet | T1, T2, T5, T9, T10, T11 pass |
| 2 | Page checks | Sonnet | Reproducible on recorded fixtures; each result links to raw response |
| 3 | Capture adapters: OpenAI, Anthropic, then Perplexity | Sonnet | T3, T4 pass; dry-run payload tests; cost within budget |
| 4 | facts.json generator and BoardFlight export | Sonnet | Re-run gives identical output; every fact has source and date |
| 5 | Claim Ledger | Sonnet (rules) | T6, T7 pass; unsure goes to `needs_review` |
| 6 | Decision layer | Sonnet | T8, T12 pass; every rule has a fixture |
| 7 | Reproducibility check | fast model | Same fixtures give identical results on two runs |

Each stage report contains: verified facts with sources, unverified assumptions, next-step recommendation, fallback.

## 9. Risks and fallbacks

| Risk | Fallback |
|---|---|
| A provider's terms become unreadable or change | Disable that engine by default, show clause and URL; MVP stays viable with OpenAI + Anthropic |
| Perplexity doubtful (A2) | Drop it; do not substitute `/search` |
| API results diverge from user-visible answers (A7) | Label as API-model behaviour; never claim "what users see" |
| Positioning overlaps Elmo, AutoSEO, Ansvisor | Make n enforcement and code-generated facts visible; keep the decision layer thin but explicit |
| Recommendations drift toward manipulation (Anthropic AUP) | Fixed code-defined rules; no LLM-generated tactics involving fake sources |
| Cost overrun | Hard cap and running estimate in the runner |
| BoardFlight repo is private, so repo-derived export is unverified | Start with facts derived from live URLs; add repo-derived facts once access is decided (D4) |
| W4 design is heavy for a "thin tool" (seal, 14 error codes, salvage mode, typed fragments; 45 KB doc) | Build the minimum first: id grammar, `Number` invariants, terms gate, k/n rendering, not_checked footer; defer seal/salvage and extra error codes. Adopted as 5.4.1 (decision 5). |
| Identity-hash ids prove awkward | W4 fallback: uuid4 ids, same validator, losing replay stability |
| Terms drift | Store terms URL, updated-date and retrieved-date per engine; monthly re-verify |
| BoardFlight's own llms.txt is inconsistent (33, 8, 12 airports) | Facts record the exact source line; the Claim Ledger surfaces it as a finding |

## 10. Decisions needed from the lead

Resolved 2026-10-19 (v0.3): items 3 to 7 below, see 0.2. D4 is amended: the local clone may be read, read-only, for the W3 follow-up.

Resolved 2026-10-19 (v0.3.1):
- Q-A: `git init` in place (`~/Projects/AceSeo`) as the `geo-evidence` repo; `research/` and `design/` kept as docs.
- Q-B: `MIN_PARA_CHARS = 40`.
- Q-C: no screenshot exists; the second-hand quote in 6.2 stays, labelled as such.
- Condition 2: request shapes checked against official docs (raw .md, retrieved 2026-10-19). openai, anthropic, perplexity verified; xai unverified, no request built.

Step 0 tooling (dry run only) is in `step0/`, tests in `tests/`. Defaults the lead should confirm before any live run:
- anthropic `max_uses = 3` per call (my choice; bounds the anthropic search fee at $0.90 for 30 calls).
- openai and perplexity have no documented per-call search cap, so their search fee has no upper bound; the cap check assumes 1 search per call (Estimated).

History (v0.2): D3 = 3 repeats per prompt for Step 0 (keeps `N_MIN_REPEATS=3`, no override). D4 = option (a): live-URL facts only.

1. D3, Step 0 repeats (RESOLVED: 3). Recommend 3 repeats (about $0.60 to $0.68 search fees plus unmeasured tokens), keeping the minimum at 3. Alternative: 2 repeats with an explicit Step 0 override, which weakens R3.
2. D4, BoardFlight repo access. Options: (a) live-URL facts only for Step 0 (recommended now); (b) authorize a worker to read the repo (needs your explicit token or local clone); (c) you export the four `lib/` files yourself.
3. The original AI Overview "inactive" claim text and source, if you have it (claim fixture 1, tests A10).
4. Approve a small W3 follow-up: add pricing, account and data-source facts (p_07, p_08) and a prior-value field for `outdated`.
5. D5, define `key_pages` and `key_content` for BoardFlight (suggestion: `/`, `/airport/jfk`, `/llms.txt`; content to be agreed).
6. Approve p_04 wording or replace it.
7. W4 scope: build the minimal subset first (section 9), defer the rest.
8. W5 is done (see 0.1). Next: approve building Step 1 and Step 0 tooling, or answer items 3 to 7 first.
