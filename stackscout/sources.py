"""Per-user source lists (milestone 2).

Each user starts from their industry's default sources (config/industries.yaml),
copied into data/users/<id>/my_sources.yaml, and can then toggle, remove or
add sources by pasting a link.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import feedparser
import httpx

from .i18n import UserError
from . import config, storage

DEFAULT_INDUSTRY = "software-ai"
FILE = "my_sources.yaml"
SOURCE_TYPES = ("rss", "hackernews", "github_new_repos", "sitemap")
USER_AGENT = "StackScout/0.1 (feed reader)"
TIMEOUT = 15.0
MAX_BYTES = 3_000_000
COMMON_FEED_PATHS = ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml", "/feed/")
GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.I)


class SourceError(UserError):
    """A user-facing problem with a source (a message key, see i18n)."""


# ---------------------------------------------------------------- list management

def matches_profile(source: dict, profile: dict | None) -> bool:
    """Does an official "stack" source cover something in this profile?"""
    rule = source.get("match") or {}
    if not profile or not rule:
        return False
    keywords = [re.compile(rf"(?<!\w){re.escape(k.casefold())}(?!\w)") for k in rule.get("keywords", [])]
    for s in profile["skills"]:
        name = s["name"].casefold()
        if s["ecosystem"] in rule.get("ecosystems", []) or s["category"] in rule.get("categories", []):
            return True
        if any(k.search(name) for k in keywords):
            return True
    return False


def default_on(source: dict, profile: dict | None) -> bool:
    tier = source.get("tier", "core")
    return tier == "core" or (tier == "stack" and matches_profile(source, profile))


def default_sources(industry: str = DEFAULT_INDUSTRY, profile: dict | None = None) -> list[dict]:
    """The catalog for this user: core always on, official sources on when they match the stack."""
    catalog = [{**copy.deepcopy(s), "enabled": default_on(s, profile)}
               for s in config.industries()[industry]["sources"]]
    return sorted(catalog, key=lambda s: not s["enabled"])  # stable: catalog order within on/off


def _fresh(user_id, industry: str = DEFAULT_INDUSTRY) -> dict:
    return {"industry": industry, "catalog_version": config.catalog_version(),
            "sources": default_sources(industry, storage.load_profile(user_id))}


def load(user_id) -> dict:
    data = storage.read_yaml(user_id, FILE)
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        return _fresh(user_id)
    data["sources"] = [s for s in data["sources"] if isinstance(s, dict) and s.get("type") in SOURCE_TYPES]
    profile = storage.load_profile(user_id)
    if int(data.get("catalog_version") or 1) < config.catalog_version():
        _upgrade(user_id, data, profile)
    # Sources the user never toggled follow the current catalog and profile;
    # a manual choice ("user_set") or a source they added ("custom") is kept.
    catalog = {s["id"]: s for s in config.industries()[data.get("industry", DEFAULT_INDUSTRY)]["sources"]}
    for s in data["sources"]:
        if s.get("user_set") or s.get("tier") == "custom":
            continue
        if s.get("id") in catalog:
            s.update(copy.deepcopy(catalog[s["id"]]))
        s["enabled"] = default_on(s, profile)
    return data


def _upgrade(user_id, data: dict, profile: dict | None) -> None:
    """Append catalog entries the user has never seen, keeping every existing choice."""
    have_ids = {s.get("id") for s in data["sources"]}
    have_urls = {s.get("url") for s in data["sources"] if s.get("url")}
    for s in default_sources(data.get("industry", DEFAULT_INDUSTRY), profile):
        if s["id"] not in have_ids and (not s.get("url") or s["url"] not in have_urls):
            data["sources"].append(s)
    data["catalog_version"] = config.catalog_version()
    save(user_id, data)


def save(user_id, data: dict) -> dict:
    storage.write_yaml(user_id, FILE, data)
    return data


def reset(user_id, industry: str = DEFAULT_INDUSTRY) -> dict:
    return save(user_id, _fresh(user_id, industry))


def enabled(data: dict) -> list[dict]:
    return [s for s in data["sources"] if s.get("enabled", True)]


def _index(data: dict, source_id: str) -> int:
    for i, s in enumerate(data["sources"]):
        if s.get("id") == source_id:
            return i
    raise SourceError("source.not_found")


def set_enabled(user_id, source_id: str, on: bool) -> dict:
    data = load(user_id)
    source = data["sources"][_index(data, source_id)]
    source["enabled"] = bool(on)
    source["user_set"] = True  # a manual choice wins over profile matching from now on
    return save(user_id, data)


def remove(user_id, source_id: str) -> dict:
    data = load(user_id)
    del data["sources"][_index(data, source_id)]
    return save(user_id, data)


def add(user_id, raw_url: str, client: httpx.Client | None = None) -> dict:
    """Discover a feed behind `raw_url` and append it to the user's list."""
    source = discover(raw_url, client)
    data = load(user_id)
    if any(s.get("url") == source["url"] for s in data["sources"]):
        raise SourceError("source.exists")
    source["id"] = _unique_id(data, source["url"])
    source["enabled"] = True
    source["tier"] = "custom"
    data["sources"].append(source)
    save(user_id, data)
    return source


