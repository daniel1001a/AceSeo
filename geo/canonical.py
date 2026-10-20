"""Canonical JSON encoding and strict loading (design/w4-data-model.md, JSONL encoding)."""

import hashlib
import json


class StrictJSONError(ValueError):
    pass


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def canonical_bytes(obj):
    return canonical_json(obj).encode("utf-8")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _reject_float(text):
    raise StrictJSONError("float literal not allowed: %s" % text)


def _reject_constant(text):
    raise StrictJSONError("constant not allowed: %s" % text)


def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise StrictJSONError("duplicate key: %s" % key)
        out[key] = value
    return out


def strict_loads(text):
    return json.loads(
        text,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
        object_pairs_hook=_no_duplicate_keys,
    )


def strict_load_path(path):
    with open(path, encoding="utf-8") as f:
        return strict_loads(f.read())
