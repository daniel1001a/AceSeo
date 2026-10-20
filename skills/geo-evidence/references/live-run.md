# Planning and running a live run

## Engines and keys

The engine list, models and terms status live in `step0/data/engines.json`; read it rather than assuming. An engine is called only if its terms status is `verified-allowed`, it has an adapter, and (for opt-in engines) the user passed `--opt-in <engine>`. The plan prints which engines will be called and the environment variable each one needs:

| Engine | Variable | Called |
|---|---|---|
| openai | `OPENAI_API_KEY` | by default |
| anthropic | `ANTHROPIC_API_KEY` | by default |
| perplexity | `PERPLEXITY_API_KEY` | only with `--opt-in perplexity` |

The user sets keys in their own shell (`export OPENAI_API_KEY=...`). Never put a key in a command you run, a file, or the chat. The tool refuses to write any file containing a key.

## Choosing repeats

- Rates need at least 3 ok answers per prompt per engine (`N_MIN_REPEATS`), and the evidence gate needs an engine with at least 6 such ok answers in each of at least 2 vendors. With `--repeats 1` the outcome can only be `insufficient_evidence`; use it only as a cheap smoke test that keys and parsing work.
- `--repeats 3` is the smallest run that can reach a decision. Failed attempts reduce the ok count, so a run with many failures can still end as insufficient.

## Choosing the cap

The plan prints the Estimated cost per call and in total, plus an upper bound that assumes more searches per call. All of it is `Estimated`: 22000 input tokens, 800 output tokens and two searches per call are planning assumptions (the rounded-up means of the first live Anthropic run; other vendors not yet measured), priced with the `Published` prices in `step0/data/prices.json` (each with source URL and retrieval date).

How `--cap-usd` works:

- Before sending, the run refuses if the expected cost of all first attempts exceeds the cap. Nothing is sent.
- While running, each attempt (including retries, up to `--max-attempts`, default 2) adds its expected per-call estimate to a running total. A request that would push the total past the cap is not sent and is recorded as skipped with `budget_cap`.
- The upper bound is not enforced. Suggest a cap at or above the upper bound if the user wants the run to finish.

Tell the user the provider bill is the real cost and to compare it after the first run.

## Refusals (exit code 2, nothing or nothing more sent)

| Message starts with | Meaning | Fix |
|---|---|---|
| `refused: <facts path>:` | facts file missing a required field | fix the field named |
| `refused: bad prompt_id` / `duplicate prompt_id` / `unfilled placeholder` | prompts file problem | fix the prompt named |
| `refused: no API key for` | a selected engine's variable is not set | user exports it, or drop the opt-in |
| `refused: Estimated first attempts ... exceed the cap` | cap below the plan | raise the cap or cut prompts or repeats |
| `refused: <path> exists` | the report file or run directory is taken | pick a new `--report-out` path |

## Skips and failures inside a run

Recorded in `captures.jsonl` and listed under "Excluded and skipped" in the report:

- `terms_gate`: the engine is not allowed or not opted in. Expected; not an error.
- `budget_cap`: the cap stopped this request.
- `user_abort`: the user pressed Ctrl-C; the run is still written and sealed.
- `quota_exhausted`: the engine's account has no credit left (OpenAI answers HTTP 429 with error type `insufficient_quota`). The first such attempt is recorded as a failed capture with that `error_class`, is not retried, and the engine's remaining requests are skipped. Tell the user to add credit with the provider; retrying will not help.
- A capture with status `failed` has an `error_class`: `timeout`, `connection`, `http_error`, `rate_limited`, `quota_exhausted`, `parse_error`, `empty_answer`, `incomplete`, or `tool_error`. Failed captures never count as ok. Many `parse_error`s after a provider change mean the adapter needs updating; tell the user rather than retrying.

Rerunning is a new run with a new directory and a new cost. Ask before doing it.

## After a live run

- `python3 -m geo.cli ledger RUN_DIR` lists every capture and claim with ids.
- `python3 -m geo.cli export-fixtures RUN_DIR` copies the raw provider bodies into `tests/fixtures/live/` with identifier fields redacted, so the parsers can be regression tested. Review the files before committing them anywhere.
