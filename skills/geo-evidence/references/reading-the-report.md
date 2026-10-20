# Reading the report

The report is Markdown with these sections, in order: Recommendation, Rule evaluations, Measurements, Independence groups, Failing blocking checks (only if any), Contradicted or outdated claims (only if any), Excluded and skipped, Not checked. Every id in square brackets resolves to a record in the run directory; `python3 -m geo.cli ledger RUN_DIR` shows captures and claims.

## The rule cascade

Rules run in this order and the first that fires decides. Thresholds are in `geo/number.py`, all provisional, and copied into the decision record.

| Rule | Outcome | Fires when | How to explain it |
|---|---|---|---|
| R1 | `seo_first` | a blocking check (`http-status`, `robots-ai`, `noindex`, `key-content`, `main-content`) failed on a key page | A page AI search cannot fetch or index is unlikely to be cited. Fix the named check first. A hypothesis, not a proven cause of low citation. |
| R0 | `insufficient_evidence` | a key page could not be checked (`page_checks_incomplete`), or fewer than 2 vendors have an engine with at least 6 ok answers, counted only from prompts with at least 3 ok answers (`engines_below_minimum`) | Not a clean result. Say what was short and what run would fill it. |
| R2 | `geo_fix_facts` | the same fact key is contradicted or outdated in at least 2 distinct ok answers | Quote the fact, what the answers said, and the claim ids. The fix is making the true value easy to find and quote on the site. |
| R3 | `geo_content` | in at least 2 vendors, every engine cites the site in under 20% of its ok answers | Engines answer without citing the site. A hypothesis to test with content that answers the prompts. |
| R4 | `no_action` | none of the above | Nothing measured calls for action. Not proof that every answer is right: check `needs_review` claims. |

Results per rule are `fired`, `not_fired`, `unknown` or `not_evaluated` (after an earlier rule fired, `cascade_stopped`). Each carries a reason code and the ids it read.

## Measurements

Each line is `hits/n [Measured] {metric; engine; prompt; evidence: ids; hits: ids; window}`. Metrics:

- `citation_rate`: answers whose citations include a site URL. Only sources the answer cites count, not everything the engine searched.
- `mention_rate`: answers whose text contains a `--mention-term`.
- `contradiction_rate`: among ok answers that produced at least one claim, those with a contradicted or outdated claim. Informational; R2 uses the reproduction count, not this rate.
- `blocking_fail.key_pages`: failed blocking page checks.

A rate below the minimum `n` is reported as insufficient and never used by a rule. Answers from one vendor are one independence group: 6 answers from one vendor are not 6 independent observations.

## Claim verdicts

| Verdict | Meaning |
|---|---|
| `matched` | the answer agrees with the fact |
| `contradicted` | the answer gives a different value |
| `outdated` | the answer gives a value listed in the fact's `prior_values` |
| `unsupported` | a known topic with no fact in the facts file |
| `needs_review` | the matcher could not decide (hedge, two topics, unreadable value, site not named, another domain with the same name) |

Only `contradicted` and `outdated` feed R2. When you explain a contradiction, open the capture with the ledger and quote the sentence, so the user sees exactly what the engine said.

## What to say, and what not to

- Keep the tool's "(draft wording, not yet reviewed against a live run)" marker when the recommendation carries it. The `insufficient_evidence` text has been reviewed and has no marker.
- Give numbers as `hits/n` with the engine, never as a bare percentage.
- Say the results describe API model behaviour, not consumer apps, and list the "Not checked" items that matter for the user's question.
- Do not combine engines into one score, rank the site against competitors, or predict traffic. The tool measures none of these.
- A `--repeats 1` run, or a run with one vendor, can only be a smoke test. Do not draw conclusions from it.
