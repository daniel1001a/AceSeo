# Changelog

All notable changes are listed here. Releases are on the
[releases page](https://github.com/daniel1001a/AceSeo/releases).

## Unreleased

- v0.2: required site inputs, packaged data for installed collections, site init,
  run comparison, declared fact matchers, and reviewable claim proposals.
- Matcher v5: fix “not live data” status collisions and keep ambiguous same-name
  domains under review, including proposal confirmation context.
- Subscription observations remain manual evidence outside API rates/decisions;
  paid API P0 deferred, FIELD_STATUS and provisional thresholds unchanged.
- CI additionally checks Python 3.13 and wheel installation outside the repo,
  with Ubuntu 24.04 pinned for Python 3.9 availability.

- Packaging: `aceseo` console command (`geo.cli:main`), project metadata
  (authors, keywords, classifiers, URLs), `step0` included in the package,
  version set to `0.1.0` to match the `v0.1.0` tag.
- README: working clone command, install with `pip install -e .`, "Who it's
  for", offline quickstart, sample report excerpt, badges.
- CI on Python 3.9 and 3.12, issue and pull request templates, CONTRIBUTING,
  CODE_OF_CONDUCT, SECURITY.
- `PLAN.md`, `PROGRESS.md` and `READY_FOR_LIVE.md` moved to `docs/`.

## [v0.1.0](https://github.com/daniel1001a/AceSeo/releases/tag/v0.1.0) - 2026-10-20

First public release. Local-first CLI for AI SEO / GEO with official API
capture, claim ledger, and rule-based decisions. Anthropic verified with one
small live run; OpenAI not yet verified; thresholds provisional.
