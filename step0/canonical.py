"""Canonical JSON encoding and strict loading; the implementation lives in geo.canonical."""

from geo.canonical import (  # noqa: F401
    StrictJSONError,
    canonical_bytes,
    canonical_json,
    sha256_hex,
    strict_load_path,
    strict_loads,
)
