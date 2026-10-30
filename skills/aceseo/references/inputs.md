# Writing the inputs

Two JSON files, both strict (no comments, no trailing commas, no duplicate keys). Templates: `examples/minimal/prompts.json` and `examples/minimal/facts.json` in the repository.

## prompts.json

```json
{
  "schema_version": "step0-prompts/v1",
  "source": "where these prompts came from",
  "substitutions": {"BRAND": "Example Co", "DOMAIN": "www.example.com"},
  "prompts": [
    {"prompt_id": "p_01", "type": "B", "lang": "en", "template": "What is {BRAND}?"}
  ]
}
```

- `prompt_id`: `p_` followed by 1 to 40 lowercase letters, digits or `_`. Unique.
- `template`: every `{NAME}` must have a value in `substitutions`, or the tool refuses.
- `type`: one of three, so effects can be told apart later:
  - `U` unbranded discovery: the site is not named ("Which website shows X?"). Measures whether engines find the site on their own.
  - `B` branded verification: the site is named ("Is {BRAND} free to use?"). Produces the claims checked against facts.
  - `F` factual lookup a page on the site could answer ("How many cities does {BRAND} cover?").
- `lang`: a language tag such as `en` or `zh-TW`. The matcher has English patterns for every topic and Chinese patterns for site status only.

Writing fair prompts:

- Ask the way a real user would. Do not tell the engine to cite the site or to search a particular domain.
- Each fact key you care about needs at least one `B` or `F` prompt that invites a sentence about it. A fact no prompt touches gets no verdicts.
- A leading prompt ("Is {BRAND} shut down?") tests a hypothesis; say so when you report its results.
- Freeze the wording before the first live run. The prompt text is hashed into every capture, so changed wording means results are no longer comparable.

## facts.json

What the tool reads at run time:

| Field | Required | Meaning |
|---|---|---|
| `site.name` | yes | The brand name answers use. A sentence must name the site (by this or a host) to be decided. |
| `site.hosts` | yes | Every hostname of the site. A mention of another domain sharing the name becomes `needs_review`. |
| `facts[].key` | yes | Unique. See the table below. |
| `facts[].value` | yes | The true value today. |
| `facts[].prior_values` | no | Old values still quoted: `[{"value": ..., "valid_until": "...", "source": {...}}]`. An answer repeating one is `outdated`, not `contradicted`. |

The collect command refuses a facts file missing any required field (`refused: <path>: ...`, exit 2). It does not apply the full schema in `design/w3-facts-schema.md`; that schema is for generated files with source snapshots.

### Fact keys the matcher decides (version 3)

Built in, for any site:

| Key | Value type | Example sentence it reads |
|---|---|---|
| `site_status` | `"live"`, `"redirect_only"`, `"error"`, `"unreachable"` | "Example Co is no longer operating." "example.com is live." |
| `llms.offer.is_free` | boolean | "Example Co is free to use." "It requires a paid subscription." |
| `jsonld.organization.same_as` | list of URLs, `[]` for none | "Example Co has no social media profiles." "Example Co has a GitHub." |

Any other boolean, integer or enum fact is decided when it has a `match` block
of literal phrases (see README "Declaring facts"):

- boolean: `{"positive": [...], "negative": [...]}`
- integer: `{"unit_terms": [...]}` ("covers 33 US airports" with unit `airports`)
- enum: `{"values": {"value": [phrases], ...}}`
- any of them: optional `"subject_terms": [...]`, words a sentence must contain

Anything else an answer says about the site is either `unsupported` (a known topic such as founding year or app store with no fact) or `needs_review` (hedged, two topics in one sentence, value not readable, or the site not named). Both are listed, never counted against the site.

If the user's important facts have no built-in topic, write a `match` block for them before they spend money; without one the run still gives citation and mention rates, but no verdicts for those facts. This is a facts-file change, not a code change.

### Before the run

- Check every value is true today. A wrong fact turns correct answers into "contradicted".
- Use the hosts exactly as they appear in URLs (`www.example.com` and `example.com` are different).
- Keep the facts file under version control next to the prompts; the run copies both byte for byte into `inputs/`.
