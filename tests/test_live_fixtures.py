"""Regression: replay recorded real provider responses (tests/fixtures/live).

Skipped until `geo export-fixtures` has written index.json there. Each body
must still parse to the outcome recorded when it was exported.
"""

import json
import os
import unittest

from geo.adapters import ADAPTERS
from geo.canonical import strict_load_path
from geo.fixtures_export import expected
from tests import geo_fixtures as fx

LIVE = os.path.join(fx.FIXTURES, "live")
INDEX = os.path.join(LIVE, "index.json")


@unittest.skipUnless(os.path.exists(INDEX), "no recorded live responses yet (tests/fixtures/live/index.json)")
class LiveReplay(unittest.TestCase):
    def test_every_fixture_parses_as_recorded(self):
        doc = strict_load_path(INDEX)
        self.assertTrue(doc["fixtures"])
        for e in doc["fixtures"]:
            with self.subTest(file=e["file"]):
                with open(os.path.join(LIVE, e["file"]), "rb") as f:
                    body = f.read()
                self.assertEqual(expected(ADAPTERS[e["engine"]].parse(e["http_status"], body)), e["expected"])

    def test_no_identifier_left(self):
        doc = strict_load_path(INDEX)
        for e in doc["fixtures"]:
            with open(os.path.join(LIVE, e["file"]), encoding="utf-8") as f:
                body = json.load(f)  # real bodies may hold floats (e.g. temperature)
            stack = [body]
            while stack:
                x = stack.pop()
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k in doc["redacted_keys"] and v is not None:
                            self.assertEqual(v, "redacted", e["file"])
                        stack.append(v)
                elif isinstance(x, list):
                    stack.extend(x)


if __name__ == "__main__":
    unittest.main()
