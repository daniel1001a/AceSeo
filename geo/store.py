"""Run directory writer (W4 2.1, 2.7, 2.8).

Layout under <root>/<run_id>/:
  manifest.json, inputs/{prompts,facts,sources}.json, raw/<sha256>.<ext>,
  captures.jsonl, page_checks.jsonl, claims.jsonl, decisions.jsonl

The run directory is created with os.mkdir, so an existing run is never
appended to. Records are append-only canonical JSON lines, fsynced. Every byte
written is checked against the secrets passed in (never read from the
environment here).
"""

import os
import tempfile

from .canonical import canonical_bytes, sha256_hex

RECORD_FILES = {"capture": "captures.jsonl", "page_check": "page_checks.jsonl",
                "claim": "claims.jsonl", "decision": "decisions.jsonl"}
RAW_EXTS = ("json", "html", "txt", "xml", "bin")
INPUT_FILES = {"prompts_sha256": "prompts.json", "facts_sha256": "facts.json",
               "sources_sha256": "sources.json"}
# Request header names that must never be stored (W4 2.7, V8). Lowercase.
FORBIDDEN_HEADER_NAMES = (b"authorization", b"x-api-key")


class SecretError(ValueError):
    pass


def input_hashes(inputs):
    """inputs: {"prompts": bytes, "facts": bytes, "sources": bytes} -> manifest hash fields."""
    return {"prompts_sha256": sha256_hex(inputs["prompts"]),
            "facts_sha256": sha256_hex(inputs["facts"]),
            "sources_sha256": sha256_hex(inputs["sources"])}


def _atomic_write(path, data):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class RunWriter:
    def __init__(self, root, manifest, inputs, secrets=()):
        self.secrets = [s.encode("utf-8") for s in secrets if s]
        self.manifest = manifest
        expected = input_hashes(inputs)
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError("manifest %s does not match the input bytes" % key)
        os.makedirs(root, exist_ok=True)
        self.run_dir = os.path.join(root, manifest["run_id"])
        os.mkdir(self.run_dir)  # FileExistsError on a run_id collision (W4 2.5)
        os.mkdir(os.path.join(self.run_dir, "raw"))
        os.mkdir(os.path.join(self.run_dir, "inputs"))
        for key, name in INPUT_FILES.items():
            self._write_file(os.path.join(self.run_dir, "inputs", name), inputs[name[:-5]])
        self.write_manifest()

    def _check(self, data):
        for s in self.secrets:
            if s in data:
                raise SecretError("refusing to write bytes that contain a secret")

    def _write_file(self, path, data):
        self._check(data)
        _atomic_write(path, data)

    def write_manifest(self):
        self._write_file(os.path.join(self.run_dir, "manifest.json"), canonical_bytes(self.manifest) + b"\n")

    def put_raw(self, data, ext, request=False):
        """Store exact bytes. Returns (sha256, relative path). Dedups by hash."""
        if ext not in RAW_EXTS:
            raise ValueError("raw ext must be one of %s" % (RAW_EXTS,))
        if not isinstance(data, bytes):
            raise TypeError("raw data must be bytes")
        self._check(data)
        if request:
            low = data.lower()
            for name in FORBIDDEN_HEADER_NAMES:
                if b'"' + name + b'"' in low:
                    raise SecretError("request body contains a forbidden header name")
        digest = sha256_hex(data)
        rel = "raw/%s.%s" % (digest, ext)
        path = os.path.join(self.run_dir, rel)
        if os.path.exists(path):
            with open(path, "rb") as f:
                if sha256_hex(f.read()) != digest:
                    raise ValueError("existing raw file %s does not match its name" % rel)
            return digest, rel
        _atomic_write(path, data)
        return digest, rel

    def append(self, record):
        name = RECORD_FILES[record["kind"]]
        line = canonical_bytes(record) + b"\n"
        self._check(line)
        with open(os.path.join(self.run_dir, name), "ab") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
