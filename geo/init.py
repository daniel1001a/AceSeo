"""aceseo init URL: draft facts.json and prompts.json from a site's public pages.

It GETs the home page and /llms.txt (two requests, no cookies or credentials)
and drafts only what code can read off them:

  site.name   JSON-LD Organization or WebSite name, else og:site_name, else the
              <title> up to its first separator, else the hostname
  site.hosts  the final hostname and its www / bare twin
  site_status from the home page's HTTP status and redirect count (site_status.v1)
  jsonld.organization.same_as   when the JSON-LD Organization lists sameAs

Facts a person must state (is the product free, how many plans, ...) are not
guessed; the llms.txt summary line is printed so the user can write them with
a match block. Existing files are never overwritten.
"""

import json
import os
import re
from urllib.parse import urljoin, urlsplit

from . import facts as facts_mod
from .pagechecks import DEFAULT_UA, FetchError

PROMPT_TEMPLATES = (
    "What is {BRAND}?",
    "Is {DOMAIN} a legitimate and active website?",
    "Is {BRAND} free to use?",
    "What does {BRAND} do, and who is it for?",
    "What are the official website and social profiles of {BRAND}?",
    "What are good alternatives to {BRAND}?",
)
TITLE_SEPARATORS = (" | ", " - ", ": ", " \u2013 ", " \u2014 ")
_META_RE = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR_RE = re.compile(r'([a-zA-Z:-]+)\s*=\s*"([^"]*)"')
_TITLE_RE = re.compile(r"<title[^>]*>([^<]*)</title>", re.I)


class InitError(ValueError):
    pass


def _types(node):
    t = node.get("@type")
    return set(t) if isinstance(t, list) else {t}


def _jsonld_nodes(html_text):
    for block in facts_mod.jsonld_blocks(html_text):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        for node in stack:
            if not isinstance(node, dict):
                continue
            yield node
            for sub in node.get("@graph") or []:
                if isinstance(sub, dict):
                    yield sub


def _og_site_name(html_text):
    for tag in _META_RE.findall(html_text):
        attrs = dict((k.lower(), v) for k, v in _ATTR_RE.findall(tag))
        if attrs.get("property") == "og:site_name" and attrs.get("content", "").strip():
            return attrs["content"].strip()
    return None


def _title_name(html_text):
    m = _TITLE_RE.search(html_text)
    if not m or not m.group(1).strip():
        return None
    title = m.group(1).strip()
    cut = min((title.find(s) for s in TITLE_SEPARATORS if s in title), default=-1)
    return title[:cut].strip() if cut > 0 else title


def read_home(html_text, host):
    """-> (name, name_source, same_as list or None)."""
    nodes = list(_jsonld_nodes(html_text))
    org = next((n for n in nodes if "Organization" in _types(n)), None)
    same_as = None
    if org is not None and isinstance(org.get("sameAs"), list):
        same_as = [u for u in org["sameAs"] if isinstance(u, str) and u.startswith(("http://", "https://"))] or None
    for node, label in ((org, "JSON-LD Organization name"),
                        (next((n for n in nodes if "WebSite" in _types(n)), None), "JSON-LD WebSite name")):
        if node is not None and isinstance(node.get("name"), str) and node["name"].strip():
            return node["name"].strip(), label, same_as
    og = _og_site_name(html_text)
    if og:
        return og, "og:site_name", same_as
    title = _title_name(html_text)
    if title:
        return title, "<title>", same_as
    return host, "hostname", same_as


def _hosts(host):
    twin = host[4:] if host.startswith("www.") else "www." + host
    return [host, twin]


def _summary_line(text):
    return next((ln[1:].strip() for ln in text.split("\n") if ln.startswith(">") and ln[1:].strip()), None)


def draft(url, fetcher):
    """-> (facts doc, prompts doc, notes list). Raises InitError."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InitError("URL must be an absolute http(s) URL, e.g. https://www.example.com")
    try:
        home = fetcher(url, DEFAULT_UA)
    except FetchError as e:
        raise InitError("could not fetch %s: %s" % (url, e))
    status = facts_mod.site_status_of(home.status, len(home.redirect_chain))
    if status is None:
        raise InitError("%s answered with status %d" % (url, home.status))
    final = urlsplit(home.final_url)
    host = final.hostname
    origin = "%s://%s" % (final.scheme, final.netloc)
    html_text = home.body.decode("utf-8", errors="replace")
    name, name_source, same_as = read_home(html_text, host)

    notes = ["site.name %r was read from the %s; correct it if the brand is written differently" % (name, name_source),
             "site_status is %r (HTTP %d after %d redirect(s))" % (status, home.status, len(home.redirect_chain))]
    facts = [{"key": "site_status", "value": status, "value_type": "enum"}]
    if same_as:
        facts.insert(0, {"key": "jsonld.organization.same_as", "value": same_as, "value_type": "string_list"})
        notes.append("jsonld.organization.same_as lists %d profile URL(s) from the home page JSON-LD" % len(same_as))
    else:
        notes.append("no JSON-LD Organization sameAs on the home page; no same_as fact drafted")

    llms_url = urljoin(origin + "/", "llms.txt")
    try:
        llms = fetcher(llms_url, DEFAULT_UA)
        if 200 <= llms.status <= 299:
            line = _summary_line(llms.body.decode("utf-8", errors="replace"))
            notes.append("llms.txt found%s" % (": %s" % line if line else " (no '>' summary line)"))
            if line:
                notes.append("state the facts in that summary yourself (e.g. a boolean llms.offer.is_free), "
                             "with a match block; see README 'Declaring facts'")
        else:
            notes.append("no llms.txt (HTTP %d at %s)" % (llms.status, llms_url))
    except FetchError as e:
        notes.append("no llms.txt (%s at %s)" % (e, llms_url))

    facts_doc = {
        "schema_version": "1.0.0",
        "site": {"name": name, "canonical_origin": origin, "hosts": _hosts(host),
                 "note": "drafted by aceseo init from %s; review every fact before a live run" % url},
        "facts": facts,
    }
    problems = facts_mod.runtime_problems(facts_doc)
    if problems:
        raise InitError("the drafted facts file is not usable: %s" % "; ".join(problems))
    prompts_doc = {
        "schema_version": "step0-prompts/v1",
        "source": "drafted by aceseo init: generic questions, replace or extend with your own",
        "substitutions": {"BRAND": name, "DOMAIN": host},
        "prompts": [{"prompt_id": "p_%02d" % i, "type": "B", "lang": "en", "template": t}
                    for i, t in enumerate(PROMPT_TEMPLATES, 1)],
    }
    return facts_doc, prompts_doc, notes


def write_drafts(out_dir, facts_doc, prompts_doc):
    """Write facts.json and prompts.json into out_dir when missing. -> [(path, written)]."""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for name, doc in (("facts.json", facts_doc), ("prompts.json", prompts_doc)):
        path = os.path.join(out_dir, name)
        try:
            with open(path, "x", encoding="utf-8") as f:
                f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            out.append((path, True))
        except FileExistsError:
            out.append((path, False))
    return out
