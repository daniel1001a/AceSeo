# W4: Data model, evidence IDs and report renderer contract

Status: design only, no implementation. Author: W4. Date: 2026-10-19.
Scope: refines PLAN.md section 4.4 so that every number the tool prints is traceable and the renderer cannot print a number without `n` and evidence ids.

## 1. Verified facts and unverified assumptions

### 1.1 Verified facts (from the files named)

| # | Fact | Source |
|---|---|---|
| F1 | Constraints: Python 3.9+ stdlib only; every number traceable to a `capture_id` or `page_check_id`; unclear terms mean `unverified` and auto-writing stops. | PLAN.md section 1 |
| F2 | Engine config fields: `enabled`, `terms_status` (verified-allowed / verified-restricted / unverified), `terms_url`, `terms_last_updated`, `terms_retrieved`, `model`, `tool_version`, `price_snapshot`. Unverified or restricted engines refuse to write captures. | PLAN.md 4.3 |
| F3 | Draft IDs: `cap_<engine>_<yyyymmddThhmmss>_<hash8>`, `pc_<check>_<...>_<hash8>`, `clm_<capture_id>_<n>`, `dec_<run>_<n>`. Draft record fields for capture, page_check, claim, decision. Renderer must fail if `n` or ids are missing. | PLAN.md 4.4 |
| F4 | Rules R0 to R4, placeholder minimum n = 3 per engine per prompt, R3 needs "at least 2 independent engines", every output lists `not_checked[]` and the "API-model behaviour" caveat, no composite score, "Why this rule fired" list of evidence ids. | PLAN.md 4.6 |
| F5 | Step 0: 10 prompts x 3 engines x 2 repeats = 60 calls, $1 cap with abort, record failure rate, citation presence rate, agreement across repeats, inactive-domain reproduction. | PLAN.md 5 |
| F6 | Step 7 acceptance: same fixtures give identical results on two runs. Step 1 acceptance: renderer rejects missing n or ids. | PLAN.md 7 |
| F7 | Borrow list: Elmo labels (Measured / First-party / Published / Estimated) and "rates not ranks"; mcp-geo failed-response exclusion with exposure; AutoSEO verdicts and downgrade to `needs_review`; Ansvisor "Why this priority?" and independent-evidence-kinds confidence. | PLAN.md 2.4; research/w2-competitors.md "Borrow" |
| F8 | Elmo's skill labels Measured numbers "from tracked runs, with n and window". mcp-geo score = mentioning usable responses / usable responses, failures excluded. | research/w2-competitors.md, comparison table and differentiator 2 |
| F9 | AutoSEO has six verdicts including `off_label`; PLAN keeps five (drops `off_label`). | research/w2-competitors.md, comparison table; PLAN.md 4.4 |
| F10 | OpenAI returns citations as `url_citation` annotations; displayed citations must be visible and clickable. | research/w1-api-terms.md 2.1 |
| F11 | Anthropic web search tool versions `web_search_20250305`, `web_search_20260209`, `web_search_20260318`; `max_uses` caps searches; citation fields `cited_text`, `title`, `url`; citations must accompany displayed outputs. | research/w1-api-terms.md 2.2 |
| F12 | Perplexity Agent API returns a `search_results` output item (url, title, snippet, date). The `fast` preset runs `openai/gpt-6-luna`; third-party model terms stack. | research/w1-api-terms.md 2.3 |
| F13 | Store terms URL, last-updated and retrieval date per engine; re-verify on a schedule (monthly suggested). | research/w1-api-terms.md 5; PLAN.md 8 |
| F14 | Local check on this machine (Python 3.9.6, run by W4): `datetime.fromisoformat("...Z")` raises ValueError; `strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ")` works; `json.loads` accepts `parse_float`, `parse_constant`, `object_pairs_hook` hooks that can raise; bundled SQLite 3.54.0 has `PRAGMA foreign_keys` = 0 by default; `dataclass(slots=True)` is a TypeError on 3.9; Python `re` `\d` matches non-ASCII digits (for example Arabic-Indic), `[0-9]` does not. | Local run, this task |

### 1.2 Unverified assumptions

| # | Assumption | Impact | How to settle |
|---|---|---|---|
| U1 | Each provider response exposes enough to map to `ok` / `failed` / `refused` and to token `usage`. Exact field names were not checked. | Status and cost fields | Adapter tests on recorded fixtures (Step 3) |
| U2 | No provider returns a billed dollar amount per call. | `cost_billed_usd` stays null | Check during Step 0 |
| U3 | `model_vendor` is an adequate proxy for engine independence. Search backends behind each engine are unknown. | R3 and confidence | Labelled as assumption in output |
| U4 | facts.json will expose a stable `fact_key`, `source`, `derived_at`, and (for `outdated`) prior values. W3 has not designed it. | Claim links, `outdated` verdict | W3 |
| U5 | Data volume per run is small (Step 0: 60 calls), so loading a whole run into memory for validation is acceptable. | Storage choice | Step 0 measurement |
| U6 | Refusals are excluded from denominators per the brief; whether a refusal is itself a meaningful "API-model behaviour" signal is not settled. | Rate definitions | Open question Q1 |

## 2. Storage and evidence ID format

### 2.1 Storage: JSONL plus content-addressed raw files (chosen) vs sqlite3

| Criterion | JSONL + raw files | sqlite3 (stdlib) |
|---|---|---|
| User can open, grep and diff an evidence id | Yes | Needs a client |
| Immutability | Append-only files plus a seal manifest of sha256 hashes | Needs triggers; file changes on every read-write open |
| Referential integrity | Python validator (needed anyway for raw-file hashes and facts.json links) | FK constraints, but off by default per connection (F14) and cannot check file hashes |
| Raw responses | Files | BLOBs or files anyway |
| Reproducibility (F6) | Canonical JSON lines are byte-comparable | DB file bytes are not comparable |
| Portability | Copy a directory | Copy one file; bundled SQLite version varies by Python build |

Decision: JSONL is the source of truth. A sqlite index may be added later as a derived, rebuildable cache, never as evidence.

