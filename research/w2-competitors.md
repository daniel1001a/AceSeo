# W2: Open-source competitor check (Elmo, OneGlanse, mcp-geo, Ansvisor, AutoSEO)

Retrieved: 2026-10-19, via the GitHub API (repo metadata, file trees, raw files) and the READMEs/docs listed under Sources. Nothing was cloned, run, or signed up for. "Not found in docs" means not visible in the README, docs, or files I read; it does not mean the feature is absent.

Identification note: "mcp-geo" is ambiguous. TencentEdgeOne/mcp-geo and webcoderz/MCP-Geo are geolocation tools. The only GEO (generative engine optimization) match is AKzar1el/mcp-geo (npm `@digestseo/mcp-geo`, "DigestSEO"). All mcp-geo findings below refer to that repo.

## Comparison table

| | Elmo | OneGlanse | mcp-geo (AKzar1el) | Ansvisor | AutoSEO |
|---|---|---|---|---|---|
| Repo | github.com/elmohq/elmo | github.com/oneglanse/oneglanse | github.com/AKzar1el/mcp-geo | github.com/ansvisor/ansvisor | github.com/codextde/autoseo |
| License | MIT | MIT | MIT | MIT (Empler AI Inc) | MIT in LICENSE file (GitHub reports NOASSERTION because of an appended third-party notice) |
| Stars | 470 | 222 | 38 | 148 | 16 |
| Last commit | 2026-10-17 | 2026-10-03 | 2026-09-24 | 2026-10-19 | 2026-10-09 |
| Stack | TypeScript, TanStack Start, PostgreSQL, pg-boss, Docker | TypeScript, pnpm, Playwright + Camoufox, Docker | TypeScript, Cloudflare Workers + D1, or local stdio + SQLite | TypeScript/JS, Next.js 16, Express, Supabase | TypeScript, Next.js 16, PostgreSQL 17, Drizzle |
| Data source | Mixed: scraping providers (BrightData, Cloro, DataForSEO) for ChatGPT, AI Mode, AI Overviews, Gemini, Perplexity, Copilot; direct APIs (OpenAI, Anthropic, Mistral, OpenRouter) | Scrapes consumer web UIs (ChatGPT, Perplexity, Gemini, Claude, AI Overview) with the user's logged-in accounts and residential proxies; argues against APIs | Official APIs (OpenAI, Anthropic, Gemini, Perplexity, xAI) plus SerpAPI (third-party SERP scraper) for AI Overviews and AI Mode | AI provider APIs via Vercel AI SDK plus Cloro scraping service (required); optional DataForSEO, Scrape.do | Per engine: DataForSEO, vendor API, or the user's local Claude Code / Codex CLI; engines without a provider can be "simulated by an AI model with web search (clearly labelled)". 16 engines |
| Raw evidence and n | Raw engine output stored in Postgres, "any metric can be re-derived"; agent skill requires every number labelled with n and window | Answers and citations saved, individual responses inspectable; n not surfaced (not found in docs) | `raw_response` stored per prompt/run with timestamps; score = mentioning usable responses / usable responses, failures excluded; n not explicit in README | Not found in docs | Answer text stored; fact-check findings keep answer quote and reference passage; n not found in docs |
| Claim ledger | Partial, manual: skill report has a "Wrong facts" section (excerpt, engine, source page), done by the agent | Not found in docs | Not found in docs | Not found in docs (has an F08 "fix brand inconsistency" action) | Yes, LLM-judged: AI statements vs user-uploaded reference documents, six verdicts (matched, contradicted, unsupported, outdated, off_label, needs_review) |
| States what it cannot check | Feature-level only (no prompt volume, crawler analytics, on-page audit) plus a "Do not recommend" list | Says scores are the analysis model's "reading of the text" | Yes: methodology doc section "What the audit does not claim" | Not found in docs | Labels simulated engines and AI-estimated SEO data; no per-check list found |
| SEO vs GEO decision layer | Not found in docs (only a blog post on AEO vs SEO) | Not found in docs | Not found in docs | Partial: action engine (about 60 definitions) mixing Search Console and AI signals, 7-factor priority score with "Why this priority?" | Partial: "Prioritised tasks" generated from all datasets |
| Traditional SEO page checks | AI-access only (robots per AI crawler, fetch as crawler, noindex/nosnippet, content in raw HTML) | No | No | Yes: site audit (authority, content, E-E-A-T, structure rubric) | Yes: crawler with 29 technical checks, Lighthouse, rank tracking, backlinks |
| Deployment | Self-hosted (MIT) or Elmo Cloud from $29/mo | Local or self-hosted only; PostHog telemetry (hashed ids) | Local stdio or self-hosted Worker; optional paid EUR 99 human audit | Self-hosted or Ansvisor Cloud | Self-hosted or AutoSEO Cloud $50/mo |

## Differentiator verdicts

