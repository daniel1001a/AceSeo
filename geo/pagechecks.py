"""Page checks (PLAN 5.2, 5.7.1; W4 3.4; W5-09).

Every check reads one stored raw response and writes one page_check record that
points at it (raw_sha256, raw_path). The fetcher is injected: this module never
opens a socket. A fetcher is a callable fetch(url, user_agent) that returns a
Response or raises FetchError(reason).

HTML is parsed with html.parser only. robots.txt is evaluated with
urllib.robotparser (stdlib semantics; RFC 9309 precedence and wildcards are not
claimed, W5 Q5).

The AI crawler user-agent tokens below come from general knowledge, not from a
vendor document read in this project (W5 assumption 4). Every robots-ai record
says so in detail.crawler_token_status = "unverified".
"""

import re
from collections import namedtuple
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from . import ids, records

Response = namedtuple("Response", "final_url status headers body redirect_chain")
# headers: list of [name, value]; redirect_chain: list of {url, status}, one per 3xx hop.


class FetchError(Exception):
    """reason is a short slug. timeout and connection mean no response bytes exist."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


MAX_REDIRECTS = 5  # W3 fetch limit. More hops: not_checkable (W5 Q7 is still open).

CRAWLERS = (  # (agent_profile, user-agent token). UNVERIFIED tokens, see module docstring.
    ("claude-searchbot", "Claude-SearchBot"),
    ("claudebot", "ClaudeBot"),
    ("google-extended", "Google-Extended"),
    ("gptbot", "GPTBot"),
    ("oai-searchbot", "OAI-SearchBot"),
    ("perplexitybot", "PerplexityBot"),
)
CRAWLER_TOKENS = dict(CRAWLERS)
DEFAULT_PROFILE = "default"
DEFAULT_UA = "geo-evidence/0.1 (page check)"
MIN_PARA_CHARS = 40  # placeholder from PLAN 5.7.1, not a decided threshold

Check = namedtuple("Check", "name version blocking_on_fail agent_profiles description")
REGISTRY = {(c.name, c.version): c for c in (
    Check("http-status", 1, True, (DEFAULT_PROFILE,), "final status 200 after at most 5 redirects"),
    Check("robots-ai", 1, True, (DEFAULT_PROFILE,) + tuple(CRAWLER_TOKENS),
          "robots.txt allows this crawler to fetch the URL"),
    Check("noindex", 1, True, (DEFAULT_PROFILE,), "no noindex in X-Robots-Tag or meta robots"),
    Check("key-content", 1, True, (DEFAULT_PROFILE,), "manifest key_content entry present in raw body"),
    Check("main-content", 1, True, (DEFAULT_PROFILE,),
          "one non-empty h1 and a first p after it with at least min_para_chars characters"),
    Check("canonical", 1, False, (DEFAULT_PROFILE,), "exactly one absolute rel=canonical link"),
    Check("llms-txt", 1, False, (DEFAULT_PROFILE,), "/llms.txt presence, reported not scored"),
)}


def _header(headers, name):
    name = name.lower()
    return [v for n, v in headers if n.lower() == name]


def _content_type(resp):
    values = _header(resp.headers, "content-type")
    return values[0].split(";")[0].strip().lower() if values else ""


def _is_html(resp):
    return _content_type(resp) in ("text/html", "application/xhtml+xml")


def _raw_ext(resp):
    if _is_html(resp):
        return "html"
    if _content_type(resp).startswith("text/"):
        return "txt"
    return "bin"


def _collapse(s):
    return " ".join(s.split())


class _PageParser(HTMLParser):
    """Collects visible text (no script, style, template), meta robots, canonical
    links, h1 texts and the first <p> after the first </h1>."""

    SKIP = ("script", "style", "template")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.meta_robots = []
        self.canonicals = []
        self.h1 = []
        self.first_p_after_h1 = None
        self._skip = 0
        self._in_h1 = None
        self._h1_closed = False
        self._in_p = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "meta" and a.get("name", "").lower() == "robots":
            self.meta_robots.append(a.get("content", ""))
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonicals.append(a.get("href", ""))
        elif tag == "h1":
            self._in_h1 = []
        elif tag == "p" and self._h1_closed and self.first_p_after_h1 is None and self._in_p is None:
            self._in_p = []

    def handle_startendtag(self, tag, attrs):
        if tag not in self.SKIP:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "h1" and self._in_h1 is not None:
            self.h1.append(_collapse("".join(self._in_h1)))
            self._in_h1 = None
            self._h1_closed = True
        elif tag == "p" and self._in_p is not None:
            self.first_p_after_h1 = _collapse("".join(self._in_p))
            self._in_p = None

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._in_h1 is not None:
            self._in_h1.append(data)
        if self._in_p is not None:
            self._in_p.append(data)


def parse_html(body):
    p = _PageParser()
    p.feed(body.decode("utf-8", errors="replace"))
    p.close()
    return p


def _directives(value):
    """'googlebot: noindex, nofollow' -> ['noindex', 'nofollow'] (prefix dropped)."""
    out = []
    for part in value.split(","):
        part = part.strip().lower()
        if ":" in part:
            part = part.split(":", 1)[1].strip()
        if part:
            out.append(part)
    return out


# Each evaluator returns (result, not_checkable_reason, detail).

def eval_http_status(resp):
    detail = {"final_status": resp.status, "hops": len(resp.redirect_chain)}
    return ("pass" if resp.status == 200 else "fail"), None, detail


def eval_noindex(resp, html):
    found = []
    for v in _header(resp.headers, "x-robots-tag"):
        if set(_directives(v)) & {"noindex", "none"}:
            found.append({"source": "header:x-robots-tag", "value": v})
    for v in (html.meta_robots if html else []):
        if set(_directives(v)) & {"noindex", "none"}:
            found.append({"source": "meta:robots", "value": v})
    nosnippet = any("nosnippet" in _directives(v) for v in
                    _header(resp.headers, "x-robots-tag") + (html.meta_robots if html else []))
    detail = {"noindex_sources": found, "nosnippet": nosnippet,
              "meta_robots": list(html.meta_robots) if html else []}
    return ("fail" if found else "pass"), None, detail


def eval_canonical(resp, html):
    hrefs = html.canonicals
    detail = {"canonicals": hrefs, "canonical": None, "same_as_final_url": None}
    if len(hrefs) != 1:
        return "fail", None, detail
    href = urljoin(resp.final_url, hrefs[0].strip())
    try:
        norm = ids.url_norm_v1(href)
    except ids.IdError:
        return "fail", None, detail
    detail["canonical"] = href
    detail["same_as_final_url"] = _path_root(norm) == _path_root(ids.url_norm_v1(resp.final_url))
    return "pass", None, detail


def _path_root(u):
    """Treat an empty path as '/' when comparing (https://h and https://h/ are one page)."""
    parts = urlsplit(u)
    return u if parts.path else u.replace(parts.netloc, parts.netloc + "/", 1)


def eval_key_content(resp, html, entry):
    if html is not None:
        text = _collapse("".join(html.text))
    else:
        text = resp.body.decode("utf-8", errors="replace")
    detail = {"expected": entry.get("expected"), "expected_pattern": entry.get("expected_pattern"),
              "fact_key": entry.get("fact_key"), "match": None}
    if entry.get("expected") is not None:
        ok = _collapse(entry["expected"]) in (text if html is not None else _collapse(text))
        detail["match"] = entry["expected"] if ok else None
    else:
        m = None
        for line in text.splitlines():
            m = re.search(entry["expected_pattern"], line)
            if m:
                break
        ok = m is not None
        detail["match"] = m.group(0) if m else None
    return ("pass" if ok else "fail"), None, detail


def eval_main_content(html, min_para_chars):
    h1 = html.h1
    para = html.first_p_after_h1
    detail = {"h1_count": len(h1), "h1": h1[0] if len(h1) == 1 else None,
              "first_p_chars": len(para) if para is not None else None,
              "first_p_start": para[:80] if para is not None else None,
              "min_para_chars": min_para_chars, "min_para_chars_status": "placeholder"}
    ok = len(h1) == 1 and bool(h1[0]) and para is not None and len(para) >= min_para_chars
    return ("pass" if ok else "fail"), None, detail


def eval_llms_txt(resp):
    ctype = _content_type(resp)
    present = resp.status == 200 and bool(resp.body.strip()) and not _is_html(resp)
    return ("pass" if present else "fail"), None, {"status": resp.status, "content_type": ctype,
                                                   "bytes": len(resp.body)}


def robots_rules(body):
    rp = RobotFileParser()
    rp.parse(body.decode("utf-8", errors="replace").splitlines())
    return rp


def eval_robots(robots_resp, url, token):
    """robots_resp is the robots.txt Response. 4xx means no rules (allow all);
    other non-200 is not_checkable, since the crawler's behavior is unknown."""
    detail = {"robots_url": robots_resp.final_url, "robots_status": robots_resp.status,
              "user_agent_token": token, "crawler_token_status": "unverified" if token != "*" else "n/a",
              "allowed": None, "sitemaps": [], "semantics": "urllib.robotparser"}
    if 400 <= robots_resp.status < 500:
        detail["allowed"] = True
        return "pass", None, detail
    if robots_resp.status != 200:
        return "not_checkable", "robots_status_%d" % robots_resp.status, detail
    rp = robots_rules(robots_resp.body)
    detail["sitemaps"] = list(rp.site_maps() or [])
    detail["allowed"] = bool(rp.can_fetch(token, url))
    return ("pass" if detail["allowed"] else "fail"), None, detail


class PageCheckRunner:
    """Runs the registry checks for manifest.key_pages (or given urls) and writes
    records through a RunWriter. clock() returns a W4 ts."""

    def __init__(self, writer, fetcher, clock, min_para_chars=MIN_PARA_CHARS):
        self.writer = writer
        self.manifest = writer.manifest
        self.fetcher = fetcher
        self.clock = clock
        self.min_para_chars = min_para_chars
        self.written = []

    def _fetch(self, url):
        """-> (resp or None, reason, fetched_at, raw_sha, raw_path)."""
        fetched_at = self.clock()
        try:
            resp = self.fetcher(url, DEFAULT_UA)
        except FetchError as e:
            return None, e.reason, fetched_at, None, None
        sha, path = self.writer.put_raw(resp.body, _raw_ext(resp))
        reason = "too_many_redirects" if len(resp.redirect_chain) > MAX_REDIRECTS else None
        return resp, reason, fetched_at, sha, path

    def _write(self, check_name, url_norm, fetch, outcome, agent_profile=DEFAULT_PROFILE, params=None,
               derived=True):
        resp, _, fetched_at, sha, path = fetch
        result, reason, detail = outcome
        entry = REGISTRY[(check_name, 1)]
        rec = records.page_check(
            self.manifest, check_name=check_name, check_version=1, url_norm=url_norm,
            agent_profile=agent_profile, params=params or {}, fetched_at=fetched_at,
            final_url=resp.final_url if resp else None, http_status=resp.status if resp else None,
            redirect_chain=list(resp.redirect_chain) if resp else [],
            response_headers=[list(h) for h in resp.headers] if resp else [],
            raw_sha256=sha, raw_path=path, derived_from_raw=derived, result=result,
            not_checkable_reason=reason, blocking_on_fail=entry.blocking_on_fail, detail=detail,
            created_at=self.clock())
        self.writer.append(rec)
        self.written.append(rec)
        return rec

    def run(self, urls=None):
        urls = sorted(ids.url_norm_v1(u) for u in (urls if urls is not None else self.manifest["key_pages"]))
        robots = {}
        for url in urls:
            page = self._fetch(url)
            self._page_checks(url, page)
            origin = "%s://%s" % urlsplit(url)[:2]
            if origin not in robots:
                robots[origin] = self._fetch(origin + "/robots.txt")
            self._robots_checks(url, robots[origin])
        return self.written

    def _page_checks(self, url, page):
        resp, reason, _, _, _ = page
        key_entries = [e for e in self.manifest.get("key_content") or [] if ids.url_norm_v1(e["url"]) == url]
        is_llms = urlsplit(url).path == "/llms.txt"
        if reason is not None:  # no usable response: every check is not_checkable, same reason
            names = ["http-status", "noindex"] + (["llms-txt"] if is_llms else ["main-content", "canonical"])
            for name in names:
                self._write(name, url, page, ("not_checkable", reason, {}))
            for e in key_entries:
                self._write("key-content", url, page, ("not_checkable", reason, {}), params=_key_params(e))
            return
        html = parse_html(resp.body) if _is_html(resp) else None
        self._write("http-status", url, page, eval_http_status(resp))
        nc = ("not_checkable", "http_status_%d" % resp.status, {}) if resp.status != 200 else None
        self._write("noindex", url, page, nc or eval_noindex(resp, html))
        if is_llms:
            self._write("llms-txt", url, page, eval_llms_txt(resp))
        elif html is not None or nc:
            self._write("main-content", url, page, nc or eval_main_content(html, self.min_para_chars),
                        params={"min_para_chars": self.min_para_chars})
            self._write("canonical", url, page, nc or eval_canonical(resp, html))
        for e in key_entries:
            self._write("key-content", url, page, nc or eval_key_content(resp, html, e), params=_key_params(e))

    def _robots_checks(self, url, robots_fetch):
        resp, reason, _, _, _ = robots_fetch
        for profile in (DEFAULT_PROFILE,) + tuple(CRAWLER_TOKENS):
            token = "*" if profile == DEFAULT_PROFILE else CRAWLER_TOKENS[profile]
            if reason is not None:
                outcome = ("not_checkable", reason, {"user_agent_token": token})
            else:
                outcome = eval_robots(resp, url, token)
            self._write("robots-ai", url, robots_fetch, outcome, agent_profile=profile)


def _key_params(entry):
    return {k: entry[k] for k in ("expected", "expected_pattern", "fact_key") if entry.get(k) is not None}


class FixtureFetcher:
    """Serves recorded or synthetic responses from a dict, following redirects.

    routes: {url: {"status": int, "headers": [[n, v]], "body": bytes, "location": str?}}
    or {url: FetchError(...)}. Records every call in .calls. No network.
    """

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, user_agent):
        self.calls.append((url, user_agent))
        chain = []
        while True:
            route = self.routes.get(url)
            if route is None:
                return Response(url, 404, [["content-type", "text/plain"]], b"", chain)
            if isinstance(route, FetchError):
                raise route
            if 300 <= route["status"] < 400 and route.get("location"):
                chain.append({"url": url, "status": route["status"]})
                if len(chain) > MAX_REDIRECTS:
                    return Response(url, route["status"], route.get("headers", []), route.get("body", b""), chain)
                url = urljoin(url, route["location"])
                continue
            return Response(url, route["status"], route.get("headers", []), route.get("body", b""), chain)
