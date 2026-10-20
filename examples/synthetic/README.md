# SYNTHETIC example run

Everything in this directory is SYNTHETIC. No request was sent to any provider
and no key was used. It exists so you can read a complete report and run
directory before you spend money on a live run.

Rebuild it (the output is deterministic, and `tests/test_example.py` checks
that the committed copy matches):

```
rm -rf examples/synthetic/report.md examples/synthetic/runs
python3 examples/make_example.py
```

## What went in

- Page checks: the RECORDED BoardFlight pages in
  `tests/fixtures/boardflight-2026-10-19/`, served with SYNTHETIC status lines
  and headers by `pipeline.FixtureFetcher`. Every blocking check passes.
- Captures: SYNTHETIC OpenAI and Anthropic response bodies (the builders in
  `tests/test_adapters.py`). Every answer says "BoardFlight covers 40 US
  airports." and cites the site.
- Facts: `design/boardflight.facts.sample.json` (a hand-assembled sample),
  which says `llms.coverage.airport_count = 33`.
- 2 prompts x 3 repeats x 2 engines = 12 captures. Perplexity (opt-in, not
  selected) and xai (terms unverified) are skipped by the terms gate.

## What came out

`report.md` recommends "GEO first: fix facts": the R2 rule fired because both
vendors repeated the same contradicted claim in at least the reproduction
threshold of captures. Every number in the report lists its `n` and the
evidence ids it was computed from, and every id resolves to a record in the
run directory.

## The run directory

`runs/run_<UTC start>_<hash>/`, one directory per run, written once:

| Path | What it holds |
|---|---|
| `manifest.json` | Run settings: engines and their terms and price snapshots, excluded engines, skipped slots, repeats, budget cap, key pages, mention terms, threshold values, transport (`fixture`, `live` or `manual`), input hashes. Sealed at the end of the run. |
| `inputs/prompts.json`, `inputs/facts.json`, `inputs/sources.json` | The exact inputs, byte for byte, hashed into the manifest. Claims point at facts in this copy, not at the file on your disk. |
| `raw/<sha256>.<ext>` | Every response body as received (provider JSON, page HTML, robots.txt), named by its SHA-256. Nothing is parsed in place; records point at raw files by hash. |
| `page_checks.jsonl` | One record per check per key page (`http-status`, `noindex`, `robots-ai`, `main-content`, `key-content`), with the redirect chain, result and raw body hash. |
| `captures.jsonl` | One record per attempt per engine, prompt and repeat: status, answer text, citations with the provider field they came from, usage, and the Estimated cost. |
| `claims.jsonl` | One record per claim-bearing sentence: the span in the answer, the fact it was compared with (`fact_ref`), and the verdict (`matched`, `contradicted`, `outdated`, `unsupported`, `needs_review`). |
| `decisions.jsonl` | The rule cascade: each rule's evaluation, the rule that fired, every number with its `n` and evidence ids, the thresholds used, and what was not checked. |

Ids have the form `<kind>_<engine or check>_<16 hex>` and come from a hash of
the record's identity fields, so the same input always gives the same id.

Inspect it with:

```
python3 -m geo.cli ledger examples/synthetic/runs/run_20261019T210001Z_6f7d91
python3 -m geo.cli report examples/synthetic/runs/run_20261019T210001Z_6f7d91
```
