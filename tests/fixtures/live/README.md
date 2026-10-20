# Recorded live responses

Empty until a real run is exported. To fill it:

    python3 -m geo.cli collect --live ...            # see READY_FOR_LIVE.md
    python3 -m geo.cli export-fixtures runs/<run_id> # writes here

`export-fixtures` replaces identifier fields (`id`, `user`, `safety_identifier`,
`prompt_cache_key`, `metadata`, `previous_response_id`) with `"redacted"` and
refuses if that changes the parse. Read every file before committing.
`tests/test_live_fixtures.py` replays them through the adapters and skips while
`index.json` is absent.
