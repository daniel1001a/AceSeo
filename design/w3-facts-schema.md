# W3: facts.json schema and export flow (design only)

Status: design. No product code written. Sample: `design/boardflight.facts.sample.json`.

## 1. Verified facts

All retrieved by plain GET (curl) on 2026-10-19, UTC times from the response `Date` header unless noted.

| # | Fact | Source | Retrieved |
|---|------|--------|-----------|
| V1 | `https://boardflight.com/` answers `308` with `Location: https://www.boardflight.com/`, body 15 bytes, hash sha256:7c040f86...d76c2 | live HTTP | 20:45:42Z |
| V2 | Following that redirect: `200`, `text/html; charset=utf-8`, 108119 bytes, `server: Vercel`, Next.js assets (`/_next/static/...`) | live HTTP | 20:45:11Z |
| V3 | `/llms.txt` on the apex 308s to `https://www.boardflight.com/llms.txt`, then `200 text/plain; charset=utf-8`, 2964 bytes, etag `3fc4c601...`, `x-matched-path: /llms.txt`, `x-vercel-cache: PRERENDER` | live HTTP | 20:45:11Z |
| V4 | `/airport/jfk` (via the same 308) returns `200 text/html`, 152857 bytes, 2 `application/ld+json` blocks: block 0 is Organization+WebSite, block 1 is Airport+WebPage+BreadcrumbList+FAQPage | live HTTP | 20:45:11Z |
| V5 | `/data` and `/robots.txt` also return 200 after the 308. Not extracted into the sample. robots.txt disallows `/api/` and `/?f=`, declares sitemap `https://www.boardflight.com/sitemap.xml` | live HTTP | 20:45:11Z |
| V6 | llms.txt line 3 says "Covers 33 US airports"; line 5 says security wait is "read at the 88th percentile"; line 7 lists 16 airports passing the TSA shape check; line 21 gives JFK "worst about 30 min at 6 AM" (modeled medians, Thu Aug 13 2026) | llms.txt body, hash sha256:c7f95451...a82a4 | 20:45:11Z |
| V7 | JFK JSON-LD block 1: `@graph[0]` Airport `iataCode` = "JFK"; `@graph[1]` WebPage `dateModified` = "2026-08-25" | /airport/jfk body, hash sha256:131a3db4...b543d | 20:45:11Z |
| V8 | Canonical domain is `www.boardflight.com`, not `boardflight.app`. The GitHub repo metadata lists homepage `https://boardflight.com` | live HTTP; repo metadata via authenticated `gh api` | 20:44-20:45Z |
| V9 | `https://boardflight.app` is a DIFFERENT product (Vite/React SPA, "BoardFlight - More to play on your Board", community games for the Board device). Every path (`/llms.txt`, `/airport/jfk`, `/data`, `/robots.txt`, `/sitemap.xml`) returns the same 2665-byte HTML shell with `200 text/html`. `www.boardflight.app` does not resolve | live HTTP | 20:44:45Z-20:45:01Z |
| V10 | Repo `daniel1001a/boardflight` is PRIVATE (default branch `main`, last push 2026-10-19T13:23:07Z). Unauthenticated raw.githubusercontent.com for `lib/seo/llms-txt.ts` on `main` returns 404 | `gh api repos/...` metadata; raw GET | 20:44:45Z |
| V11 | Public repo `daniel1001a/boardflight-airport-wait-data` exists, `private: false`, default branch `main`. It is linked from llms.txt and from JSON-LD `sameAs`. Contents not inspected | api.github.com unauthenticated GET | 20:45:42Z |

Not verified by any fetch: the AI Overview "inactive" claim itself (not seen by me); that it targeted boardflight.com versus boardflight.app.

## 2. Unverified assumptions

- U1. Contents of `lib/seo/llms-txt.ts`, `lib/seo/data-page-facts.ts`, `lib/seo/structured-data.ts`, `lib/profiles/tiering.ts`: unread (private repo). Their roles are inferred from names only. The llms.txt "Data study" and "TSA check" sections look generated from a data-page-facts module; that is a guess.
- U2. The repo is Next.js/TypeScript (owner statement). Live headers are consistent with Next on Vercel but that is not proof about repo layout.
- U3. Stability classes in the sample (e.g. `dateModified` as `changes_per_deploy`, `site_status` as `changes_daily`) are my judgment, not read from code.
- U4. The "inactive" claim may stem from the boardflight.app / boardflight.com name collision (V9). This is a hypothesis for the claim-extraction worker, not a finding.
- U5. The page `dateModified` may be a build-time constant or derived from data; unknown without the repo.

