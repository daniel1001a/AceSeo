"""Step 2 tests: page checks (W5-09) and validator V25 on page_check records.

Fixture labels:
  RECORDED  tests/fixtures/boardflight-2026-10-19/{home.html, airport_jfk.html, llms.txt}
            (bodies only; status 200 and content-type headers around them are SYNTHETIC)
  SYNTHETIC robots.txt R-A, noindex H1 to H4, HTML-1/HTML-2, redirect chains, timeout.
  R-B (real robots.txt) is deferred: it was not recorded in Step 0.
"""

import json
import os
import tempfile
import unittest

from geo import ids, pagechecks
from geo.canonical import canonical_bytes, sha256_hex
from geo.pagechecks import FetchError, FixtureFetcher, PageCheckRunner
from geo.validate import codes, validate_run

from tests import geo_fixtures as fx

REC_DIR = os.path.join(fx.FIXTURES, "boardflight-2026-10-19")
HTML = [["content-type", "text/html; charset=utf-8"]]
TXT = [["content-type", "text/plain; charset=utf-8"]]
WWW = "https://www.boardflight.com"
JFK = WWW + "/airport/jfk"

R_A = (b"User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow: /api/\nDisallow: /?f=\n\n"
       b"Sitemap: https://www.boardflight.com/sitemap.xml\n")
HTML_1 = b"<html><body><h1>JFK</h1><p>Plan for John F. Kennedy International security lines.</p></body></html>"
HTML_2 = b'<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
JFK_KEY = {"url": JFK, "expected": "John F. Kennedy International", "fact_key": None}
LLMS_KEY = {"url": WWW + "/llms.txt", "expected_pattern": r"Covers [0-9]+ US airports", "fact_key": None}


def recorded(name):
    with open(os.path.join(REC_DIR, name), "rb") as f:
        return f.read()


def ok(body, headers=HTML):
    return {"status": 200, "headers": headers, "body": body}


def bf_routes(robots=R_A, **over):
    routes = {
        WWW + "/": ok(recorded("home.html")),
        JFK: ok(recorded("airport_jfk.html")),
        WWW + "/llms.txt": ok(recorded("llms.txt"), TXT),
        WWW + "/robots.txt": ok(robots, TXT),
    }
    routes.update(over)
    return routes


def pick(recs, name, url=JFK, profile="default"):
    found = [r for r in recs if r["check_name"] == name and r["url_norm"] == url and r["agent_profile"] == profile]
    assert len(found) == 1, (name, url, profile, len(found))
    return found[0]


class PageCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.n = 0

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, routes, urls=None, key_content=()):
        self.n += 1
        self.run_ = fx.Run(os.path.join(self._tmp.name, str(self.n)), key_content=key_content)
        self.fetcher = FixtureFetcher(routes)
        recs = PageCheckRunner(self.run_.writer, self.fetcher, self.run_.tick).run(urls)
        return recs

    def assertValid(self):
        self.assertEqual(validate_run(self.run_.dir, secrets=(fx.SECRET,)), [])


