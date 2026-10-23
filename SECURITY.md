# Security policy

## API keys

AceSeo calls paid APIs (OpenAI, Anthropic, and Perplexity if you opt in) only
with `--live`. How it handles keys:

- Keys are read from the environment only (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`), only for engines that pass the
  terms gate, and only when `--live` is given.
- Keys are never written to disk; the run writer refuses any file that
  contains one.
- `export-fixtures` replaces identifier fields in raw responses with
  `"redacted"` before writing test fixtures.
- The Claude Code skill in `skills/aceseo/` never asks for keys in the chat.

What you should do:

- Do not put keys in `facts.json`, `prompts.json`, shell history you share, or
  issues and pull requests.
- Use keys with a spending limit, and always set `--cap-usd`.
- Check run directories before sharing them.

## Reporting a vulnerability

Please do not open a public issue for a security problem, such as a path where
a key could reach disk or output. Use GitHub's "Report a vulnerability"
(private vulnerability reporting) on this repository if it is enabled, or
contact the maintainer, [@daniel1001a](https://github.com/daniel1001a), on
GitHub.

## Supported versions

Only the latest release receives fixes.