## 3. Schema

JSON, UTF-8, one object. Hashes are `sha256:<64 lowercase hex>`. Timestamps are ISO 8601 UTC with `Z`, second precision.

### 3.1 Header

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `schema_version` | string semver | yes | Validator picks rules by major version |
| `site` | object | yes | `name`, `canonical_origin` (https origin, no path), `hosts` (list of hostnames the facts may describe), optional `note` |
| `generator` | object | yes | `name`, `version`; optional `sample_notice`. Real files must not set `sample_notice` |
| `generated_at` | datetime | yes | When the file was produced |
| `source_snapshots` | list | yes | Every distinct source fetched or read; facts point to these by `id` |
| `facts` | list | yes | Fact records, sorted by `key` |

Snapshot record:
- `id` (unique string), `kind` (`file|http`)
- http: `request_url`, `final_url`, `status_code`, `redirect_chain` (list of `{status_code, location}`), `response_headers` (allowlisted subset: `content-type`, `etag`, `location`, `last-modified`), `fetched_at`
- file: `repo`, `commit` (full 40-hex SHA), `path`, `read_at`
- both: `bytes` (int), `content_hash` (sha256 of the exact bytes stored/hashed, before any decoding)

### 3.2 Fact

| Field | Type | Req | Notes |
|-------|------|-----|-------|
| `key` | string | yes | Stable id, regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$`. `site_status` is a one-segment key by design. Keys never change meaning; a changed meaning gets a new key |
| `value` | JSON | yes | Must match `value_type`. No null |
| `value_type` | enum | yes | `string, integer, number, boolean, date, datetime, url, enum, string_list, integer_list` |
| `enum_values` | list | iff `enum` | `value` must be a member |
| `source` | object | yes | See below |
| `derived_at` | datetime | yes | When the extractor produced this value |
| `derivation` | string | yes | Extractor rule id, `^[a-z0-9_.]+\.v[0-9]+$` (e.g. `llms_txt.regex.airport_count.v1`). Version bumps when rule logic changes |
| `content_hash` | sha256 | yes | Hash of the source bytes. Must equal the referenced snapshot's `content_hash` |
| `verification` | object | yes | `method` (`refetch_and_extract|reparse_jsonld|http_probe|rehash_file`) and `steps` (non-empty list of strings a human or a stdlib script can follow to re-derive the value) |
| `stability` | enum | yes | `static`, `changes_daily`, `changes_per_deploy` |

`source`:
- `kind` (`file|url|jsonld|http`), `locator` (repo-relative path for file; absolute https URL otherwise), `snapshot_id`
- locator refinement, at least one when the source is multi-valued: `line` (1-based), `json_path` (restricted form `$['k'][i].k`), `jsonld_index` (0-based block order in document), `header` (http header name)
- optional: `excerpt` (<= 200 chars, the matched text, for human review), `fragment_hash` (sha256 of the sub-part, e.g. one JSON-LD block, since whole-page hashes churn)
- http kind: `http` object with `status_code`, `final_url`, `redirects`, `fetched_at`, which must equal the snapshot values

Notes:
- Single-line minified HTML (as /airport/jfk) cannot use `line`; use `jsonld_index` + `json_path`.
- For `http_probe` facts such as `site_status`, the whole-body hash is volatile (home page is `no-store`). `content_hash` identifies the observed snapshot; the verifier compares the mapped value only.
- Mapping `site_status.v1`: final status 200..299 after at most 5 redirects = `live`; 3xx loop or only redirect = `redirect_only`; 4xx/5xx = `error`; DNS or TLS failure = `unreachable`.

### 3.3 How the Claim Ledger uses `stability`

- `static`: a claim that disagrees is `contradicted`.
- `changes_per_deploy` or `changes_daily`: a disagreeing claim is `outdated` only if there is evidence it was once true or it predates `derived_at` (kept via prior facts.json versions in a local history dir); otherwise `contradicted`. `changes_daily` facts older than 24h at comparison time are marked `stale` and require re-derivation before any contradiction verdict.
- `site_status = live` contradicts "inactive" / "down" / "parked" claims about hosts in `site.hosts` only. Claims about other domains (e.g. boardflight.app) are out of scope and should be reported as `wrong_entity`, not contradicted.

## 4. Validation rules

A stdlib-only validator (json, re, hashlib, datetime, urllib.parse) must enforce:

1. Valid UTF-8 JSON, top-level object, no duplicate keys (use `object_pairs_hook` to detect), no NaN/Infinity.
2. `schema_version` present and major version supported; unknown top-level fields rejected (strict), unknown fact fields rejected.
3. All required fields present; types exact (`bool` is not `integer`; integers are not floats).
4. `key` matches regex; keys unique; facts sorted by key (determinism check).
5. `value` conforms to `value_type`: dates `YYYY-MM-DD` and real calendar dates; datetimes end in `Z`; `url` is https with host in `site.hosts`; list types non-empty homogeneous lists, sorted when the extractor declares the list a set.
6. `enum`: `enum_values` present, unique, `value` in it.
7. Every `source.snapshot_id` resolves; `fact.content_hash == snapshot.content_hash`; `source.kind` consistent with snapshot kind (jsonld/url/http map to an http snapshot; file maps to a file snapshot).
8. Hash format `sha256:` + 64 lowercase hex. If the validator is run with `--recheck-local` and snapshot bodies are cached locally, recompute and compare hashes and `bytes`.
9. Timestamps: ISO 8601 UTC with `Z`; `derived_at >= snapshot fetched_at/read_at`; `generated_at >= max(derived_at)`; no timestamp in the future beyond a 5-minute skew.
10. http snapshots: `status_code` int 100..599; `fact.source.http` fields equal the snapshot; for `site_status`, the value must equal the mapping of the snapshot status (rule 3.2); the final URL host must be in `site.hosts`.
11. file snapshots: `commit` 40-hex, `path` relative, no `..`, no absolute paths, no `.env*` or key-like filenames.
12. `locator` host must be in `site.hosts` for url/jsonld/http kinds (prevents facts about other domains such as boardflight.app).
13. `derivation` matches regex; `stability` and `verification.method` in enum; `verification.steps` non-empty.
14. `excerpt`, if present, must occur in the source text at `line` when the validator has the body.
15. `generator.sample_notice` present means the file is a sample; the CLI must refuse to treat a sample as ground truth unless `--allow-sample`.

The validator must REJECT: hand-written files (missing `generator`, or `generator.name` not in an allowlist of known generators), null or empty values, values with no source or an unresolved snapshot, hash mismatches, facts about hosts outside `site.hosts`, secrets-looking values (high-entropy strings, keys matching `token|secret|password|api_key`), duplicate keys, unsorted facts, unknown fields, `content_hash` of an empty body for non-redirect statuses, fetch times later than `generated_at`, excerpts not found in the source, and any `site_status` whose snapshot is not a real HTTP fetch.

## 5. Sample notes

File: `design/boardflight.facts.sample.json`, 8 facts. The generator is labeled `w3-hand-assembled-sample` because I assembled it by hand from observed fetches; a real file must come from code. I cross-checked every value, hash and byte count against the saved response bodies with a throwaway script (all matched).

| key | value | evidence |
|-----|-------|----------|
| `site_status` | live | GET https://boardflight.com/ -> 308 -> 200 at https://www.boardflight.com/, fetched 2026-10-19T20:45:11Z |
| `site.canonical_host` | www.boardflight.com | 308 `Location` header, 20:45:42Z |
| `llms.coverage.airport_count` | 33 | llms.txt line 3 |
| `llms.security_wait.percentile` | 88 | llms.txt line 5 |
| `llms.tsa_check.passing_airports` | AUS BNA BOS DCA EWR HNL JFK LAS LAX LGA PHX SAN SEA SFO SNA TPA | llms.txt line 7 |
| `llms.data_study.jfk.worst_wait_minutes` | 30 | llms.txt line 21 |
| `jsonld.airport.jfk.iata_code` | JFK | JSON-LD block 1, `$['@graph'][0].iataCode` |
| `jsonld.airport.jfk.page_date_modified` | 2026-08-25 | JSON-LD block 1, `$['@graph'][1].dateModified` |

Left out: anything from `/data` (not parsed), anything from the private repo, and any `boardflight.app` fact (different product).

Design observation: the sample is anchored to the apex URL for `site_status` because that is what a user or AI would try first; the 308 is recorded in `redirect_chain`, so a verdict of "live" is never confused with "redirect_only".

## 6. Export flow recommendation

Basis: file names only (repo private, V10). Everything in this section about repo internals is UNVERIFIED (U1).

Principles: read-only, deterministic (sorted keys, fixed number formatting, no wall-clock inside values, timestamps only in `derived_at`/`generated_at`/snapshots), re-runnable (same inputs give byte-identical output except timestamps; support `--now` override for golden tests), no network beyond GET to the site's own hosts and public GitHub.

Two-lane derivation:

1. Repo lane (what the site is meant to say). A local checkout, pinned by commit SHA recorded in a `file` snapshot. Read only these files: `lib/seo/llms-txt.ts` (template and constants behind llms.txt), `lib/seo/data-page-facts.ts` (data-study numbers), `lib/seo/structured-data.ts` (JSON-LD shapes and fields), `lib/profiles/tiering.ts` (which airports are in which tier, hence the 33 / 16 / 8 counts). Extract with restricted regexes or a tiny TS-literal reader over exported constants. If values are computed at build time from data files, the repo lane cannot see final values; it should then emit only structural facts (field names, which airports are tiered) and leave values to the live lane. Never execute repo code, never read `.env*`, `node_modules`, or credentials.
2. Live lane (what crawlers and AI engines actually see). GET `/` (status, redirect, canonical host), `/llms.txt`, `/airport/jfk` (and later each airport), `/data`, `/robots.txt`. Single-pass fetch with a fixed UA string naming the tool, 10s timeout, max 5 redirects, no cookies, one request per URL, snapshot bodies stored locally under a content-addressed name. Extractors run on stored bytes, not on a second fetch, so the hash is guaranteed to match.

Authority: live-lane facts are the ones compared to AI claims (AI engines see the live site). Repo-lane facts are used only for drift detection and for explaining why a live value changed. `site_status` is live-only by definition.

Drift detection: for every key present in both lanes (e.g. `llms.coverage.airport_count` derived from `tiering.ts` versus llms.txt line 3), compare values after normalization. Emit a separate `drift-report.json` (not part of facts.json):
- `match`: same value.
- `live_behind_repo`: repo value differs and the repo commit is newer than the live deployment (compare `meta`/build id or ETag changes, or commit date vs last-seen change). Likely a pending deploy or cache.
- `live_ahead_or_diverged`: live value differs and repo commit is not newer. Treat as an extractor bug or a data-driven value; flag for human review.
- `repo_only` / `live_only`: key not derivable on one side.
Also record per-fact `content_hash` between runs: a changed hash with an unchanged value is benign layout churn; changed value + changed hash with `static` stability is a red flag.

Re-run cadence: `changes_daily` facts on every run; others when `etag` or body hash differs from the previous snapshot (conditional GET with `If-None-Match` is allowed and is still a plain GET).

## 7. Open questions

1. Is `www.boardflight.com` the intended canonical origin for facts, with apex treated as an alias? (Evidence says yes; the owner's mention of "boardflight.app" appears to be wrong or refers to a different project.) Which domain did the AI Overview "inactive" claim name?
2. Does `/llms.txt` content come from `llms-txt.ts` constants or from a build-time data pipeline? Determines how much the repo lane can verify.
3. Should facts for all 33 airport pages be generated, or only airports with a data-page entry? Key scheme proposal: `jsonld.airport.<iata>.*`.
4. What does `dateModified` track (build time, data refresh, manual)? Needed to set the correct stability class.
5. Is the public `boardflight-airport-wait-data` repo a third lane (open dataset claims such as "12 airports, CC BY 4.0" in llms.txt line 30)? The sample leaves it out, and the llms.txt "12 airports" figure differs from the 8 and 33 in the same file; they refer to different things but the Claim Ledger will need entity-scoped keys.
6. Allowlist policy for `generator.name` values and where it is stored so a hand-written file is rejected without being trivially spoofable.
7. History retention: how many previous facts.json versions to keep for the outdated-versus-contradicted decision.

## 8. Fallback if the repo is unreadable

Current state (V10): the repo is private, so the sample and this design are live-only.

- Run live lane only. Header gets `"repo_lane": "unavailable"`; no `file` snapshots; drift report says `live_only` for everything instead of silently omitting.
- Contradiction power is unchanged for site-level and page-level claims, because AI engines read the live site. Loss: cannot say whether a live value is a bug versus intended, and cannot detect a pending deploy.
- Optional middle path that needs no private access: the owner commits or publishes a generated `facts.build.json` as a build artifact (produced by the site's own build), and the CLI treats it as another snapshot with `kind: url`. Not designed here.
- If the owner grants a read-only local checkout later, add the repo lane without changing the schema; only `file` snapshots and `drift-report.json` appear.