Layout (one self-contained directory per run):

```
.geo-evidence/runs/<run_id>/
  manifest.json          run config, engine snapshots, thresholds, planned and skipped slots
  inputs/prompts.json    snapshot of the prompt set
  inputs/facts.json      exact facts.json used (its sha256 is in the manifest)
  inputs/sources.json    published sources (price tables, terms pages, studies)
  captures.jsonl
  page_checks.jsonl
  claims.jsonl
  decisions.jsonl
  raw/<sha256>.<ext>     raw response bodies and stored request bodies
  SEAL.json              sha256 and line count of every file above; presence = sealed
.geo-evidence/reports/<run_id>/report.md
```

JSONL encoding: one record per line, `json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`, UTF-8, `\n` terminated. Floats, NaN and Infinity are forbidden in records (validator loads with `parse_float` and `parse_constant` hooks that raise, F14); money is a decimal string, counts are ints. Duplicate JSON keys are rejected via `object_pairs_hook`.

### 2.2 ID options compared

| Option | Stable on replay | Verifiable from record | Unique across runs | Problem |
|---|---|---|---|---|
| A. Draft: kind + engine + wall-clock timestamp + hash8 | No (timestamp changes) | No | Mostly | Breaks F6; 32-bit hash; `clm_<capture_id>_<n>` nests ids and depends on extraction order |
| B. Hash of raw response content | Yes | Yes | Yes | No id exists for a call with no response (timeout); identical answers collide |
| C. `uuid.uuid4()` | No | No | Yes | Breaks F6 |
| D. Hash of a declared identity tuple that includes `run_id` (chosen) | Yes | Yes (recompute) | Yes | Needs a defined identity tuple per kind |

Chosen: D. The id names the observation slot ("which question, which engine, which repeat, which run"). What came back is bound to the record by `raw_sha256` inside the immutable record. The id therefore exists before the network call, so failed calls get ids too.

### 2.3 Grammar

```
RUN_ID     ^run_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{6}$
RECORD_ID  ^(?P<prefix>cap|pc|clm|dec)_(?P<slug>[a-z0-9](?:[a-z0-9-]{0,22}[a-z0-9])?)_(?P<h>[0-9a-f]{16})$
AUX_REF    ^(?P<prefix>fct|src)_(?P<h>[0-9a-f]{16})$
EVIDENCE   RECORD_ID | AUX_REF
SHA256     ^[0-9a-f]{64}$
```

Use `[0-9]`, never `\d` (F14). Slug meaning (readability only, validated against the record):

| Prefix | Kind | Slug |
|---|---|---|
| `cap` | capture | engine id, for example `openai` |
| `pc` | page_check | check name, for example `robots-ai` |
| `clm` | claim | engine id of the parent capture |
| `dec` | decision | rule set scope, for example `site` |
| `fct` | auxiliary: a fact in a facts.json snapshot | none |
| `src` | auxiliary: a published source in sources.json | none |

`fct` and `src` are not record kinds. They exist because First-party and Published numbers must also cite evidence (F1 only names capture and page_check ids, which cannot back a price or a site fact).

### 2.4 What is hashed

```
identity_bytes = b"geo-evidence/id/v1\n" + canonical_json(identity_dict).encode("utf-8")
identity_sha256 = sha256(identity_bytes).hexdigest()
id = prefix + "_" + slug + "_" + identity_sha256[:16]
```

`canonical_json` is the JSONL encoding above. Identity dict values are str, int, bool, null, list or dict only.

| Kind | identity_dict keys |
|---|---|
| capture | `kind, run_id, engine, model, tool_version, prompt_id, prompt_sha256, repeat_index, attempt` |
| page_check | `kind, run_id, check_name, check_version, url_norm, agent_profile, params` |
| claim | `kind, run_id, capture_id, facts_sha256, matcher, matcher_version, span_start, span_end` |
| decision | `kind, run_id, rule_set_version, scope` |
| fct | `kind, facts_sha256, fact_key` |
| src | `kind, url, retrieved, locator` |

`run_id` hex6 = first 6 hex of sha256 over canonical `{plan_sha256, started_at}`, where `plan_sha256` hashes the manifest's plan section (engines, prompts sha, repeats, key pages, thresholds).

`url_norm`: lowercase scheme and host, drop default port and fragment, keep path and query byte-exact (urllib.parse). The same function, versioned as `url_norm_v1`, is used everywhere a URL is compared.

`series_key` (stored on captures and page_checks, not an id): sha256 of the identity dict without `run_id` and `attempt`. It is the only legal key for comparing the same slot across runs.

### 2.5 Collision handling

- 64-bit prefix. The validator recomputes `identity_sha256` for every record and requires `id` to match it.
- Two records with the same id and different `identity_sha256`: hard error `E_ID_COLLISION`; the run cannot be sealed. No suffixing, because suffixes depend on write order and break replay. Fix is a code change to lengthen the prefix with a new `schema_version`.
- Two records with the same id and the same `identity_sha256`: `E_DUPLICATE_RECORD` (a slot was written twice).
- `run_id` collision (same plan, same second): run directory is created with `os.mkdir` (fails if it exists); the runner aborts and never appends to an existing run.

### 2.6 Stability rules

| Situation | IDs |
|---|---|
| Re-validate, re-render, or replay the same run from recorded raw files | Identical (same identity tuples, same `run_id`) |
| New live run with identical prompts and engines | New `run_id`, therefore new ids; same `series_key` |
| Re-analysis of sealed captures with a new facts.json or matcher version | New analysis run (`run_kind = analyze`, `source_run_ids` set); new claim and decision ids; capture ids unchanged and referenced, never copied |
| Retry of a failed call | Same slot, `attempt + 1`, new id; the failed attempt record stays |

### 2.7 Raw response files