def _unique_id(data: dict, url: str) -> str:
    host = (urlparse(url).hostname or "src").removeprefix("www.").split(".")[0]
    base = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "src"
    candidate = f"{base}-{hashlib.sha1(url.encode()).hexdigest()[:6]}"
    taken = {s.get("id") for s in data["sources"]}
    return candidate if candidate not in taken else f"{candidate}-{len(taken)}"


# ---------------------------------------------------------------- feed discovery

def check_public_host(host: str | None) -> None:
    """Refuse loopback/private addresses: sources are fetched by the server."""
    if not host:
        raise SourceError("source.bad_url")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SourceError("source.unknown_host", host=host) from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise SourceError("source.private_host")


def http_client() -> httpx.Client:
    """Client that re-checks the host on every request, redirects included."""
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [lambda req: check_public_host(req.url.host)]},
    )


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or " " in raw:
        raise SourceError("source.bad_url")
    return raw


class _FeedLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and "alternate" in (a.get("rel") or "").lower() and a.get("href") and (
            "rss" in (a.get("type") or "") or "atom" in (a.get("type") or "")
        ):
            self.hrefs.append(a["href"])


def _get(client: httpx.Client, url: str) -> tuple[bytes, str]:
    resp = client.get(url)
    resp.raise_for_status()
    if len(resp.content) > MAX_BYTES:
        raise SourceError("source.too_large")
    return resp.content, str(resp.url)


def _as_source(content: bytes, url: str) -> dict | None:
    feed = feedparser.parse(content)
    if not feed.get("version"):
        return None
    return {"name": (feed.feed.get("title") or urlparse(url).hostname or url).strip(), "type": "rss", "url": url}


def discover(raw_url: str, client: httpx.Client | None = None) -> dict:
    url = normalize_url(raw_url)
    repo = GITHUB_REPO.match(url)
    if repo:
        owner, name = repo.groups()
        return {"name": f"{owner}/{name} releases", "type": "rss",
                "url": f"https://github.com/{owner}/{name}/releases.atom"}

    if client is None:
        check_public_host(urlparse(url).hostname)
    ctx = contextlib.nullcontext(client) if client else http_client()
    with ctx as c:
        try:
            content, final = _get(c, url)
        except httpx.HTTPError as exc:
            raise SourceError("source.unreachable", error=str(exc)) from exc
        if found := _as_source(content, final):
            return found
        parser = _FeedLinks()
        parser.feed(content.decode("utf-8", "ignore"))
        candidates = [urljoin(final, h) for h in parser.hrefs] + [urljoin(final, p) for p in COMMON_FEED_PATHS]
        for candidate in dict.fromkeys(candidates):
            try:
                content, final_c = _get(c, candidate)
            except (httpx.HTTPError, SourceError):
                continue
            if found := _as_source(content, final_c):
                return found
    raise SourceError("source.no_feed")
