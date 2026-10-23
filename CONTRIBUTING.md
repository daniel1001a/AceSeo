# Contributing

Thanks for helping. AceSeo is a small, standard-library-only Python CLI, and
contributions should keep it that way.

## Set up

```
git clone https://github.com/daniel1001a/AceSeo.git
cd AceSeo
pip install -e .
python3 -m unittest discover -s tests -q
```

The tests run offline and need no API keys.

## Rules for changes

- Python 3.9 or newer, standard library only. No new dependencies.
- Tests must not call a live API. Use the fixtures in `tests/fixtures/`.
  `python3 -m geo.cli export-fixtures RUN_DIR` turns a live run into redacted
  fixtures.
- Every number the tool prints must keep its `n` and evidence ids.
- Thresholds live in `geo/number.py` and are labelled provisional; say why if
  you change one.
- An engine is only called if its API terms were read and recorded in
  `step0/data/engines.json`. Do not add scraping of consumer apps.
- Never commit API keys or run directories (`runs/` is ignored by git).

Design background is in `design/`, `research/` and `docs/`.

## Pull requests

Describe what changed and why, run the tests, and fill in the checklist in the
pull request template. Report security problems privately through GitHub private vulnerability
reporting, not in a public issue; see [SECURITY.md](SECURITY.md).