- Name: `raw/<sha256 of exact bytes>.<ext>`, ext from a fixed map: `json`, `html`, `txt`, `xml`, `bin`. Path stored relative to the run directory.
- Content: response body bytes exactly as received (not re-serialized). HTTP status, headers (ordered list of `[name, value]` pairs, duplicates kept) and redirect chain go in the record.
- Request bodies for captures are stored the same way (`request_sha256`). Request headers are never stored. The writer asserts that the API key string is not a substring of any byte it writes.
- Write: if the file exists, verify its hash and reuse it (dedup within a run); otherwise write to a temp name in `raw/`, fsync, `os.replace` to the final name. After seal, files are chmod read-only (best effort).
- Missing body: allowed only for `status = failed` with `error_class` in `{timeout, connection}`; then `raw_sha256` and `raw_path` are null.

### 2.8 Immutability

1. Records are append-only. No edit, no delete, inside a run.
2. A run is sealed once: `SEAL.json` lists sha256 and line count of every file. Any later difference is `E_SEAL_MISMATCH`.
3. Reports render only from sealed runs (`E_UNSEALED`).
4. Corrections are new records in a new run that references the old one.
5. The tool never deletes runs. A report that cites ids from a deleted run fails to render.
6. A crashed run with a torn last line cannot be sealed as-is; `seal --salvage` (fallback, section 9) drops only the torn line and records it in `not_checked`.

## 3. Required fields per record kind

Types: `ts` = UTC timestamp `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$`, parsed with `strptime("%Y-%m-%dT%H:%M:%S.%fZ")` (not `fromisoformat`, F14). `date` = `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`. `dec` = decimal string `^(0|[1-9][0-9]*)(\.[0-9]{1,12})?$`, parsed with `decimal.Decimal`. `slug` = `^[a-z0-9](?:[a-z0-9-]{0,22}[a-z0-9])?$`. R = required, O = optional (key present, value may be null), C = conditional.

### 3.1 Common to all four kinds

| Field | Type | Req | Validation |
|---|---|---|---|
| `kind` | str | R | one of `capture`, `page_check`, `claim`, `decision`; matches file |
| `schema_version` | int | R | equals the validator's supported version (1); no silent migration |
| `id` | str | R | RECORD_ID grammar; prefix matches kind; equals recomputed id |
| `identity_sha256` | sha256 | R | equals sha256 of identity bytes |
| `run_id` | str | R | RUN_ID grammar; equals the containing run directory |
| `created_at` | ts | R | within `[manifest.started_at, manifest.sealed_at]` |
| `tool_build` | str | R | equals `manifest.tool_build` |

### 3.2 Run manifest (one per run, not a record kind)

| Field | Type | Req | Validation |
|---|---|---|---|
| `run_id`, `schema_version`, `tool_build` | as above | R | |
| `run_kind` | enum `collect`, `analyze` | R | `analyze` runs contain no captures or page_checks |
| `source_run_ids` | list[str] | R | empty for `collect`; each resolves to a sealed run |
| `started_at`, `sealed_at` | ts | R, C | `sealed_at` set at seal |
| `engines` | list[engine_snapshot] | R | see 3.3; one per engine id |
| `engines_excluded` | list[{engine, terms_status, reason}] | R | every configured engine not in `engines` appears here |
| `prompts_sha256`, `facts_sha256`, `sources_sha256` | sha256 | R | equal the hashes of the `inputs/` files |
| `repeats`, `max_attempts` | int | R | >= 1; `max_attempts` placeholder |
| `key_pages` | list[str] | R | `url_norm_v1` form; non-empty if any page_check exists |
| `key_content` | list[{url, expected, fact_key}] | O | expected strings for the raw-HTML content check |
| `mention_terms` | list[str] | R | non-empty; used by mention statistics |
| `thresholds` | map name -> {value, status} | R | status `placeholder` or `calibrated` |
| `planned_slots` | int | R | engines x prompts x repeats |
| `skipped_slots` | list[{engine, prompt_id, repeat_index, reason}] | R | reason in `budget_cap`, `user_abort`, `terms_gate` |
| `budget` | {cap_usd: dec, spent_estimate_usd: dec} | R | spent <= cap, else run must show `budget_abort` |

### 3.3 capture

| Field | Type | Req | Validation |
|---|---|---|---|
| `engine` | slug | R | equals id slug; present in `manifest.engines` |
| `engine_snapshot` | object | R | byte-equal (canonical) to the manifest entry for `engine` |
| `.model` | str | R | non-empty; equals model in stored request body |
| `.model_vendor` | slug | R | independence key, for example `openai` for the Perplexity `fast` preset (F12) |
| `.tool_version` | str | R | non-empty |
| `.terms_status` | enum | R | must equal `verified-allowed` (V12) |
| `.terms_url` | str | R | https URL |
| `.terms_last_updated`, `.terms_retrieved` | date | R | `terms_retrieved` <= capture date; age <= `TERMS_MAX_AGE_DAYS` (placeholder) |
| `.opt_in` | bool | R | true for engines that are opt-in (Perplexity) |
| `.price_snapshot` | list[{unit, per, price_usd, condition, source_ref}] | R | unit in `input_token`, `output_token`, `cached_input_token`, `search_call`; per in `1`, `1k`, `1m`; price `dec`; `source_ref` is a resolvable `src_` id |
| `.config_sha256` | sha256 | R | sha256 of canonical snapshot without this field |
| `prompt_id` | str | R | `^p_[a-z0-9_]{1,40}$`; in prompts snapshot |
| `prompt_text` | str | R | NFC-normalized; equals prompts snapshot text |
| `prompt_sha256` | sha256 | R | sha256 of UTF-8 `prompt_text` |
| `repeat_index` | int | R | `0 <= i < manifest.repeats` |
| `attempt` | int | R | `1 <= a <= max_attempts`; attempts per slot contiguous from 1; no attempt after an `ok` |
| `started_at`, `completed_at` | ts | R | `completed_at >= started_at` |
| `status` | enum | R | `ok`, `failed`, `refused` |
| `error_class` | enum | C | required iff `failed`: `timeout`, `connection`, `http_error`, `rate_limited`, `parse_error`, `empty_answer` |
| `http_status` | int | O | 100..599 |
| `request_sha256` | sha256 | R | file exists, hash matches |
| `raw_sha256`, `raw_path` | sha256, str | R, O null | see 2.7 |
| `answer_text` | str | R | non-empty if `ok`; may be empty if `failed` |
| `citations` | list | R | may be empty; each `{url, title, cited_text, position, provider_field}`; url scheme http/https; positions unique ints from 0 |
| `usage` | {input_tokens, output_tokens, cached_input_tokens, search_calls} | O | ints >= 0 |
| `cost_estimate_usd` | dec | R | pre-call, from price snapshot and planned limits |
| `cost_from_usage_usd` | dec | O | if `usage` present, equals recomputation from usage x price snapshot |
| `cost_billed_usd` | dec | O | only if the provider returns it (U2), with `cost_billed_field` naming the raw field |
| `series_key` | sha256 | R | recomputed per 2.4 |

