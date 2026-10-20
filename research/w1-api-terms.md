# W1: AI provider API terms for storing and analyzing answers and citations

Scope: can a local-first, open-source SEO/GEO evidence tool call each provider's API with web search, store the answer text and the cited URLs, and analyze them to produce optimization recommendations for a website owner?

Method: primary sources only (official terms, policies and API docs). Every page below was retrieved on 2026-10-19. Quotes are 15 words or fewer. Anything that could not be read directly from an official page is marked UNVERIFIED. No accounts were created, no credentials were entered and no paid API was called.

Note on reading the terms: none of the general API terms for OpenAI, Anthropic, Perplexity or xAI contains a clause that expressly permits or forbids "storing" or "analyzing" Output. Where a classification says ALLOWED, the basis is (a) the terms assign ownership of Output to the customer, and (b) no clause restricting storage or analysis was found on the pages read. Google is the only provider with an express prohibition on analysis.

## 1. Summary table

| Provider | Classification | One-line reason |
| --- | --- | --- |
| OpenAI Responses API + `web_search` (`gpt-5-mini`) | VERIFIED-ALLOWED | Customer owns Output and no storage or analysis restriction exists; citations must be visible and clickable when shown to end users. |
| Anthropic Messages API + `web_search` (`claude-haiku-4-5` / `claude-haiku-5-5`) | VERIFIED-ALLOWED | Customer owns Outputs and no storage restriction exists; citations must accompany displayed outputs, and the AUP bars source-seeding manipulation. |
| Perplexity Agent API (and legacy Sonar) | VERIFIED-ALLOWED (with caveats) | Customer owns all Output; the license covers receiving and displaying Output in the customer's app; Third-Party model terms also apply. |
| xAI (Grok), default OFF | UNVERIFIED (ambiguous) | Customer owns Output, but the AUP bans "harvesting ... any Input or Output" and bot access; it is unclear whether that covers systematic storage. |
| Google Gemini grounding with Google Search | VERIFIED-RESTRICTED | Terms forbid you to "analyze, train on, or otherwise learn from Grounded Results". |

## 2. Per-provider details

### 2.1 OpenAI

**Model ID (verified)**
- Model `gpt-5-mini`, snapshot `gpt-5-mini-2025-08-07`. Web search is listed as a supported tool on the Responses API, and Batch is supported.
  Source: https://developers.openai.com/api/docs/models/gpt-5-mini (retrieved 2026-10-19).
- The same page recommends "GPT-5.6 Terra" for "most new low-latency, high-volume workloads". The web search guide recommends gpt-5.5 for new integrations and does not mention gpt-5-mini. gpt-5-mini remains listed and supported.

**Storing and analyzing outputs: allowed**
- Services Agreement, section 4.1: Customer "owns all Output", and OpenAI assigns its rights in Output to Customer.
  Source: https://openai.com/policies/services-agreement/ ("Updated: December 1, 2025"; "Effective: January 1, 2026"; retrieved 2026-10-19).
- The agreement has no clause restricting storage, caching or analysis of Output.
- Restrictions that do apply:
  - Section 3.3(e): no using Output to develop AI models that compete with OpenAI, except for a "Permitted Exception". That exception covers in-house classifiers or embeddings that are not distributed, and OpenAI fine-tuning.
  - Section 3.3(f): no extracting data from the Services "other than as permitted".
  - Section 3.3(h): no circumventing rate limits.
  - Section 3.4: Third-Party Services are governed by their own terms.
