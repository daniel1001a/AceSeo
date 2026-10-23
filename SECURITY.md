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

Please report vulnerabilities privately through GitHub private vulnerability
reporting: open the repository's **Security** tab and choose **Report a
vulnerability**. Do not open a public issue, pull request or discussion with
details of a vulnerability, such as a path where a key could reach disk or
output.

## Supported versions

Only the latest release receives fixes.