### 3.4 page_check

| Field | Type | Req | Validation |
|---|---|---|---|
| `check_name` | slug | R | equals id slug; in check registry |
| `check_version` | int | R | in check registry |
| `url_norm` | str | R | `url_norm_v1` form |
| `url_role` | enum `key`, `other` | R | `key` iff `url_norm` in `manifest.key_pages` |
| `agent_profile` | slug | R | for example `gptbot`, `default`; in registry |
| `params` | object | R | may be `{}` |
| `fetched_at` | ts | R | |
| `final_url` | str | O | null if no response |
| `http_status` | int | O | |
| `redirect_chain` | list[{url, status}] | R | may be empty |
| `response_headers` | list[[name, value]] | R | may be empty |
| `raw_sha256`, `raw_path` | | R, O null | null only with `result = not_checkable` and reason `timeout` or `connection` |
| `derived_from_raw` | bool | R | true when several checks share one fetch (independence, 6.4) |
| `result` | enum | R | `pass`, `fail`, `not_checkable` |
| `not_checkable_reason` | str | C | required iff `not_checkable` |
| `blocking_on_fail` | bool | R | equals registry value for `check_name, check_version` |
| `detail` | object | R | schema per check in registry |
| `series_key` | sha256 | R | |

### 3.5 claim

| Field | Type | Req | Validation |
|---|---|---|---|
| `capture_id` | str | R | resolves; capture `status = ok`; capture in this run or a source run |
| `span_start`, `span_end` | int | R | `0 <= start < end <= len(answer_text)` |
| `statement` | str | R | equals `answer_text[span_start:span_end]` of the capture |
| `fact_key` | str | C | required unless verdict in `unsupported`, `needs_review`; exists in facts snapshot |
| `fact_ref` | AUX_REF `fct_` | C | required iff `fact_key`; recomputes from `facts_sha256` and `fact_key` |
| `facts_sha256` | sha256 | R | equals `manifest.facts_sha256` |
| `fact_value_snapshot` | str/int/bool | C | equals the fact's value in the snapshot |
| `verdict` | enum | R | `matched`, `contradicted`, `unsupported`, `outdated`, `needs_review` |
| `verdict_basis` | enum | R | `exact`, `normalized`, `value_mismatch`, `prior_value`, `no_fact`, `undecided` |
| `matcher` | enum `rule`, `llm` | R | `llm` claims may only have verdict `needs_review` in MVP (V20) |
| `matcher_version` | int | R | |

Allowed `verdict` x `verdict_basis` pairs: matched {exact, normalized}; contradicted {value_mismatch}; outdated {prior_value}; unsupported {no_fact}; needs_review {undecided}. Anything else is rejected. This is the AutoSEO downgrade rule (F7) made structural: a matcher that cannot produce one of the decided bases must emit `needs_review`.

### 3.6 decision

| Field | Type | Req | Validation |
|---|---|---|---|
| `scope` | slug | R | equals id slug; MVP: `site` |
| `rule_set_version` | int | R | |
| `outcome` | enum | R | `insufficient_evidence`, `seo_first`, `geo_fix_facts`, `geo_content`, `no_action` |
| `fired_rule_id` | enum `R0`..`R4` | R | consistent with `outcome` (7.1) |
| `evaluations` | list[{rule_id, result, reason_code, input_ids}] | R | one entry per rule in evaluation order; result `fired`, `not_fired`, `unknown`, `not_evaluated` |
| `input_ids` | list[EVIDENCE] | R | non-empty; union of all evaluation input ids; all resolve |
| `numbers` | list[Number] | R | every Number the decision relies on (section 5) |
| `hypothesis` | bool | R | true for R1 and R3 |
| `assumption_refs` | list[str] | R | `^A[0-9]+$`; contains `A6` if R1 fired; contains `A7` always |
| `confidence_basis` | list[{group_key, evidence_ids}] | R | computed per 6.4; no numeric weight |
| `thresholds_snapshot` | map | R | equals `manifest.thresholds` |
| `why` | list[{template_id, evidence_ids}] | R | non-empty; every id in `input_ids` |
| `not_checked` | list[{item, reason_code, detail}] | R | non-empty; contains every baseline item (5.5) |

Removed from the PLAN draft: decision-level `n` and `label`. They are ambiguous on a record that combines several statistics; they move onto each Number.

## 4. Validation rules (reject conditions)

The validator loads a run (plus declared source runs) and returns all errors; any error means the run cannot be sealed and cannot be rendered. Errors only; there are no warnings.