class RecordedFixtures(PageCase):
    def test_fixture_hashes_match_provenance(self):
        with open(os.path.join(REC_DIR, "FIXTURES.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["label"], "RECORDED")
        for item in meta["files"]:
            body = recorded(item["file"])
            self.assertEqual((len(body), sha256_hex(body)), (item["bytes"], item["sha256"]))

    def test_three_key_pages_pass(self):
        recs = self.check(bf_routes(), key_content=[JFK_KEY, LLMS_KEY])
        self.assertValid()
        for url in fx.KEY_PAGES:
            self.assertEqual(pick(recs, "http-status", url)["result"], "pass")
            self.assertEqual(pick(recs, "noindex", url)["result"], "pass")
            self.assertEqual(pick(recs, "http-status", url)["url_role"], "key")
        for url in fx.KEY_PAGES[:2]:
            self.assertEqual(pick(recs, "main-content", url)["result"], "pass")
            self.assertEqual(pick(recs, "canonical", url)["result"], "pass")
        home = pick(recs, "main-content", WWW + "/")["detail"]
        self.assertEqual(home["h1"], "Know exactly when to be at the airport")
        self.assertTrue(home["first_p_start"].startswith("Every airport runs differently"))
        jfk = pick(recs, "main-content")["detail"]
        self.assertEqual(jfk["h1"], "How early should you arrive at John F. Kennedy International?")
        self.assertTrue(jfk["first_p_start"].startswith("For a typical domestic flight out of JFK"))
        self.assertEqual(jfk["min_para_chars_status"], "placeholder")
        self.assertEqual(pick(recs, "key-content")["result"], "pass")
        llms_key = pick(recs, "key-content", WWW + "/llms.txt")
        self.assertEqual((llms_key["result"], llms_key["detail"]["match"]), ("pass", "Covers 33 US airports"))
        self.assertEqual(pick(recs, "llms-txt", WWW + "/llms.txt")["result"], "pass")
        self.assertEqual(pick(recs, "noindex")["detail"]["meta_robots"], ["index, follow"])
        self.assertTrue(pick(recs, "canonical", WWW + "/")["detail"]["same_as_final_url"])

    def test_each_result_links_to_its_raw_response(self):
        recs = self.check(bf_routes(), key_content=[JFK_KEY])
        for r in recs:
            with open(os.path.join(self.run_.dir, r["raw_path"]), "rb") as f:
                self.assertEqual(sha256_hex(f.read()), r["raw_sha256"])
        self.assertEqual(pick(recs, "key-content")["raw_sha256"], sha256_hex(recorded("airport_jfk.html")))
        self.assertEqual(pick(recs, "robots-ai", profile="gptbot")["raw_sha256"], sha256_hex(R_A))
        self.assertEqual(pick(recs, "llms-txt", WWW + "/llms.txt")["raw_path"],
                         "raw/%s.txt" % sha256_hex(recorded("llms.txt")))

    def test_reproducible(self):
        a = [canonical_bytes(r) for r in self.check(bf_routes(), key_content=[JFK_KEY])]
        b = [canonical_bytes(r) for r in self.check(bf_routes(), key_content=[JFK_KEY])]
        self.assertEqual(a, b)

    def test_robots_fetched_once_per_origin(self):
        self.check(bf_routes())
        self.assertEqual([u for u, _ in self.fetcher.calls].count(WWW + "/robots.txt"), 1)
        self.assertTrue(all(ua == pagechecks.DEFAULT_UA for _, ua in self.fetcher.calls))


class W509Robots(PageCase):
    def test_r_a_per_crawler(self):
        recs = self.check(bf_routes(), urls=[JFK, WWW + "/api/x"], key_content=[])
        self.assertValid()
        self.assertEqual(pick(recs, "robots-ai", profile="gptbot")["result"], "fail")
        for profile, token in pagechecks.CRAWLERS:
            r = pick(recs, "robots-ai", profile=profile)
            self.assertEqual(r["detail"]["crawler_token_status"], "unverified")
            if profile != "gptbot":
                self.assertEqual(r["result"], "pass", profile)  # the * group must not leak into GPTBot
            self.assertEqual(pick(recs, "robots-ai", WWW + "/api/x", profile)["result"], "fail", profile)
        self.assertEqual(pick(recs, "robots-ai")["result"], "pass")
        self.assertEqual(pick(recs, "robots-ai", WWW + "/api/x")["result"], "fail")
        self.assertEqual(pick(recs, "robots-ai")["detail"]["sitemaps"], ["https://www.boardflight.com/sitemap.xml"])
        self.assertIs(pick(recs, "robots-ai")["derived_from_raw"], True)
        self.assertIs(pick(recs, "robots-ai")["blocking_on_fail"], True)

    def test_query_disallow(self):
        recs = self.check(bf_routes(), urls=[WWW + "/?f=1"])
        self.assertEqual(pick(recs, "robots-ai", WWW + "/?f=1")["result"], "fail")

    def test_missing_robots_allows(self):
        recs = self.check(bf_routes(**{WWW + "/robots.txt": {"status": 404, "headers": TXT, "body": b""}}))
        self.assertEqual({r["result"] for r in recs if r["check_name"] == "robots-ai"}, {"pass"})

    def test_robots_server_error_not_checkable(self):
        recs = self.check(bf_routes(**{WWW + "/robots.txt": {"status": 503, "headers": TXT, "body": b"x"}}))
        r = pick(recs, "robots-ai", profile="gptbot")
        self.assertEqual((r["result"], r["not_checkable_reason"]), ("not_checkable", "robots_status_503"))
        self.assertValid()

    @unittest.skip("W5-09 R-B: real robots.txt was not recorded in Step 0; expectation must be written after recording")
    def test_r_b_recorded_robots(self):
        pass


class W509Noindex(PageCase):
    def _noindex(self, body, headers=HTML):
        return pick(self.check({JFK: ok(body, headers)}, urls=[JFK]), "noindex")

    def test_h1_header(self):
        r = self._noindex(HTML_1, HTML + [["X-Robots-Tag", "noindex"]])
        self.assertEqual(r["result"], "fail")
        self.assertEqual(r["detail"]["noindex_sources"][0]["source"], "header:x-robots-tag")

    def test_h2_meta_case_insensitive(self):
        r = self._noindex(b'<html><head><meta name="robots" content="NoIndex, follow"></head><body></body></html>')
        self.assertEqual(r["result"], "fail")

    def test_h3_index_follow(self):
        self.assertEqual(self._noindex(b'<meta name="robots" content="index, follow"><p>x</p>')["result"], "pass")

    def test_h4_body_text_is_not_a_directive(self):
        self.assertEqual(self._noindex(b"<p>add noindex to private pages</p>")["result"], "pass")

    def test_agent_prefixed_header_and_nosnippet(self):
        r = self._noindex(HTML_1, HTML + [["x-robots-tag", "googlebot: noindex"], ["X-Robots-Tag", "nosnippet"]])
        self.assertEqual(r["result"], "fail")
        self.assertIs(r["detail"]["nosnippet"], True)


class W509Redirect(PageCase):
    def test_one_hop(self):
        routes = {"https://boardflight.com/": {"status": 308, "headers": [], "location": WWW + "/"},
                  WWW + "/": ok(recorded("home.html"))}
        r = pick(self.check(routes, urls=["https://boardflight.com/"]), "http-status", "https://boardflight.com/")
        self.assertEqual(r["redirect_chain"], [{"url": "https://boardflight.com/", "status": 308}])
        self.assertEqual((r["final_url"], r["http_status"], r["result"]), (WWW + "/", 200, "pass"))
        self.assertEqual(r["url_role"], "other")
        self.assertValid()

    def test_five_hops(self):
        routes = {"https://h.example/%d" % i: {"status": 301, "headers": [], "location": "/%d" % (i + 1)}
                  for i in range(5)}
        routes["https://h.example/5"] = ok(HTML_1)
        r = pick(self.check(routes, urls=["https://h.example/0"]), "http-status", "https://h.example/0")
        self.assertEqual((len(r["redirect_chain"]), r["result"]), (5, "pass"))

    def test_more_than_five_hops_not_checkable(self):
        routes = {"https://h.example/%d" % i: {"status": 301, "headers": [], "location": "/%d" % (i + 1)}
                  for i in range(7)}
        recs = self.check(routes, urls=["https://h.example/0"])
        r = pick(recs, "http-status", "https://h.example/0")
        self.assertEqual((r["result"], r["not_checkable_reason"]), ("not_checkable", "too_many_redirects"))
        self.assertValid()

    def test_non_200_fails_and_dependents_not_checkable(self):
        recs = self.check({JFK: {"status": 500, "headers": HTML, "body": b"err"}}, urls=[JFK], key_content=[JFK_KEY])
        self.assertEqual(pick(recs, "http-status")["result"], "fail")
        for name in ("noindex", "main-content", "canonical", "key-content"):
            r = pick(recs, name)
            self.assertEqual((r["result"], r["not_checkable_reason"]), ("not_checkable", "http_status_500"))
        self.assertValid()


class W509Content(PageCase):
    def test_html_1_and_html_2(self):
        recs = self.check({JFK: ok(HTML_1)}, urls=[JFK], key_content=[JFK_KEY])
        self.assertEqual(pick(recs, "key-content")["result"], "pass")
        recs = self.check({JFK: ok(HTML_2)}, urls=[JFK], key_content=[JFK_KEY])
        self.assertEqual(pick(recs, "key-content")["result"], "fail")
        self.assertEqual(pick(recs, "main-content")["result"], "fail")

    def test_text_inside_script_does_not_count(self):
        body = b"<h1>x</h1><script>var s='John F. Kennedy International';</script>"
        recs = self.check({JFK: ok(body)}, urls=[JFK], key_content=[JFK_KEY])
        self.assertEqual(pick(recs, "key-content")["result"], "fail")

    def test_main_content_short_paragraph_and_two_h1(self):
        recs = self.check({JFK: ok(b"<h1>a</h1><p>short</p>")}, urls=[JFK])
        self.assertEqual(pick(recs, "main-content")["result"], "fail")
        recs = self.check({JFK: ok(b"<h1>a</h1><h1>b</h1><p>%s</p>" % (b"x" * 50))}, urls=[JFK])
        self.assertEqual(pick(recs, "main-content")["detail"]["h1_count"], 2)
        self.assertEqual(pick(recs, "main-content")["result"], "fail")

    def test_canonical_missing_or_double(self):
        self.assertEqual(pick(self.check({JFK: ok(HTML_1)}, urls=[JFK]), "canonical")["result"], "fail")
        two = b'<link rel="canonical" href="/a"><link rel="canonical" href="/b">'
        r = pick(self.check({JFK: ok(two)}, urls=[JFK]), "canonical")
        self.assertEqual(r["result"], "fail")
        self.assertIs(r["blocking_on_fail"], False)


class W509FetchFailure(PageCase):
    def test_timeout(self):
        recs = self.check(bf_routes(**{JFK: FetchError("timeout")}), urls=[JFK], key_content=[JFK_KEY])
        page = [r for r in recs if r["check_name"] != "robots-ai"]
        self.assertEqual(len(page), 5)
        for r in page:
            self.assertEqual(r["result"], "not_checkable")
            self.assertEqual(r["not_checkable_reason"], "timeout")
            self.assertIsNone(r["raw_sha256"])
            self.assertIsNone(r["final_url"])
        self.assertEqual(pick(recs, "robots-ai")["result"], "pass")  # robots fetch is independent
        self.assertValid()

    def test_robots_connection_error(self):
        recs = self.check(bf_routes(**{WWW + "/robots.txt": FetchError("connection")}), urls=[JFK])
        self.assertEqual({(r["result"], r["not_checkable_reason"]) for r in recs if r["check_name"] == "robots-ai"},
                         {("not_checkable", "connection")})
        self.assertValid()


class V25PageCheckValidator(PageCase):
    def edit(self, mutate):
        recs = self.check(bf_routes(), urls=[JFK])
        out = []
        for r in recs:
            if r["check_name"] == "noindex":
                r = dict(r)
                mutate(r)
                identity = ids.record_identity(r)
                r.update(identity_sha256=ids.identity_sha256(identity), id=ids.make_id(identity, r["check_name"]),
                         series_key=ids.series_key(identity))
            out.append(r)
        self.run_.rewrite_records("page_checks.jsonl", out)
        return codes(validate_run(self.run_.dir))

    def test_clean(self):
        self.assertEqual(self.edit(lambda r: None), [])

    def test_unknown_check(self):
        self.assertEqual(self.edit(lambda r: r.update(check_version=9)), ["E_PAGE_CHECK"])

    def test_blocking_differs_from_registry(self):
        self.assertEqual(self.edit(lambda r: r.update(blocking_on_fail=False)), ["E_PAGE_CHECK"])

    def test_agent_not_in_registry(self):
        self.assertEqual(self.edit(lambda r: r.update(agent_profile="gptbot")), ["E_PAGE_CHECK"])

    def test_url_role(self):
        self.assertEqual(self.edit(lambda r: r.update(url_role="other")), ["E_PAGE_CHECK"])

    def test_null_raw_needs_timeout(self):
        self.assertEqual(self.edit(lambda r: r.update(raw_sha256=None, raw_path=None)), ["E_STATUS"])

    def test_reason_iff_not_checkable(self):
        self.assertEqual(self.edit(lambda r: r.update(not_checkable_reason="x")), ["E_SCHEMA"])

    def test_raw_tamper(self):
        recs = self.check(bf_routes(), urls=[JFK])
        path = os.path.join(self.run_.dir, pick(recs, "noindex")["raw_path"])
        with open(path, "r+b") as f:
            b = f.read(1)
            f.seek(0)
            f.write(bytes([b[0] ^ 1]))
        self.assertEqual(set(codes(validate_run(self.run_.dir))), {"E_RAW_HASH"})


if __name__ == "__main__":
    unittest.main()
