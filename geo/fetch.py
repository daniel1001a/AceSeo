"""Live page fetcher for page checks (the only page-fetch code that opens a socket).

UrllibFetcher follows redirects itself, one hop at a time, so every 3xx hop is
recorded in Response.redirect_chain exactly as FixtureFetcher records it. It
sends one GET per hop with the given user agent and no cookies or credentials.
Bodies are read up to MAX_BODY_BYTES; a longer body is cut there and the
response gets an extra header so the cut is visible in the stored record.
"""

import socket
import urllib.error
import urllib.request
from urllib.parse import urljoin

from .pagechecks import MAX_REDIRECTS, FetchError, Response

MAX_BODY_BYTES = 5 * 1024 * 1024
TRUNCATED_HEADER = "x-geo-evidence-truncated"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises HTTPError with the 3xx response


def _default_open():
    return urllib.request.build_opener(_NoRedirect).open


def _headers(msg):
    return [[n.lower(), v] for n, v in msg.items()]


def _read(fp):
    body = fp.read(MAX_BODY_BYTES + 1)
    return body[:MAX_BODY_BYTES], len(body) > MAX_BODY_BYTES


class UrllibFetcher:
    """fetch(url, user_agent) -> Response, or FetchError("timeout" | "connection")."""

    def __init__(self, timeout_s=30, open_fn=None):
        self.timeout_s = timeout_s
        self.open_fn = open_fn or _default_open()

    def _one(self, url, user_agent):
        if not url.startswith(("http://", "https://")):
            raise FetchError("connection")
        req = urllib.request.Request(url, headers={"User-Agent": user_agent}, method="GET")
        try:
            with self.open_fn(req, timeout=self.timeout_s) as resp:
                body, cut = _read(resp)
                return resp.status, _headers(resp.headers), body, cut
        except urllib.error.HTTPError as e:
            body, cut = _read(e) if e.fp is not None else (b"", False)
            return e.code, _headers(e.headers or {}), body, cut
        except (socket.timeout, TimeoutError):
            raise FetchError("timeout")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise FetchError("timeout")
            raise FetchError("connection")
        except (ConnectionError, OSError):
            raise FetchError("connection")

    def __call__(self, url, user_agent):
        chain = []
        while True:
            status, headers, body, cut = self._one(url, user_agent)
            if cut:
                headers.append([TRUNCATED_HEADER, str(MAX_BODY_BYTES)])
            location = [v for n, v in headers if n == "location"]
            if 300 <= status < 400 and location:
                chain.append({"url": url, "status": status})
                if len(chain) > MAX_REDIRECTS:
                    return Response(url, status, headers, body, chain)
                url = urljoin(url, location[0])
                continue
            return Response(url, status, headers, body, chain)
