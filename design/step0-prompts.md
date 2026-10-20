# Step 0 prompt list (DRAFT v1, for review)

Status: written by the lead (main thread, Sonnet 5.5), revised after W3 found the correct domain. Not yet reviewed by the user. No API calls have been made.

Domain: `{BRAND}` = BoardFlight, `{DOMAIN}` = `www.boardflight.com` (verified by W3: apex 308 to www, 200; `boardflight.app` is an unrelated product, see design/w3-facts-schema.md V8, V9).

## Design rules

- Three types so Step 0 can separate effects: U (unbranded discovery, site not named), B (branded verification, feeds the Claim Ledger), F (factual lookup a site page could answer).
- Plain user questions. No instruction to cite or mention the site (avoids leading).
- Stable `prompt_id`; wording is frozen once Step 0 starts, because the prompt hash is stored per capture and n is only comparable with identical text.
- `fact_key` column uses the key names in design/boardflight.facts.sample.json. "none yet" means the sample has no matching fact and W3 must add one (or the prompt is dropped) before the Claim Ledger can score it.

## List

| prompt_id | type | lang | prompt | intent | what it tests | fact_key |
|---|---|---|---|---|---|---|
| p_01 | U | en | What is the current TSA security wait time at JFK airport? | airport wait time | Surfaced or cited for wait times at all | none (citation rate only) |
| p_02 | U | en | Which website shows historical TSA wait times by hour for US airports? | airport wait time | Category discovery without naming a site | none (citation rate only) |
| p_03 | U | en | What is the best time of day to go through security at LAX to avoid long lines? | airport wait time | Advice query where site data could be cited | none (citation rate only) |
| p_04 | B | en | What is the difference between boardflight.com and boardflight.app? | domain disambiguation | Tests W3 hypothesis U4 that the "inactive" claim comes from a name collision | site_status, site.canonical_host |
| p_05 | B | en | What is {BRAND}? | site identity | Basic description accuracy | llms.coverage.airport_count (and a purpose fact, none yet) |
| p_06 | B | en | Is {DOMAIN} a legitimate and active website? | site legitimacy | Reproduces the known "inactive" misjudgment | site_status |
| p_07 | B | en | Where does {BRAND} get its airport wait time data from? | data provenance | Claims about data sources | none yet (needs a data-source fact) |
| p_08 | B | en | Is {BRAND} free to use, and does it require an account? | pricing and access | Checkable product claim; llms.txt line 3 says "Free, no account" (W3 did not extract it into the sample) | none yet (W3 to add pricing and account facts) |
| p_09 | F | en | How many US airports does {BRAND} cover? | coverage | Numeric claim vs code-derived fact | llms.coverage.airport_count |
| p_10 | B | zh-TW | {BRAND} 是什麼網站？現在還有在營運嗎？ | identity and status | Language sensitivity of the inactive claim | site_status |

Mix: 3 U, 6 B, 1 F; English-first with one zh-TW.

## Changes since v0

- `{DOMAIN}` set to www.boardflight.com.
- p04 replaced: v0 had a second unbranded advice prompt; now a direct domain-collision prompt. This is a leading-ish branded question by design; treat its results as a hypothesis test, not as a visibility measure.
- p08, p09, p10 keyed to facts or flagged where a fact is missing.

## Notes and caveats

- Prompts without a fact_key still yield citation and mention rates but no Claim Ledger verdicts.
- The p04 hypothesis (name collision) is W3's guess; the "inactive" claim itself has not been seen by anyone in this project. If the user has the original AI Overview text, store it as the first claim fixture.
- Budget: with 3 repeats, 10 prompts x 2 default engines = 60 calls, about $0.60 search fees; adding opt-in Perplexity adds 30 calls, about $0.075. Token cost is unmeasured (assumption A8); run the dry-run estimator first.
- Unverified: that these wordings are representative of real user queries.
