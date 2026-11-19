"""Weekly collection (milestone 3): RSS/Atom, Hacker News, new GitHub repos.

Every item has the same shape:
    {id, source_id, source, title, url, summary, published (ISO 8601)}
`id` is derived from the canonical URL, so the same link coming from two
sources is collected once.
"""

from __future__ import annotations

import calendar
import hashlib
import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx

from .sources import USER_AGENT

log = logging.getLogger(__name__)

WINDOW_DAYS = 7
PER_SOURCE_LIMIT = 15
SEEN_KEEP_WEEKS = 12


def week_id(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def canonical_url(url: str) -> str:
    p = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref"))]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, "", urlencode(query), ""))


def item_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:12]


def strip_html(text: str, limit: int = 500) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _item(source: dict, title: str, url: str, summary: str, published: datetime) -> dict:
    return {
        "id": item_id(url),
        "source_id": source.get("id", ""),
        "source": source.get("name", ""),
        "title": strip_html(title, 300),
        "url": url,
        "summary": strip_html(summary),
        "published": published.astimezone(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- fetchers

def fetch_rss(source: dict, since: datetime, client: httpx.Client) -> list[dict]:
    resp = client.get(source["url"])
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries:
        stamp = e.get("published_parsed") or e.get("updated_parsed")
        link = e.get("link")
        if not stamp or not link:
            continue
        published = datetime.fromtimestamp(calendar.timegm(stamp), tz=timezone.utc)
        if published < since:
            continue
        summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "")
        items.append(_item(source, e.get("title", link), link, summary, published))
    items.sort(key=lambda i: i["published"], reverse=True)
    return items


def fetch_hackernews(source: dict, since: datetime, client: httpx.Client) -> list[dict]:
    min_points = int(source.get("min_points", 150))
    resp = client.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={
            "tags": "story",
            "numericFilters": f"points>={min_points},created_at_i>={int(since.timestamp())}",
            "hitsPerPage": 100,
        },
    )
    resp.raise_for_status()
    hits = sorted(resp.json().get("hits", []), key=lambda h: h.get("points") or 0, reverse=True)
    items = []
    for h in hits:
        discussion = f"https://news.ycombinator.com/item?id={h['objectID']}"
        summary = (f"{h.get('points', 0)} points, {h.get('num_comments') or 0} comments on Hacker News. "
                   f"Discussion: {discussion}")
        published = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc)
        item = _item(source, h.get("title") or discussion, h.get("url") or discussion, summary, published)
        item["discussion_url"] = discussion
        items.append(item)
    return items


def fetch_github_new_repos(source: dict, since: datetime, client: httpx.Client) -> list[dict]:
    min_stars = int(source.get("min_stars", 200))
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    resp = client.get(
        "https://api.github.com/search/repositories",
        params={"q": f"created:>={since:%Y-%m-%d} stars:>={min_stars}", "sort": "stars",
                "order": "desc", "per_page": PER_SOURCE_LIMIT},
        headers=headers,
    )
    resp.raise_for_status()
    items = []
    for r in resp.json().get("items", []):
        desc = r.get("description") or ""
        summary = f"⭐ {r.get('stargazers_count', 0)} · {r.get('language') or 'n/a'} · {desc}"
        published = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        items.append(_item(source, f"{r['full_name']}: {desc}" if desc else r["full_name"],
                           r["html_url"], summary, published))
    return items


SITEMAP_MAX_PAGES = 30


def _meta(page: str, *names: str) -> str:
    for name in names:
        m = re.search(rf'<meta[^>]+(?:property|name)="{re.escape(name)}"[^>]+content="([^"]*)"', page) or \
            re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{re.escape(name)}"', page)
        if m:
            return html.unescape(m.group(1))
    return ""


def _published(page: str) -> datetime | None:
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page)
    raw = m.group(1) if m else _meta(page, "article:published_time")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
    except ValueError:
        return None


def fetch_sitemap(source: dict, since: datetime, client: httpx.Client) -> list[dict]:
    """First-party news for sites without RSS (e.g. anthropic.com/news).

    `lastmod` in a sitemap is when a page was last *edited*, so it only picks
    candidates; each page's real publish date (JSON-LD datePublished or
    article:published_time) decides whether it is this week's news.
    """
    resp = client.get(source["url"])
    resp.raise_for_status()
    prefixes = source.get("paths") or [source.get("path", "/")]
    candidates = []
    for block in re.findall(r"<url>(.*?)</url>", resp.text, re.S):
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block)
        if not loc or not mod or not any(p in urlparse(loc.group(1)).path for p in prefixes):
            continue
        try:
            lastmod = datetime.fromisoformat(mod.group(1).replace("Z", "+00:00"))
        except ValueError:
            continue
        if lastmod.tzinfo is None:
            lastmod = lastmod.replace(tzinfo=timezone.utc)
        if lastmod >= since:
            candidates.append((lastmod, loc.group(1)))
    candidates.sort(reverse=True)

    def page_item(entry: tuple[datetime, str]) -> dict | None:
        lastmod, url = entry
        page = client.get(url)
        if page.status_code != 200:
            return None
        published = _published(page.text) or lastmod
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published < since:
            return None
        title = _meta(page.text, "og:title", "twitter:title") or url
        summary = _meta(page.text, "og:description", "description")
        return _item(source, title, url, summary, published)

    with ThreadPoolExecutor(max_workers=6) as pool:
        items = [i for i in pool.map(page_item, candidates[:SITEMAP_MAX_PAGES]) if i]
    items.sort(key=lambda i: i["published"], reverse=True)
    return items


FETCHERS = {"rss": fetch_rss, "hackernews": fetch_hackernews, "github_new_repos": fetch_github_new_repos,
            "sitemap": fetch_sitemap}


def collect(sources: list[dict], *, now: datetime | None = None, client: httpx.Client | None = None,
            per_source: int = PER_SOURCE_LIMIT) -> tuple[list[dict], list[dict]]:
    """Fetch the last WINDOW_DAYS from every source. Returns (items, errors).

    One broken source never stops the others; it is reported in `errors`.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    own_client = client is None
    client = client or httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    items: list[dict] = []
    errors: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = [(s, pool.submit(FETCHERS[s["type"]], s, since, client))
                    for s in sources if s.get("type") in FETCHERS]
            for source, job in jobs:
                try:
                    items.extend(job.result()[: int(source.get("limit") or per_source)])
                except Exception as exc:  # noqa: BLE001 - report and continue
                    log.warning("source %s failed: %s", source.get("name"), exc)
                    errors.append({"source": source.get("name", "?"), "error": str(exc)[:200]})
    finally:
        if own_client:
            client.close()

    unique: dict[str, dict] = {}
    for item in items:
        unique.setdefault(item["id"], item)
    return list(unique.values()), errors


# ---------------------------------------------------------------- seen.json

def filter_unseen(items: list[dict], seen: dict, week: str) -> list[dict]:
    """Drop items already reported in an earlier week (re-runs in the same week keep them)."""
    return [i for i in items if seen.get(i["id"], week) == week]


def mark_seen(items: list[dict], seen: dict, week: str) -> dict:
    for item in items:
        seen.setdefault(item["id"], week)
    weeks = sorted(set(seen.values()))
    keep = set(weeks[-SEEN_KEEP_WEEKS:])
    return {k: v for k, v in seen.items() if v in keep}