1. **Official APIs only: partially covered by mcp-geo.** mcp-geo uses official model APIs for five providers but adds SerpAPI for Google AI surfaces. Elmo, Ansvisor and AutoSEO mix APIs with scraping providers or local CLI agents; OneGlanse deliberately scrapes UIs. A strict "official APIs only, no scrapers" policy was not found in any of the five, so the strict form remains ours, but it is a policy choice rather than a capability gap.
2. **Every conclusion carries raw evidence and n: partially covered by Elmo (near full) and mcp-geo.** Elmo stores raw engine output and its skill mandates "Measured (from tracked runs, with n and window)" and "Report rates, not ranks". mcp-geo stores `raw_response` and computes rates over usable responses. Neither documents enforcement of n on every number shown in the product UI. Our claim is defensible only if enforced in code on every output, not as a guideline.
3. **Code-generated facts.json used in a claim ledger: partially covered by AutoSEO.** AutoSEO's fact check (src/server/optimize/fact-check/run.ts) compares extracted AI statements against reference documents with an LLM (`runLlm`) and six verdicts plus quotes. The difference: its facts come from user-uploaded documents (PDF, text, URL), not facts extracted by code from the crawled site, and it has no deterministic fact file. Elmo's "Wrong facts" is manual. The code-generated site-fact source is still unique among these five.
4. **Explicit list of what cannot be checked: partially covered by mcp-geo.** mcp-geo's methodology doc has a "What the audit does not claim" section (one run is not every answer, not an official ranking, cited is not recommended, no outcome guarantee, surfaces may return nothing). It is a static doc, not a per-run list. OneGlanse and AutoSEO add honest labels. A per-report, machine-emitted "not checked" list was not found in docs.
5. **SEO-vs-GEO decision layer: partially covered by Ansvisor.** Ansvisor's action center ranks one queue across search and AI signals (for example F12 improve low-CTR pages, F13 align search and AI content, R10 recover search performance) with a 7-factor priority and a generated "Why this priority?". AutoSEO has prioritised tasks across datasets. Neither frames an explicit "fix traditional SEO first or invest in GEO" decision. Our framing is unique; the underlying prioritisation is not.

Net: none of the five differentiators is "confirmed unique" in isolation. What is not found in any one project is the combination: official APIs only, n on every conclusion, code-extracted site facts, a per-run cannot-check list, and an SEO-vs-GEO call, in a local-first tool with no account.

## Risks to our positioning

- **API validity attack.** OneGlanse cites a Surfer 2026 study (21.3% to 31.6% brand overlap between API and UI answers). "Official APIs only" can be read as "measures something users never see". We must label results as API-model behaviour, never as "what ChatGPT users see".
- **Elmo owns the evidence narrative.** 470 stars, active, raw output stored, n-and-window rules, a "Do not recommend" list. Our "evidence-first" pitch sounds like Elmo unless enforcement in code is visible.
- **AutoSEO already ships a fact-check ledger** with verdicts, severity and accuracy trends, inside a full SEO suite. If we describe our ledger as "fact-check AI answers", it is not new.
- **Ansvisor's action engine is mature** (about 60 tested action definitions, Search Console integration). A thin decision layer will look weak next to it.
- **mcp-geo is the closest in philosophy** (local stdio, official APIs, explicit non-claims) and could add the rest cheaply.
- Outside the five: limelit-co/open (Go, SQLite, BYOK, MCP-first) and Auriti-Labs/geo-optimizer-skill (about 1125 stars) target the same local/agent niche.

## Borrow

- Elmo: number labels (Measured / First-party / Published / Estimated), "rates not ranks", the evidence-backed "Do not recommend" list (llms.txt, schema as a citation lever, composite GEO scores), and the AI-access checks in scripts/check_ai_access.py (fetch as each crawler, content present in raw HTML).
- mcp-geo: exclude failed responses from the denominator and expose them; the "does not claim" structure as a seed for our cannot-check list.
- AutoSEO: verdict taxonomy (matched, contradicted, unsupported, outdated, needs_review) and the rule that downgrades unsure verdicts to needs_review.
- Ansvisor: "Why this priority?" generated from the facts the score rests on; confidence counted as independent kinds of evidence, not repeated signals; deterministic tie-breaks.
- OneGlanse: plain statement that LLM scores are a model's reading, not ground truth.

## Avoid

- Composite health or GEO scores with invented weights (Ansvisor rubric, AutoSEO health score); Elmo itself argues against them.
- Consumer UI scraping with stealth browsers and residential proxies (OneGlanse); it conflicts with our official-API rule and provider terms.
- Mixing simulated or AI-estimated data with measured data (AutoSEO labels it, but it blurs the evidence line).
- All-in-one suite scope creep (AutoSEO, Ansvisor); we cannot win on breadth.
- Default-on telemetry in a local-first tool.

## Sources (all retrieved 2026-10-19)

- Elmo: https://github.com/elmohq/elmo (README, skills/aeo/SKILL.md, scripts/check_ai_access.py)
- OneGlanse: https://github.com/oneglanse/oneglanse (README)
- mcp-geo: https://github.com/AKzar1el/mcp-geo (README, docs/ai-visibility-audit-methodology.md, schema and SerpAPI provider source)
- Ansvisor: https://github.com/ansvisor/ansvisor (README, server/src/lib/action-center/priority.js, candidates.js, definitions/f13-align-search-and-ai-content.js, server/src/lib/audit tree)
- AutoSEO: https://github.com/codextde/autoseo (README, LICENSE, src/server/optimize/fact-check/run.ts, cloud/src/components/marketing/catalog/en/features/ai-fact-check.ts)
- Repo metadata (stars, license, last commit): GitHub REST API `repos/{owner}/{repo}` and `commits`