- Service Terms (https://openai.com/policies/service-terms/, "Updated: October 16, 2026"; retrieved 2026-10-19) have no section specific to web search.
- Usage Policies (https://openai.com/policies/usage-policies/, "Effective: October 29, 2025"; retrieved 2026-10-19) prohibit "deceit, fraud, scams, spam, or impersonation". They say nothing about SEO, GEO or scraping.

**Citation and attribution rules**
- When web results are displayed to end users, "inline citations must be made clearly visible and clickable in your user interface".
  Source: https://developers.openai.com/api/docs/guides/tools-web-search (retrieved 2026-10-19).
- Citations are returned as `url_citation` annotations.

**Retention**
- Section 4.2 of the Services Agreement: OpenAI does not use Customer Content to improve its services unless the customer agrees.
- On OpenAI's side, the `/v1/responses` endpoint has a 30-day abuse-monitoring retention. Zero Data Retention (ZDR) is available to eligible customers.
  Source: https://developers.openai.com/api/docs/guides/your-data (retrieved 2026-10-19).
- No limit was found on how long the customer may keep Output.

**Caching limits**
- None found for Output.

**Rate limits for batch runs**
- Web search follows the tiered rate limits of the underlying model. Search context is capped at 128k.
- Web search is not supported on gpt-5 with `minimal` reasoning. Source: web search guide above.
- gpt-5-mini limits, from the model page above:

  | Tier | RPM | TPM | Batch queue limit |
  | --- | --- | --- | --- |
  | Free | not supported | not supported | not supported |
  | Build | 5,000 | 2,000,000 | 20,000,000 |
  | Launch | 10,000 | 10,000,000 | 1,000,000,000 |
  | Grow | 30,000 | 180,000,000 | 15,000,000,000 |

**Pricing**
- Source: https://developers.openai.com/api/docs/pricing (retrieved 2026-10-19).
- Web search (all models): $10.00 per 1k calls, plus search content tokens billed at the model's rates.
- `web_search_preview` on non-reasoning models: $25 per 1k calls, with search content tokens free.
- Token prices:

  | Model | Input per 1M | Cached input per 1M | Output per 1M |
  | --- | --- | --- | --- |
  | gpt-5-mini, standard | $0.25 | $0.025 | $2.00 |
  | gpt-5-mini, Batch or Flex | $0.125 | $0.0125 | $1.00 |
  | gpt-5-nano (comparison) | $0.05 | not recorded | $0.40 |
  | gpt-5.4-mini (comparison) | $0.75 | not recorded | $4.50 |

### 2.2 Anthropic

**Model ID (verified)**
- `claude-haiku-4-5-20251001` has status "Active", with retirement "Not sooner than October 15, 2026".
  Source: https://platform.claude.com/docs/en/about-claude/model-deprecations (retrieved 2026-10-19).
  That date has already passed (today is 2026-10-19), so the model can be retired once notice is given.
- `claude-haiku-5-5` is the current Haiku. It is Active, with retirement not sooner than October 7, 2027.
  Sources: https://platform.claude.com/docs/en/about-claude/models/overview and the deprecations page (retrieved 2026-10-19).

**Storing and analyzing outputs: allowed**
- Commercial Terms: Customer "owns its Outputs", and Anthropic assigns its rights.
  Source: https://www.anthropic.com/legal/commercial-terms ("Effective June 17, 2025"; retrieved 2026-10-19).
- The Commercial Terms have no clause restricting storage or analysis.
- Restrictions that do apply:
  - Section D.4: no access "to build a competing product or service, including to train competing AI models".
  - Section A.2: Third Party Features are not part of the Services.
- Usage Policy: https://www.anthropic.com/legal/aup ("Effective November 12, 2026"; retrieved 2026-10-19). Under "Do Not Engage in Deceptive Campaigns or Artificial Activity", it prohibits using the service to:
  - "Manipulate the sources from which search engines or AI systems draw answers". The full clause covers seeding sources with content that misrepresents its origin, authorship or independence.
  - build tools that facilitate astroturfing or sockpuppets;
  - send spam.

  This limits what the tool may *recommend* when Claude generates the advice. It does not limit storage or analysis.

**Citation and attribution rules**
- "When displaying API outputs directly to end users, citations must be included to the original source."
- If outputs are modified or combined, display citations "as appropriate based on consultation with your legal team".
- The `cited_text`, `title` and `url` fields do not count toward token usage.
- Source: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool (retrieved 2026-10-19).

**Retention**
- "Anthropic may not train models on Customer Content from Services" (Commercial Terms).
- The data retention page says conversation content is not retained by default; the exception is "Covered Models", which require 30-day retention.
- The web search tool is listed as eligible for ZDR, except for dynamic filtering.
- Source: https://platform.claude.com/docs/en/manage-claude/api-and-data-retention (retrieved 2026-10-19).
- No limit was found on how long the customer may keep Outputs.

**Caching limits**
- None found for Outputs.

**Tool versions**
- `web_search_20250305`, `web_search_20260209` and `web_search_20260318`. Dynamic filtering requires Claude 4.6 or later.
- `max_uses` caps the number of searches per request.

**Rate limits for batch runs**
- Source: https://platform.claude.com/docs/en/api/rate-limits (retrieved 2026-10-19). Tiers are Start, Build, Scale and Custom.
- Haiku 4.5 and Haiku 5.5 have the same limits:

  | Tier | RPM | ITPM | OTPM |
  | --- | --- | --- | --- |
  | Start | 1,000 | 2,000,000 | 400,000 |
  | Build | 5,000 | 5,000,000 | 1,000,000 |
  | Scale | 10,000 | 10,000,000 | 2,000,000 |

**Pricing**
- Web search: "$10 per 1,000 searches, plus standard token costs for search-generated content". Source: web search tool page above.
- Token prices, from https://platform.claude.com/docs/en/about-claude/pricing (retrieved 2026-10-19), per 1M tokens:

  | Model | Input | Output | 5m cache write | 1h cache write | Cache hit | Batch input / output |
  | --- | --- | --- | --- | --- | --- | --- |
  | Haiku 4.5 | $1 | $5 | $1.25 | $2 | $0.10 | $0.50 / $2.50 |
  | Haiku 5.5, prompts up to 100k | $0.10 | $0.50 | $0.125 | $0.20 | $0.01 | $0.05 / $0.25 |
  | Haiku 5.5, prompts over 100k | $0.50 | $2.50 | not recorded | not recorded | not recorded | not recorded |

- The Batch API gives a 50% discount.

### 2.3 Perplexity

**Does the "Agent API" exist under that name? Yes, verified.**
- https://docs.perplexity.ai/llms.txt names the Agent API as the default for web-grounded AI.
- The endpoint is `POST https://api.perplexity.ai/v1/agent`. Presets are `fast`, `low`, `medium`, `high` and `xhigh`.
- Source: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/overview.md (retrieved 2026-10-19):
  - "Sonar Chat Completions support ended on September 27, 2026."
  - Synchronous and streaming Sonar requests are being reformulated as Agent API requests. Async Sonar requests are no longer supported.
  - Preset mapping: Sonar and Sonar Pro map to `fast`; Sonar Reasoning Pro maps to `low`; Sonar Deep Research maps to `high`.
- Agent API responses carry a `search_results` output item with url, title, snippet and date.
- The `fast` preset currently uses model `openai/gpt-6-luna` with service tier `priority`, `max_steps` 1, and `web_search` with `search_type: "fast"`.
  Source: https://docs.perplexity.ai/docs/agent-api/presets.md (retrieved 2026-10-19).

**Storing and analyzing outputs: allowed, with caveats**
- Source: https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service ("Last updated: January 23, 2026"; retrieved 2026-10-19). The terms cover the "Sonar by Perplexity and/or Agentic Research" API services.
- Section 2.3.1: Customer "owns all Output", and Perplexity assigns any rights it has.
- Section 2.1(ii): the license lets Customer submit Input, receive Output, and "display such Output, in each case, solely within the Customer Applications". This is a license to use the Services. The page has no clause restricting storage or analysis of Output, which the customer owns.
- Section 2.5: Perplexity may deactivate keys for an application it deems "competitive with Perplexity".
- AUP (https://www.perplexity.ai/hub/legal/aup, "Last updated: July 8th, 2025"; retrieved 2026-10-19) forbids:
  - products "competitive with, similar to, or that would otherwise be a substitute for the Services";
  - using the Services "on a service bureau or similar basis";
  - creating disinformation, manipulative content, or unsolicited advertising.

  An SEO evidence tool is not a search or answer engine, but this is a judgment call. See section 3.
- Section 2.6, Third-Party Models: when a third-party model is used through the Agent API, that provider's terms also apply. The list is at https://www.perplexity.ai/hub/legal/third-party-models ("Last updated: November 25th, 2025"; retrieved 2026-10-19):
  - GPT models: OpenAI terms apply. This includes the `fast` preset model.
  - Claude models: Anthropic terms apply.
  - Grok models: xAI terms apply.
  - Gemini models: Google terms apply, including ai.google.dev/gemini-api/terms.
  - Sonar models: Meta Llama license terms apply.
- Search API addendum: https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service-search ("Last updated: September 22, 2025"; retrieved 2026-10-19). It applies only to the `/search` endpoint, not to the Agent API. Under it:
  - "Customer does not own" the Search API's Output.
  - Perplexity may retain and use Search Data.
  - Personal Data may not be submitted.

  Avoid `/search` for stored evidence.

**Citation and attribution rules**
- The API terms contain no attribution or citation clause (searched for "attribut" and "citation" with no match).
- No display rule was found on the web search tool page (https://docs.perplexity.ai/docs/agent-api/tools/web-search.md, retrieved 2026-10-19).
- When a third-party model is used, that provider's display rules may apply. For example, OpenAI's clickable-citation rule may apply to the `fast` preset; this inference was not verified on a Perplexity page.

**Retention and training**
- Section 2.3.3: Perplexity "shall not use" Customer Content to train generative models.
- FAQ: "By default, the API has zero day retention of user prompt data". The FAQ also says Perplexity does not train on API data.
  Source: https://docs.perplexity.ai/docs/resources/faq.md (retrieved 2026-10-19).
- Perplexity may use Usage Data (metadata) for any lawful purpose.
- No limit was found on how long the customer may keep Output.

**Rate limits for batch runs**
- Source: https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers.md (retrieved 2026-10-19).
- Tiers are based on lifetime credit purchases: Tier 0 at $0, Tier 1 at $50+, through Tier 5 at $5,000+.
- Agent API request limit, shared across all models and keys (polls count too):

  | Tier | QPS |
  | --- | --- |
  | Tier 0 | 1 |
  | Tier 1 | 3 |
  | Tier 2 | 8 |
  | Tier 3 | 17 |
  | Tier 4 | 33 |
  | Tier 5 | 33 |

- Token limits, per model:

  | Tier | TPM | TPH |
  | --- | --- | --- |
  | Tier 0 | 5,000,000 | 300,000,000 |
  | Tier 5 | 16,000,000 | 960,000,000 |

- Section 2.7 of the terms lets Perplexity throttle traffic or temporarily lower limits.

**Pricing**
- Source: https://docs.perplexity.ai/docs/getting-started/pricing.md (retrieved 2026-10-19).
- Agent API tool fees:
  - `web_search` standard: $0.0025 per invocation ($2.50 per 1,000).
  - `web_search` fast: $0.001 per invocation ($1.00 per 1,000).
  - `fetch_url`: $0.0005 per invocation.
- Search API: $5 per 1K requests ($1 per 1K with fast search), with no token charges.
- Service tiers multiply token rates: `flex` at 0.5x and `priority` at 2x, only for models that list those tiers.
- Token prices, per 1M tokens, from https://docs.perplexity.ai/docs/agent-api/models.md (retrieved 2026-10-19):

  | Model | Input | Output | Cache read |
  | --- | --- | --- | --- |
  | `perplexity/sonar` | $0.25 | $2.50 | $0.0625 |
  | `openai/gpt-6-luna`, up to 272k (used by `fast` at 2x priority) | $0.10 | $0.50 | not recorded |
  | `anthropic/claude-haiku-5-5`, up to 100k | $0.10 | $0.50 | not recorded |
  | `xai/grok-4.7`, under 200k | $2 | $6 | not recorded |

### 2.4 xAI (Grok), default OFF

**Storing and analyzing outputs: UNVERIFIED (ambiguous)**
- Terms of Service - Enterprise: https://x.ai/legal/terms-of-service-enterprise ("Last Updated: August 14, 2026"; retrieved 2026-10-19 via browser, since curl returned 403). The contracting party is named "SpaceXAI LLC" ("SpaceXSI").
  - Customer "owns all right, title, and interest in the Output in perpetuity".
  - Customer will not use Output to train AI systems, except as an Order Form permits.
  - Customer will not use the Services "except as expressly authorized under this Agreement".
- Acceptable Use Policy: https://x.ai/legal/acceptable-use-policy ("Effective: August 14, 2026"; retrieved 2026-10-19). It prohibits:
  - "Scraping, harvesting or reselling any Input or Output";
  - "using bots to access" the Service, together with copying and distributing;
  - using Output to develop products "that compete with SpaceXSI".
- The terms grant ownership of Output, but "harvesting ... Output" is undefined. A batch tool that systematically collects and stores Grok answers could fall under it. Under the "ambiguous means UNVERIFIED" rule, this stays UNVERIFIED and the engine stays OFF.

**Citation and attribution rules**
- No display or attribution rule was found on the web search guide (https://docs.x.ai/developers/tools/web-search, retrieved 2026-10-19).
- Responses return `citations`.

**Retention**
- User Content is deleted no later than 30 days after the session, unless another period applies. ZDR is available.
- xAI may create and use de-identified, aggregated data, except under ZDR.
- xAI will not train on User Content, "subject to disclosures to Customer and Customer-controlled user settings".

**Rate limits**
- Not retrieved.
- From the pricing page: Batch API requests "don't count towards rate limits". The batch discount is 20% for grok-4.3 and the grok-4.20-0309 variants; models not listed, including grok-4.7, get no batch discount.

**Pricing**
- Source: https://docs.x.ai/developers/pricing.md (retrieved 2026-10-19).
- `web_search`: $5 per 1k calls.
- Token prices, per 1M tokens:

  | Model | Input | Cached input | Output |
  | --- | --- | --- | --- |
  | grok-4.7, under 200k | $2.00 | $0.50 | $6.00 |
  | grok-4.3, under 200k | $1.25 | $0.20 | $2.50 |

### 2.5 Google Gemini grounding with Google Search

**Storing and analyzing outputs: VERIFIED-RESTRICTED**
- Source: Gemini API Additional Terms of Service, https://ai.google.dev/gemini-api/terms. The page shows "Last updated 2026-04-28 UTC", and the terms are "Effective March 23, 2026". Retrieved 2026-10-19.
- In the Grounding with Google Search use restrictions, you and your end users will not "cache, frame, syndicate, resell, analyze, train on, or otherwise learn from Grounded Results" or Search Suggestions.
- You may not use Links "to build an index", or use them to identify destination pages for crawling or scraping.
- Click tracking, link tracking and monitoring are not allowed.
- Results may not be modified or interspersed with other content.
- Grounded Results may be shown only with their Search Suggestions, and only to the end user who submitted the prompt.
- Narrow storage exception: you may "copy and store, for up to two (2) years, the text" of Grounded Results, but only for these purposes:
  - to evaluate and optimize how the results display in your app;
  - in the end user's chat history;
  - temporarily, for a refined function-call prompt.

  Cross-site analysis for SEO advice is not among them.
- Google stores prompts and output for 30 days for debugging.
- The page does not limit these restrictions to paid or unpaid use.
- Grounding with Google Maps has a parallel section: no scraping or export, and caching only up to 90 days or within 6 months of chat history.
- Result: the lead's belief is confirmed. Gemini with Google Search grounding must be excluded.

**Pricing and rate limits**
- Not retrieved, because the engine is excluded.

## 3. Unverified items

1. **xAI storage and analysis.** The AUP term "harvesting ... any Input or Output" is ambiguous for systematic storage. xAI rate limits were not retrieved.
2. **Perplexity "competitive / similar / substitute" AUP clause, and Terms section 2.5 "competitive with Perplexity".** Whether a GEO monitoring tool counts as "similar to" the Services is a judgment call. No official page addresses it.
3. **Perplexity citation display obligations.** None were found. Whether OpenAI's clickable-citation rule carries over through a third-party model (for example the `fast` preset's `openai/gpt-6-luna`) is not stated on any Perplexity page.
4. **Perplexity license wording.** Section 2.1(ii) licenses receiving and displaying Output "solely within the Customer Applications". Storage and analysis rest on Output ownership (2.3.1), not on an express grant.
5. **Anthropic "Covered Models".** The data retention page says Covered Models need 30-day retention. Whether Haiku 4.5 or 5.5 is a Covered Model was not checked.
6. **OpenAI web-search-specific retention** beyond the `/v1/responses` table row was not checked in detail.
7. **Gemini pricing and rate limits** were not retrieved, because the engine is out of scope.
8. **Open-source distribution model.** Every provider's terms bind the "Customer", meaning whoever holds the API key. In a local-first, bring-your-own-key design, each end user is the Customer under their own key. This reading is a structural inference, not a quoted term.

Leads (third-party, not verified): none were used.

## 4. Recommended MVP engine set

1. **OpenAI Responses API + `web_search`, model `gpt-5-mini`** (VERIFIED-ALLOWED).
   - Store the answer text and `url_citation` annotations.
   - Any UI that shows the answer must render the citations visible and clickable.
   - Cost: $0.01 per search call plus tokens at $0.25 in / $2.00 out per 1M.
2. **Anthropic Messages API + `web_search`** (VERIFIED-ALLOWED).
   - Default to `claude-haiku-5-5`: it is current, cheaper, and Active until at least 2027-10-07. Offer `claude-haiku-4-5-20251001` only as a legacy option, because its retirement window opened on 2026-10-15.
   - Show citations with displayed outputs.
   - Recommendation prompts must not suggest fake-source or astroturf tactics (AUP).
   - Cost: $0.01 per search call plus tokens.
3. **Perplexity Agent API** (VERIFIED-ALLOWED with caveats), opt-in at first.
   - Prefer an explicit `model: "perplexity/sonar"` with the `web_search` tool over the `fast` preset. This keeps the engine a "Perplexity" answer and avoids priority-tier 2x pricing and OpenAI terms stacking on top. Note that Sonar itself carries the Meta Llama license as Third-Party Terms.
   - Do not use the `/search` endpoint for stored evidence: the customer does not own that Output.
   - Cost: $0.0025 per standard web search or $0.001 per fast search, plus tokens.
4. **xAI**: OFF. Keep it disabled until the "harvesting" question is answered by xAI or by counsel.
5. **Google Gemini grounding with Google Search**: EXCLUDED, because analysis of Grounded Results is prohibited.

Design rules that satisfy all ALLOWED providers:
- Bring-your-own-key, so each user is the Customer.
- Keep stored answers local.
- Keep provider citations attached to any displayed answer.
- Never use stored outputs to train or fine-tune models.
- Respect rate limits, with no limit circumvention or key rotation.
- Make the recommendations generator refuse manipulation tactics such as fake sources, sockpuppets and spam.

## 5. Fallback if a provider is unreadable or its terms change

- If a provider's terms page becomes unreadable, or a re-check finds new storage or analysis restrictions, disable that engine by default. Show the user why, with the clause and URL, and let them re-enable it only after reading the terms themselves.
- The MVP stays viable with **OpenAI + Anthropic only**. Both are VERIFIED-ALLOWED with ownership of Output.
- If Perplexity becomes doubtful, drop it. Do not substitute the Perplexity `/search` endpoint, whose Output the customer does not own.
- Never fall back to Gemini grounding with Google Search: it is expressly restricted.
- Store the terms URL, the "last updated" date and the retrieval date with each engine's config. Re-verify on a schedule, for example monthly, because several pages here changed in 2026: OpenAI Service Terms on Oct 16, the Anthropic AUP on Nov 12, and the xAI terms on Aug 14.