| # | Reject when | Code |
|---|---|---|
| V1 | A line is not valid JSON, has duplicate keys, a float, NaN or Infinity | `E_JSON` |
| V2 | A required field is missing, has the wrong type, or an unknown field is present | `E_SCHEMA` |
| V3 | `schema_version` is not the supported version | `E_SCHEMA_VERSION` |
| V4 | `id` fails grammar, slug does not match the record, or does not equal the recomputed id | `E_ID_MISMATCH` |
| V5 | Same id with different identity, or the same record twice | `E_ID_COLLISION`, `E_DUPLICATE_RECORD` |
| V6 | A timestamp fails the `ts` format, or ordering (`completed_at < started_at`, outside run window) | `E_TIME` |
| V7 | A raw or request file is missing, its sha256 differs from its name or record, or the path is absolute or contains `..` | `E_RAW_HASH` |
| V8 | A stored file contains a forbidden request header name or the API key string (writer-side check, re-checked when the key is available) | `E_SECRET` |
| V9 | `prompt_sha256` does not match `prompt_text`, or one `prompt_id` maps to two texts in a run | `E_PROMPT` |
| V10 | `engine_snapshot` differs from the manifest entry, or `config_sha256` does not recompute | `E_ENGINE_SNAPSHOT` |
| V11 | Slot rules: `repeat_index` out of range, attempts not contiguous, attempt after an `ok`, more than one `ok` per slot | `E_SLOT` |
| V12 | Any capture whose `engine_snapshot.terms_status` is not `verified-allowed`, or whose `terms_retrieved` is older than `TERMS_MAX_AGE_DAYS`, or whose engine is `opt_in` but not opted in for the run | `E_TERMS_GATE` |
| V13 | `status = ok` with empty `answer_text` or null raw; `failed` without `error_class`; null raw outside the allowed error classes | `E_STATUS` |
| V14 | A citation URL is not http/https, or positions are not unique | `E_CITATION` |
| V15 | Cost: non-decimal string, or `cost_from_usage_usd` does not recompute | `E_COST` |
| V16 | Referential: `claim.capture_id` does not resolve, or resolves to a non-`ok` capture | `E_REF_CAPTURE` |
| V17 | Referential: `fact_key` missing from the facts snapshot, `fact_ref` does not recompute, `facts_sha256` differs from the manifest | `E_REF_FACT` |
| V18 | `statement` differs from the capture span | `E_CLAIM_SPAN` |
| V19 | Disallowed `verdict` x `verdict_basis` pair | `E_VERDICT` |
| V20 | `matcher = llm` with a verdict other than `needs_review` | `E_VERDICT_LLM` |
| V21 | Referential: any decision `input_ids`, `why` or Number evidence id does not resolve within the run plus its declared sealed source runs | `E_REF_UNRESOLVED` |
| V22 | A reference points into a run not listed in `source_run_ids`, or a source run is unsealed | `E_REF_SCOPE` |
| V23 | Decision consistency: `outcome` and `fired_rule_id` disagree, `evaluations` not in the evaluation order, `hypothesis` or `assumption_refs` inconsistent with the fired rule | `E_DECISION` |
| V24 | `not_checked` empty or missing a baseline item | `E_NOT_CHECKED` |
| V25 | Page check: `blocking_on_fail` or `url_role` inconsistent with registry or manifest | `E_PAGE_CHECK` |
| V26 | Seal file present and any file hash or line count differs | `E_SEAL_MISMATCH` |
| V27 | Every configured engine is in exactly one of `engines` or `engines_excluded` | `E_ENGINE_SET` |

Terms gate is enforced twice: (a) the capture writer refuses before any network call when the engine snapshot is not `verified-allowed` (the slot is logged in `skipped_slots` with reason `terms_gate` and the engine in `engines_excluded`); (b) V12 rejects any capture that slipped through. An engine with `unverified` or `verified-restricted` status therefore cannot produce a capture that survives validation.

## 5. Report renderer contract

### 5.1 Number value object

Frozen dataclass (no `slots`, no `kw_only`: both need 3.10+; F14). Validated in `__post_init__`.

| Field | Type | Rule |
|---|---|---|
| `statistic_id` | str | key in the statistic registry (section 6.2) |
| `kind` | `count`, `rate`, `money` | |
| `value` | int (count, rate) or Decimal (money) | count and rate: `value == len(hit_ids)` |
| `n` | int | `n == len(evidence_ids)`; the counted units |
| `min_n` | int | must equal the registry value; callers cannot lower it |
| `evidence_ids` | tuple[str] | non-empty, unique, sorted, EVIDENCE grammar |
| `hit_ids` | tuple[str] | subset of `evidence_ids`; required for count and rate, empty for money |
| `excluded` | tuple[(id, status)] | required (may be empty); status in `failed`, `refused`, `not_checkable`; disjoint from `evidence_ids` |
| `label` | `Measured`, `First-party`, `Published`, `Estimated` | |
| `basis_labels` | tuple[label] | non-empty iff `label == Estimated`; lists the component labels |
| `window` | (ts, ts) | equals [earliest, latest] timestamp of resolved evidence |
| `scope` | map | for example `{engine, prompt_id}`; display only |

For rates the renderer prints `k/n` and may add a percentage it computes itself; a percentage is never passed in. No ordinal ranks are rendered (no "1st", no sorted leaderboard); engines appear in manifest order.

Label to evidence compatibility: Measured accepts only `cap`, `pc`, `clm`; First-party only `fct`; Published only `src`; Estimated accepts any kind but requires `basis_labels` covering the kinds present.

`Insufficient` is a sibling type for statistics whose `n < min_n`: `{statistic_id, n, min_n, evidence_ids (may be empty), excluded}`. It renders as "insufficient evidence" with its n, minimum and ids, and never carries a value.

### 5.2 Structural guarantee

The renderer's only input is a `Report` made of blocks, each a sequence of typed fragments:

`Text`, `Number`, `Insufficient`, `EvidenceRef`, `Quote` (verbatim capture span with its `capture_id` and that capture's citations), `Url`, `ConfigLiteral` (a manifest key path, resolved by the renderer, for example a model name or a threshold with its status), `Timestamp`.

- Any other Python type (raw `str`, `int`, `float`, `Decimal`) in a fragment position: `E_TYPE`.
- A `Text` fragment matching `\d` (Unicode digits, F14): `E_STRAY_DIGIT`. Digits can therefore only reach the output through `Number`, `Insufficient`, ids, URLs, quotes, config literals and timestamps, each of which is traceable.
- A `Quote` is always rendered with its citations as visible URLs (W1 display rules, PLAN A4).

### 5.3 Failure behaviour (all are errors that abort rendering)

Rendering collects all errors, then raises `RenderError` with the list of codes; it writes to a temp file and only `os.replace`s it into place on success, so no partial report ever exists. CLI exit status is non-zero. There is no `--force`.

| Condition | Code |
|---|---|
| `n` missing or not an int | `E_N_MISSING` |
| `evidence_ids` empty | `E_EVIDENCE_EMPTY` |
| `n != len(evidence_ids)` or duplicates | `E_N_MISMATCH` |
| `n < min_n` in a `Number` (must have been an `Insufficient`) | `E_N_BELOW_MIN` |
| `min_n` differs from registry | `E_MIN_N_OVERRIDE` |
| An evidence, hit or excluded id does not resolve in the sealed run set | `E_EVIDENCE_UNRESOLVED` |
| Label incompatible with evidence kinds, or a Number combines sub-Numbers of different labels without being `Estimated` with `basis_labels` | `E_LABEL_MIXED` |
| `window` differs from the evidence time range | `E_WINDOW_MISMATCH` |
| `value != len(hit_ids)` for count or rate | `E_VALUE_MISMATCH` |
| A counted capture is not `ok`, or an excluded id is `ok` | `E_EXCLUSION` |
| Run-level failed, refused or skipped set not fully listed in the excluded section | `E_EXCLUDED_MISSING` |
| `not_checked` missing, empty or lacking a baseline item | `E_NOT_CHECKED_MISSING` |
| Unknown fragment type, or digit in `Text` | `E_TYPE`, `E_STRAY_DIGIT` |
| Source run unsealed | `E_UNSEALED` |

### 5.4 Failed and refused responses

- Every capture-based Number carries `excluded`; the renderer prints it next to the number, for example "cited in k/n usable responses; excluded: failed [ids], refused [ids]".
- Every report has a mandatory "Excluded and skipped" section listing all `failed` and `refused` attempts and all `skipped_slots` of the run with reasons. Its counts are Numbers themselves (statistic `failure_rate`, section 6), so they also carry n and ids.
- Completeness is checked: the set of non-ok capture ids in the run must equal the set listed (`E_EXCLUDED_MISSING`).

### 5.5 not_checked[] and footer

- `not_checked` is emitted by code, never by the caller. Sources: (a) a fixed baseline list in code (consumer UI answers, personalization and location, logged-in or app surfaces, engines not configured, traffic or ranking outcomes, Gemini grounding excluded by terms); (b) `engines_excluded` with `terms_status`; (c) `skipped_slots`; (d) page_checks with `not_checkable`; (e) claims with `needs_review` or `unsupported`; (f) statistics rendered as `Insufficient`.
- Footer: the renderer appends a fixed constant stating that results describe API-model behaviour, not what consumer app users see (PLAN A7). It is appended by the renderer itself, is not an input, and its presence is asserted after rendering.

## 6. Aggregation rules

### 6.1 Principles

1. Rates, not ranks. Every statistic is `k/n` with ids; no composite score, no ordinal ranking.
2. The unit of observation is the slot `(engine, prompt_id, repeat_index)`. Each slot contributes at most one counted capture (its single `ok` attempt).
3. Content rates count only `ok` captures; `failed` and `refused` attempts and skipped slots are excluded from the denominator and exposed (mcp-geo, F8).
4. Statistics below `min_n` become `Insufficient`; they are never dropped silently.
5. Runs are never pooled silently. Pooling across runs is allowed only when `series_key`, `engine_snapshot.model` and `tool_version` match, and the Number window then spans both runs. Otherwise runs are shown side by side.
6. Site match uses `url_norm_v1` host equality or subdomain suffix of the site host. Mention match uses `manifest.mention_terms`, case-insensitive, word-boundary regex.

### 6.2 What counts as n

| statistic_id | Unit (evidence_ids) | k (hit_ids) | n | Excluded and exposed | min_n | Label |
|---|---|---|---|---|---|---|
| `citation_rate.engine_prompt` | ok captures of one (engine, prompt) | site host in citations | ok captures | failed, refused attempts; skipped slots | `N_MIN_REPEATS` (placeholder 3) | Measured |
| `mention_rate.engine_prompt` | same | mention term in `answer_text` | ok captures | same | `N_MIN_REPEATS` | Measured |
| `citation_rate.engine` | ok captures of one engine, only prompts meeting `N_MIN_REPEATS` | as above | pooled ok captures | as above plus prompts below minimum (as `Insufficient`) | `N_MIN_ENGINE` (placeholder) | Measured |
| `repeat_agreement.engine` | (engine, prompt) pairs with >= 2 ok captures | pairs whose cited flag is identical across repeats | eligible pairs | pairs with < 2 ok | placeholder | Measured |
| `failure_rate.engine` | all attempts of one engine | `failed` or `refused` attempts | all attempts | none (this is the exposure) | 1 | Measured |
| `contradiction_rate.engine` | ok captures with >= 1 rule-matcher claim with a fact_key | captures with >= 1 `contradicted` or `outdated` claim | eligible captures | `needs_review` and `unsupported` claims listed | placeholder | Measured (evidence ids are `clm` and `cap`) |
| `blocking_fail.key_pages` | key-page page_checks with `blocking_on_fail` and result pass or fail | result `fail` | checkable checks | `not_checkable` checks | 1 | Measured |
| `fact_value` | one fact | n/a | 1 | none | 1 | First-party |
| `price` | one price entry | n/a | 1 | none | 1 | Published |
| `cost_total.run` | attempts with `usage` | n/a (money) | attempts summed | attempts without usage listed | 1 | Estimated, basis Measured + Published |

Multi-engine pooling (one rate across engines) is not provided; R3 reads per-engine rates.

### 6.3 Repeated runs within a run

Repeats feed per-prompt rates directly (k of n repeats). Engine-level rates pool ok captures from prompts that meet `N_MIN_REPEATS`; the number of contributing prompts is shown as a separate count Number. Retries never add to n: a retried slot that succeeds counts once; its failed attempts appear in `failure_rate`.

### 6.4 Independence of evidence kinds (decision confidence)

Each evidence id maps to one independence group:

| Evidence | group_key |
|---|---|
| `pc` | `site:<host of url_norm>` (all page checks of a host share the server) |
| `cap` | `vendor:<engine_snapshot.model_vendor>` |
| `clm` | the group of its parent capture (a claim is not independent of its capture) |
| `fct` with URL source | `site:<host>` (same group as page checks of that host) |
| `fct` with repo file source | `repo:<repo id>` (W3 defines repo id) |
| `src` | `published:<host of url>` |

`confidence_basis` is the sorted list of distinct groups among a decision's input ids, each with its ids. Repeats, multiple prompts, or multiple checks within one group add nothing. "At least 2 independent engines" (R3) means at least 2 distinct `vendor:` groups, each with a sufficient `citation_rate.engine`. Under this rule the Perplexity `fast` preset (`openai/gpt-6-luna`, F12) is not independent of OpenAI. Confidence is shown as the list of groups, not as a numeric score.

## 7. Decision record: mapping R0 to R4

### 7.1 Mapping

| Rule | Reads | Condition in fields | outcome | hypothesis, assumption_refs |
|---|---|---|---|---|
| R0 | `citation_rate.engine_prompt`, `mention_rate.engine_prompt` per enabled engine | capture-dependent rules lack sufficient n (see fix below) | `insufficient_evidence` | false, [A7] |
| R1 | `blocking_fail.key_pages` | `value >= 1` | `seo_first` | true, [A6, A7] |
| R2 | `contradiction_rate.engine`, claims | page checks pass, at least one `contradicted` or `outdated` rule-matcher claim reproduced per `K_CONTRA_REPRODUCE` (placeholder) | `geo_fix_facts` | false, [A7] |
| R3 | `citation_rate.engine` (and or `mention_rate`, see fix) | page checks pass, R2 not fired, rate below `T_LOW` (placeholder) in >= 2 distinct vendor groups each with `n >= N_MIN_ENGINE` | `geo_content` | true, [A7] |
| R4 | all of the above | none fired, all inputs sufficient | `no_action` | false, [A7] |

Each rule's `evaluations` entry records `result`, a `reason_code` and the ids it read, so the report's "Why this rule fired" and "why the others did not" are generated from fields only.

### 7.2 Ambiguities and proposed fixes

| # | Rule | Problem | Proposed fix |
|---|---|---|---|
| D1 | R0 order | R0 is listed first, but R1 needs no captures. With R0 first, a site with a hard SEO failure and too few captures would get "insufficient evidence" instead of "SEO first". | Evaluate R1 first, then R0 as a gate on R2 to R4. |
| D2 | R0 scope | "n per engine per prompt below minimum" does not say whether one thin prompt blocks everything. | Per-prompt statistics below minimum become `Insufficient` and are excluded from engine pooling. R0 fires when fewer than `MIN_ENGINES` (2, from PLAN R3) vendor groups have a sufficient engine-level rate. |
| D3 | R0 vs Step 0 | Step 0 runs 2 repeats (PLAN 5) while the placeholder minimum is 3 (PLAN 4.6). Every Step 0 statistic would be `Insufficient` and every decision R0, unless R1 fires. | Either raise Step 0 repeats to 3 (the $1 cap must be re-checked; PLAN 5 already says 180 calls exceed it) or run Step 0 with `N_MIN_REPEATS` marked as a Step 0 override in `thresholds` with status `placeholder`. Lead decides. |
| D4 | R1 | "Key pages" and "content absent from raw HTML" are undefined, so R1 is untestable. | `manifest.key_pages` and `manifest.key_content` (expected strings, optionally tied to fact keys). |
| D5 | R1 and not_checkable | If a blocking key-page check is `not_checkable`, "page checks pass" is neither true nor false. | R1 result `unknown`; cascade stops with `insufficient_evidence`, reason `page_checks_incomplete`. |
| D6 | R2 | One contradicted claim from one repeat may be noise; "claims about site facts" is undefined. | Only rule-matcher claims with a `fact_key` count. Require reproduction across `K_CONTRA_REPRODUCE` (placeholder) ok captures of the same fact_key. |
| D7 | R2 `outdated` | Needs a prior value of the fact; facts.json has no history yet (U4). | W3 adds prior values with validity dates; until then the matcher cannot emit `outdated` and such cases are `contradicted`. |
| D8 | R3 | "mention/citation rate low" mixes two statistics and "low" has no threshold. | Pick one primary statistic (proposal: `citation_rate.engine`; `mention_rate` reported, not decisive). `T_LOW` placeholder. |
| D9 | R3 | "Independent engines" undefined. | Distinct `vendor:` groups (6.4). |
| D10 | R4 | "None of the above" could fire when evidence was insufficient. | R4 requires R0 not fired and R1 result not `unknown`. |
| D11 | All | PLAN draft puts one `n` and one `label` on the decision. | Replace with `numbers[]` (each with its own n and label) and `confidence_basis`. |

Placeholders introduced (no values invented): `N_MIN_ENGINE`, `K_CONTRA_REPRODUCE`, `T_LOW`, `TERMS_MAX_AGE_DAYS` (PLAN says monthly; value not fixed here), `max_attempts`, `repeat_agreement` minimum, `contradiction_rate` minimum. Values taken from PLAN: `N_MIN_REPEATS` = 3 (placeholder), `MIN_ENGINES` = 2.

## 8. Test-oriented invariants for W5

| # | Name | Input | Expected |
|---|---|---|---|
| T1 | `id_replay_stable` | Build a capture id twice from the same identity dict; then change only `repeat_index`; then change only `run_id` | First two equal; the other two differ from it and from each other; all match RECORD_ID |
| T2 | `id_mismatch_rejected` | capture record whose `id` hash part has one hex digit changed | Validator returns `E_ID_MISMATCH` |
| T3 | `terms_gate_writer` | Engine snapshot `terms_status = unverified`; adapter is a mock | Writer raises before the adapter is called (call count 0); no line in captures.jsonl; slot in `skipped_slots` with `terms_gate` |
| T4 | `terms_gate_validator` | captures.jsonl hand-edited to contain a capture with `terms_status = verified-restricted` | `E_TERMS_GATE` |
| T5 | `raw_hash_tamper` | Sealed run; flip one byte of a raw file | `E_RAW_HASH` and `E_SEAL_MISMATCH`; render refuses |
| T6 | `claim_refs` | (a) claim whose `capture_id` points to a `failed` capture; (b) claim with `fact_key` absent from facts snapshot; (c) `statement` differs from span | `E_REF_CAPTURE`; `E_REF_FACT`; `E_CLAIM_SPAN` |
| T7 | `verdict_downgrade` | claim `verdict = matched`, `verdict_basis = undecided`; and an `llm` claim with `contradicted` | `E_VERDICT`; `E_VERDICT_LLM` |
| T8 | `failed_excluded_and_exposed` | One (engine, prompt): 4 ok captures (2 cite site), 1 failed, 1 refused, `min_n = 3` | Number `value = 2`, `n = 4`, `excluded` has the 2 ids; rendered output contains both excluded ids; `failure_rate` Number is `2` of `6` |
| T9 | `renderer_rejects_bad_numbers` | Numbers with: empty `evidence_ids`; `n = 2` with 3 ids; `n = 2 < min_n = 3`; one unresolvable id | `E_EVIDENCE_EMPTY`; `E_N_MISMATCH`; `E_N_BELOW_MIN`; `E_EVIDENCE_UNRESOLVED`; no report file created |
| T10 | `renderer_label_and_type` | (a) Measured Number with an `src_` id; (b) Estimated Number with empty `basis_labels`; (c) `Text("3 of 5 engines")`; (d) a bare `int` fragment | `E_LABEL_MIXED` (a, b); `E_STRAY_DIGIT`; `E_TYPE` |
| T11 | `footer_and_not_checked` | Valid report model with no caller-supplied footer; then the same with a decision whose `not_checked` is empty | First renders and contains the API-model footer and all baseline not_checked items; second fails `E_NOT_CHECKED_MISSING` |
| T12 | `decision_cascade` | Fixture A: blocking key-page fail plus a contradicted claim, captures with 2 repeats. Fixture B: all pages pass, 2 ok repeats per prompt, `N_MIN_REPEATS = 3` | A: outcome `seo_first`, `fired_rule_id = R1`, `hypothesis = true`, `A6` in `assumption_refs`. B: outcome `insufficient_evidence`, `R0` |

## 9. Open questions and fallback

### 9.1 Open questions

| # | Question | Default until answered |
|---|---|---|
| Q1 | Should refusals stay out of content-rate denominators (brief) even though a refusal is model behaviour? | Excluded and exposed, plus `failure_rate` shows them |
| Q2 | Step 0 repeats vs `N_MIN_REPEATS` (D3) | Lead decides |
| Q3 | Primary R3 statistic: citation or mention rate (D8) | Citation rate |
| Q4 | facts.json history for `outdated`, fact key grammar, repo id (U4, D7) | W3 |
| Q5 | Provider field mapping for `refused`, `usage`, billed cost (U1, U2) | Per-adapter fixture tests in Step 3 |
| Q6 | Where `.geo-evidence/` lives (project directory vs user home) | Current working directory, overridable |
| Q7 | Will an LLM matcher ever decide verdicts? | No in MVP; `llm` limited to `needs_review` (V20) |
| Q8 | `model_vendor` for `perplexity/sonar` (Perplexity or Meta, given the Llama license in W1 2.3) | `perplexity`, flagged as U3 |

### 9.2 Fallback

- If identity-hash ids prove awkward, switch to `uuid4` ids with the same validator, seal and renderer contract. Traceability holds; replay stability (F6) is lost and would be checked by comparing `series_key` and content hashes instead.
- If JSONL validation becomes slow, add a derived sqlite index rebuilt from JSONL; JSONL stays the source of truth.
- If a run crashes mid-write, `seal --salvage` drops only a torn final line, records it in `not_checked`, and seals; nothing else is repaired.
- If the strict renderer blocks Step 0 reporting, the answer is `Insufficient` blocks, never a bypass flag.

## 10. Required changes to PLAN.md section 4.4

1. IDs: replace timestamp-based ids with identity-hash ids (2.3, 2.4); claim ids no longer nest the capture id; add `run_id`, `identity_sha256`, `schema_version` to every record; add the run manifest and seal.
2. Add auxiliary references `fct_` and `src_` so First-party and Published numbers can cite evidence (F1 names only capture and page_check ids).
3. capture: rename `run_index` to `repeat_index`; add `attempt`, `engine_snapshot` (with `model_vendor`, terms fields, `opt_in`, `price_snapshot`), `prompt_sha256`, `completed_at`, `error_class`, `request_sha256`, `raw_sha256`, `usage`, `series_key`; split cost into `cost_estimate_usd`, `cost_from_usage_usd`, `cost_billed_usd` as decimal strings.
4. page_check: add `check_version`, `url_role`, `agent_profile`, `final_url`, `http_status`, `redirect_chain`, `response_headers`, `raw_sha256`, `blocking_on_fail`, `not_checkable_reason`, `derived_from_raw`.
5. claim: add `span_start`, `span_end`, `facts_sha256`, `fact_ref`, `fact_value_snapshot`, `verdict_basis`, `matcher_version`; `quote` becomes `statement` checked against the span; `llm` matcher limited to `needs_review`.
6. decision: remove decision-level `n` and `label`; add `outcome`, `fired_rule_id`, `evaluations`, `numbers[]`, `hypothesis`, `assumption_refs`, `confidence_basis` (groups), `thresholds_snapshot`, `why`.
7. Renderer rule ("fails if n or ids missing") becomes the full contract in section 5, including the typed-fragment rule and `E_STRAY_DIGIT`.
8. Related changes outside 4.4: PLAN 4.6 rule order R1 before R0 and fixes D1 to D10; PLAN 4.3 add `model_vendor`, `opt_in` and a terms age limit; PLAN 5 resolve the repeats vs minimum conflict (D3).
