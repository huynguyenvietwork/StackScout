"""Milestones 2-6: sources, collection, matching, comparison rules, digest, delivery."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest

from stackscout import ai, classify, collect, compare, digest, notify, sources, storage
from stackscout import profile as prof

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>Cool Blog</title>
<item><title>Fresh &amp; new</title><link>https://cool.dev/fresh?utm_source=x</link>
<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description><pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Too old</title><link>https://cool.dev/old</link><pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STACKSCOUT_REPORTS_DIR", str(tmp_path / "reports"))


def skill(name, category, ecosystem="any", level="intermediate"):
    return {"name": name, "category": category, "ecosystem": ecosystem, "level": level}


PROFILE = prof.clean({
    "person": {"role": "backend", "interests": ["AI agent"]},
    "skills": [skill("Hangfire", "background-jobs", "dotnet", "advanced"), skill("Redis", "cache"),
               skill("Entity Framework Core", "orm-data-access", "dotnet")],
    "projects": [{"name": "AcmeAPI", "description": "API", "stack": ["Hangfire"]}],
})


def mock_client(routes: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, (status, body, ctype) in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(status, content=body.encode(), headers={"content-type": ctype})
        return httpx.Response(404, content=b"not found")
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


# ---------------------------------------------------------------- sources

def test_default_catalog_core_on_and_official_sources_follow_the_stack():
    data = sources.load("u1")  # no profile: only the core sources are on
    on = {s["id"] for s in sources.enabled(data)}
    assert on == {s["id"] for s in data["sources"] if s["tier"] == "core"}
    assert {"anthropic-news", "claude-code-releases", "openai-news", "openai-codex-releases",
            "gemini-blog", "gemini-cli-releases", "google-deepmind"} <= on and len(on) == 15
    # community aggregators are options, not defaults
    assert not {"hackernews", "github-new-repos", "lobsters"} & on
    assert all(s.get("url", "").startswith("https://") for s in data["sources"] if s["type"] in ("rss", "sitemap"))

    storage.save_profile("u1", PROFILE)  # Hangfire (dotnet), Redis, Entity Framework Core
    on = {s["id"] for s in sources.enabled(sources.load("u1"))}
    assert {"dotnet-blog", "redis"} <= on
    assert not {"react", "kubernetes", "postgresql", "thoughtworks"} & on


def test_keyword_matching_uses_whole_words():
    redis = {"tier": "stack", "match": {"keywords": ["redis"]}}
    swift = {"tier": "stack", "match": {"keywords": ["swift"]}}
    p = prof.clean({"skills": [{"name": "Redis Stack"}, {"name": "SwiftUI Kit"}]})
    assert sources.matches_profile(redis, p) and not sources.matches_profile(swift, p)
    assert not sources.default_on({"tier": "extra"}, p) and sources.default_on({"tier": "core"}, None)


def test_manual_choice_wins_and_reset_restores_defaults():
    storage.save_profile("u1", PROFILE)
    sources.set_enabled("u1", "redis", False)          # user turns off a matched source
    sources.set_enabled("u1", "thoughtworks", True)    # and turns on an extra one
    data = sources.load("u1")
    by_id = {s["id"]: s for s in data["sources"]}
    assert by_id["redis"]["enabled"] is False and by_id["thoughtworks"]["enabled"] is True
    storage.save_profile("u1", prof.merge(PROFILE, {"skills": [{"name": "Kubernetes", "category": "containers"}]}))
    by_id = {s["id"]: s for s in sources.load("u1")["sources"]}
    assert by_id["kubernetes"]["enabled"] is True      # untouched source follows the new skill
    assert by_id["redis"]["enabled"] is False          # manual choice kept
    assert len(sources.remove("u1", "infoq")["sources"]) == len(data["sources"]) - 1
    with pytest.raises(sources.SourceError):
        sources.remove("u1", "nope")
    reset = {s["id"]: s for s in sources.reset("u1")["sources"]}
    assert reset["redis"]["enabled"] is True and "infoq" in reset and not reset["thoughtworks"]["enabled"]


def test_old_source_lists_get_new_catalog_entries_without_losing_choices():
    storage.write_yaml("u1", sources.FILE, {"industry": "software-ai", "sources": [
        {"id": "hackernews", "name": "Hacker News", "type": "hackernews", "enabled": True},
        {"id": "lobsters", "name": "Lobsters", "type": "rss", "url": "https://lobste.rs/rss", "enabled": True,
         "user_set": True},
        {"id": "my-blog", "name": "Mine", "type": "rss", "url": "https://mine.dev/feed", "enabled": True,
         "tier": "custom"}]})
    data = sources.load("u1")
    by_id = {s["id"]: s for s in data["sources"]}
    assert by_id["hackernews"]["enabled"] is False      # untouched: follows the catalog (now optional)
    assert by_id["lobsters"]["enabled"] is True         # the user's own choice is kept
    assert by_id["my-blog"]["enabled"] is True and by_id["anthropic-news"]["enabled"] is True
    assert by_id["openai-news"]["enabled"] is True and data["catalog_version"] >= 2
    assert storage.read_yaml("u1", sources.FILE)["catalog_version"] == data["catalog_version"]  # saved once


def test_add_source_discovers_feed_from_html_page():
    page = '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>'
    client = mock_client({"https://cool.dev/feed.xml": (200, FEED, "application/rss+xml"),
                          "https://cool.dev/": (200, page, "text/html")})
    added = sources.add("u1", "cool.dev/", client=client)
    assert added == {**added, "name": "Cool Blog", "type": "rss", "url": "https://cool.dev/feed.xml",
                     "enabled": True, "tier": "custom"}
    with pytest.raises(sources.SourceError, match="already in your list"):
        sources.add("u1", "https://cool.dev/", client=client)


def test_add_source_github_repo_follows_releases_and_unknown_page_fails():
    assert sources.discover("https://github.com/HangfireIO/Hangfire")["url"] == \
        "https://github.com/HangfireIO/Hangfire/releases.atom"
    client = mock_client({"https://nofeed.dev/": (200, "<html></html>", "text/html")})
    with pytest.raises(sources.SourceError, match="No RSS/Atom"):
        sources.discover("https://nofeed.dev/", client=client)


def test_private_hosts_are_refused():
    for host in ("127.0.0.1", "localhost", "10.0.0.5"):
        with pytest.raises(sources.SourceError):
            sources.check_public_host(host)


# ---------------------------------------------------------------- collect

def test_collect_rss_window_html_cleanup_and_broken_source():
    client = mock_client({"https://cool.dev/feed.xml": (200, FEED, "application/rss+xml")})
    srcs = [{"id": "cool", "name": "Cool", "type": "rss", "url": "https://cool.dev/feed.xml"},
            {"id": "dup", "name": "Dup", "type": "rss", "url": "https://cool.dev/feed.xml"},
            {"id": "bad", "name": "Bad", "type": "rss", "url": "https://broken.dev/feed"}]
    items, errors = collect.collect(srcs, now=NOW, client=client)
    assert [i["title"] for i in items] == ["Fresh & new"]  # old item filtered, duplicate merged
    assert items[0]["summary"] == "Hello world"
    assert errors == [{"source": "Bad", "error": errors[0]["error"]}]


def test_hackernews_and_github_parsing():
    hn = {"hits": [{"objectID": "1", "title": "Show HN: X", "url": "https://x.dev", "points": 300,
                    "num_comments": 50, "created_at_i": int(NOW.timestamp()) - 3600},
                   {"objectID": "2", "title": "Ask HN: Y", "url": None, "points": 500,
                    "num_comments": 9, "created_at_i": int(NOW.timestamp()) - 7200}]}
    gh = {"items": [{"full_name": "a/b", "description": "fast queue", "stargazers_count": 900,
                     "language": "Rust", "html_url": "https://github.com/a/b", "created_at": "2026-11-15T00:00:00Z"}]}
    client = mock_client({"https://hn.algolia.com/": (200, json.dumps(hn), "application/json"),
                          "https://api.github.com/": (200, json.dumps(gh), "application/json")})
    since = NOW.replace(day=11)
    items = collect.fetch_hackernews({"name": "HN"}, since, client)
    assert [i["title"] for i in items] == ["Ask HN: Y", "Show HN: X"]  # sorted by points
    assert items[0]["url"] == "https://news.ycombinator.com/item?id=2"
    repo = collect.fetch_github_new_repos({"name": "GH"}, since, client)[0]
    assert repo["title"] == "a/b: fast queue" and "⭐ 900" in repo["summary"]


def test_sitemap_uses_real_publish_date_not_lastmod():
    sitemap = """<urlset><url><loc>https://lab.ai/news/new-model</loc><lastmod>2026-11-17T10:00:00Z</lastmod></url>
    <url><loc>https://lab.ai/news/old-post-edited</loc><lastmod>2026-11-16T10:00:00Z</lastmod></url>
    <url><loc>https://lab.ai/careers/job</loc><lastmod>2026-11-17T10:00:00Z</lastmod></url>
    <url><loc>https://lab.ai/news/ancient</loc><lastmod>2025-01-01T00:00:00Z</lastmod></url></urlset>"""
    def page(title, date):
        return (f'<html><head><meta property="og:title" content="{title}"><meta name="description" content="About {title}">'
                f'<script type="application/ld+json">{{"datePublished":"{date}"}}</script></head></html>')
    client = mock_client({
        "https://lab.ai/sitemap.xml": (200, sitemap, "application/xml"),
        "https://lab.ai/news/new-model": (200, page("Model X &amp; tools", "2026-11-17T09:00:00Z"), "text/html"),
        "https://lab.ai/news/old-post-edited": (200, page("Old post", "2025-10-27T00:00:00Z"), "text/html"),
    })
    src = {"id": "lab", "name": "Lab", "type": "sitemap", "url": "https://lab.ai/sitemap.xml", "paths": ["/news/"]}
    items, errors = collect.collect([src], now=NOW, client=client)
    assert errors == [] and [(i["title"], i["summary"]) for i in items] == [("Model X & tools", "About Model X & tools")]


def test_seen_only_hides_items_from_earlier_weeks():
    items = [{"id": "a"}, {"id": "b"}]
    seen = collect.mark_seen([{"id": "a"}], {}, "2026-W46")
    assert collect.filter_unseen(items, seen, "2026-W47") == [{"id": "b"}]
    seen = collect.mark_seen(items, seen, "2026-W47")
    assert collect.filter_unseen(items, seen, "2026-W47") == [{"id": "b"}]  # re-run same week
    assert collect.canonical_url("https://www.X.dev/a/?utm_source=t#top") == "https://x.dev/a"


# ---------------------------------------------------------------- classify + match

def tech(name, category, ecosystem="any", items=("i1",), kind="new", summary=""):
    return {"name": name, "category": category, "ecosystem": ecosystem, "kind": kind,
            "version": "", "summary": summary, "items": list(items)}


def test_match_splits_into_the_four_groups():
    groups = classify.match(PROFILE, [
        tech("hangfire", "background-jobs", "dotnet", kind="release"),
        tech("TickerQ", "background-jobs", "dotnet"),
        tech("Dragonfly", "cache", "any"),
        tech("BullMQ", "background-jobs", "node"),
        tech("LangGraph", "agent-framework", "python"),
        tech("Some company", "other"),
        tech("AgentKit", "other", summary="AI agent toolkit"),
    ])
    assert [(t["name"], t["skill"]) for t in groups["updates"]] == [("hangfire", "Hangfire")]
    assert [(t["name"], t["rivals"][0]) for t in groups["compare"]] == [("TickerQ", "Hangfire"), ("Dragonfly", "Redis")]
    assert [t["name"] for t in groups["other_ecosystem"]] == ["BullMQ"]
    assert [t["name"] for t in groups["new_areas"]] == ["AgentKit", "LangGraph"]  # interest first; plain "other" dropped


def test_classify_drops_unknown_items_and_merges_batches(monkeypatch):
    items = [{"id": f"i{n}", "title": f"t{n}", "summary": "", "source": "s"} for n in range(45)]
    answer = {"technologies": [
        {"name": "TickerQ", "category": "background-jobs", "ecosystem": "dotnet", "kind": "new", "items": ["i1", "i44"]},
        {"name": "Ghost", "category": "cache", "items": ["not-an-item"]},
        {"name": "llm", "category": "llm-provider-sdk", "items": ["i3"]},
        {"name": "Weird", "category": "nonsense", "ecosystem": "cobol", "kind": "??", "items": ["i2"]}]}
    monkeypatch.setattr(ai, "complete", lambda prompt, **kw: json.dumps(answer))
    techs, errors = classify.classify(items, PROFILE)
    by_name = {t["name"]: t for t in techs}
    assert set(by_name) == {"TickerQ", "Weird"} and errors == []
    assert (by_name["Weird"]["category"], by_name["Weird"]["ecosystem"], by_name["Weird"]["kind"]) == ("other", "any", "discussion")


# ---------------------------------------------------------------- compare rules

def test_compare_requires_cited_claims_and_two_sources():
    t = {**tech("TickerQ", "background-jobs", "dotnet"), "rivals": ["Hangfire"]}
    good = compare.finalize(t, "Hangfire", {
        "what_is_new": "x", "recommendation": "adopt", "confidence": "high",
        "pros": [{"text": "nhanh hơn", "sources": [1, 9]}, {"text": "không dẫn nguồn", "sources": []}],
        "cons": [{"text": "ít tài liệu", "sources": ["3"]}],
        "sources": [{"n": 1, "title": "Vendor", "url": "https://vendor.dev/b", "independent": False},
                    {"n": 2, "title": "Dup", "url": "https://vendor.dev/b"},
                    {"n": 3, "title": "Blog", "url": "https://blog.dev/x", "independent": False},
                    {"n": 4, "title": "Bad", "url": "javascript:alert(1)"}]})
    assert [p["text"] for p in good["pros"]] == ["nhanh hơn"]
    assert good["cons"] == [{"text": "ít tài liệu", "sources": [2]}]  # renumbered after dedupe
    assert [s["url"] for s in good["sources"]] == ["https://vendor.dev/b", "https://blog.dev/x"]
    assert (good["recommendation"], good["confidence"]) == ("adopt", "medium")  # no independent source

    thin = compare.finalize(t, "Hangfire", {"recommendation": "adopt", "confidence": "high",
                                            "sources": [{"n": 1, "url": "https://a.dev"}]})
    assert (thin["recommendation"], thin["confidence"]) == ("insufficient", "low")

    # Sources nobody cites don't count towards the 2-source minimum.
    uncited = compare.finalize(t, "Hangfire", {
        "recommendation": "trial", "pros": [{"text": "a", "sources": [1]}],
        "sources": [{"n": 1, "url": "https://a.dev"}, {"n": 2, "url": "https://b.dev"}]})
    assert uncited["recommendation"] == "insufficient" and len(uncited["sources"]) == 1


def test_compare_caps_length_for_the_newsletter():
    t = {**tech("TickerQ", "background-jobs", "dotnet"), "rivals": ["Hangfire"]}
    srcs = [{"n": n, "url": f"https://s{n}.dev", "independent": True} for n in (1, 2)]
    out = compare.finalize(t, "Hangfire", {
        "what_is_new": "x" * 1000, "fit": "y" * 1000, "sources": srcs,
        "pros": [{"text": f"pro {i} " + "z" * 400, "sources": [1]} for i in range(6)],
        "cons": [{"text": f"con {i}", "sources": [2]} for i in range(6)]})
    assert len(out["pros"]) == len(out["cons"]) == compare.MAX_CLAIMS
    assert len(out["pros"][0]["text"]) == compare.MAX_CLAIM_CHARS and out["pros"][0]["text"].endswith("…")
    assert len(out["what_is_new"]) <= 600 and len(out["fit"]) <= 500


# ---------------------------------------------------------------- digest end to end

def fake_ai(prompt, **kw):
    if "Extract the concrete technologies" in prompt:
        batch = json.loads(prompt.split("<items>")[1].split("</items>")[0])
        ids = [batch[0]["id"]]
        return json.dumps({"technologies": [
            {"name": "Gemini 4", "category": "llm-provider-sdk", "kind": "new", "summary": "Model mới",
             "items": [i["id"] for i in batch]},
            {"name": "Some model chat", "category": "llm-provider-sdk", "kind": "discussion", "items": ids},
            {"name": "TickerQ", "category": "background-jobs", "ecosystem": "dotnet", "kind": "new",
             "summary": "Thư viện job mới", "items": ids},
            {"name": "Redis", "category": "cache", "kind": "release", "version": "8.4", "summary": "Bản mới", "items": ids}]})
    if "honest, sourced comparison" in prompt:
        assert kw["tools"] == "WebSearch,WebFetch"
        return json.dumps({"what_is_new": "Mới", "recommendation": "trial", "confidence": "medium",
                           "pros": [{"text": "Nhanh <b>hơn</b>", "sources": [1]}],
                           "cons": [{"text": "Ít người dùng", "sources": [2]}], "fit": "Hợp",
                           "sources": [{"n": 1, "title": "Bench", "url": "https://b.dev", "independent": True},
                                       {"n": 2, "title": "HN", "url": "https://news.ycombinator.com/item?id=1"}]})
    if "STRONGEST current competitors" in prompt:
        assert kw["tools"] == "WebSearch,WebFetch"
        return json.dumps({"summary": "Dẫn đầu", "confidence": "high", "rivals": [
            {"name": "GPT-6.2", "vendor": "OpenAI", "pros": [{"text": "Rẻ hơn", "sources": [1]}],
             "cons": [{"text": "Chậm hơn", "sources": [2]}], "verdict": "Chọn Gemini nếu cần rẻ"},
            {"name": "Uncited", "pros": [{"text": "x", "sources": [9]}]}],
            "sources": [{"n": 1, "title": "Artificial Analysis", "url": "https://aa.ai", "independent": True},
                        {"n": 2, "title": "LMArena", "url": "https://lmarena.ai", "independent": True}]})
    if "editor of a weekly tech newsletter" in prompt:
        first = json.loads(prompt.split("<items>")[1].split("</items>")[0])[0]["id"]
        return json.dumps({"themes": [{"title": "Job queues", "summary": "Tóm tắt", "items": [first, "fake"]},
                                      {"title": "No links", "summary": "x", "items": ["fake"]}]})
    raise AssertionError("unexpected prompt")


def test_run_radar_end_to_end(monkeypatch):
    storage.save_profile("web", PROFILE)
    fetched = [{"id": "i1", "source_id": "s", "source": "Cool", "title": "TickerQ 1.0", "url": "https://t.dev",
                "summary": "jobs", "published": "2026-11-17T00:00:00+00:00"},
               {"id": "i2", "source_id": "gemini-blog", "source": "Google Gemini Blog", "title": "Introducing Gemini 4",
                "url": "https://blog.google/g4", "summary": "", "published": "2026-11-16T00:00:00+00:00"}]
    monkeypatch.setattr(collect, "collect", lambda srcs, now=None: (list(fetched), [{"source": "X", "error": "down"}]))
    storage.save_settings("web", {"language": "en"})
    prompts = []
    monkeypatch.setattr(ai, "complete", lambda prompt, **kw: prompts.append((prompt, kw)) or fake_ai(prompt, **kw))
    steps = []
    report = digest.run_radar("web", progress=steps.append, now=NOW)

    assert report["week"] == "2026-W47" and report["week_label"] == "Tuần 47/2026"
    assert report["stats"]["items"] == 2 and report["stats"]["technologies"] == 4
    assert steps == ["collect", "classify", "themes", "done"]
    assert not any(kw.get("tools") for _, kw in prompts)  # no web search during the weekly run
    assert all("in English" in p for p, _ in prompts)  # AI writes in the user's language
    ai_news = report["ai_news"]
    assert [(b["name"], b["group"]) for b in ai_news] == [("Gemini 4", "models")]  # discussion excluded
    assert ai_news[0]["links"][0] == {"title": "Introducing Gemini 4", "url": "https://blog.google/g4",
                                      "source": "Google Gemini Blog", "official": True}  # first-party link first
    assert "Gemini 4" not in [b["name"] for b in report["new_areas"]]  # shown once
    assert report["stats"]["sources"] == len(sources.enabled(sources.load("web")))
    stack = report["stack"]
    assert [(b["name"], b["rivals"][0], b["category"]) for b in stack] == [("TickerQ", "Hangfire", "background-jobs")]
    assert stack[0]["items"] and set(stack[0]["items"]) <= set(report["items"])  # evidence kept for later
    assert [u["name"] for u in report["updates"]] == ["Redis"]
    assert [t["title"] for t in report["themes"]] == ["Job queues"]  # theme without real link dropped
    assert report["errors"] == ["X: down"] and report["language"] == "en"
    assert digest.list_reports("web") == ["2026-W47"]
    assert digest.load_report("web", "2026-W47")["week"] == "2026-W47"
    assert digest.load_report("web", "../../etc") is None

    text = "\n".join(digest.render_telegram(report, lang="vi"))
    assert text.index("MODEL &amp; CÔNG CỤ AI MỚI") < text.index("1. CÙNG LOẠI VỚI STACK")
    assert "Google Gemini Blog</a> (chính chủ)" in text and "TickerQ</b> (cùng loại Hangfire)" in text
    for heading in ("TECH RADAR — Tuần 47/2026", "2. CẬP NHẬT", "3. CÙNG LOẠI", "4. LĨNH VỰC MỚI", "5. TỔNG HỢP"):
        assert heading in text

    # "So với stack": one comparison on demand, with web search, cached
    calls = []
    monkeypatch.setattr(ai, "complete", lambda prompt, **kw: calls.append(kw) or fake_ai(prompt, **kw))
    result = digest.compare_item("web", "2026-W47", "tickerq", "hangfire")
    assert (result["new"], result["current"], result["recommendation"]) == ("TickerQ", "Hangfire", "trial")
    assert calls[0]["tools"] == "WebSearch,WebFetch"
    assert digest.compare_item("web", "2026-W47", "TickerQ", "Hangfire") == result and len(calls) == 1
    assert list(digest.cached_comparisons("web", "2026-W47")) == ["tickerq|hangfire"]
    with pytest.raises(ValueError):
        digest.compare_item("web", "2026-W47", "TickerQ", "Not in profile")
    with pytest.raises(ValueError):
        digest.compare_item("web", "2026-W47", "Unknown tech", "Hangfire")

    def broken(prompt, **kw):
        raise ai.AIError("down")
    monkeypatch.setattr(ai, "complete", broken)
    with pytest.raises(ai.AIError):  # failures are not cached, the reader can retry
        digest.compare_item("web", "2026-W47", "Gemini 4", "Redis")
    assert list(digest.cached_comparisons("web", "2026-W47")) == ["tickerq|hangfire"]


def test_auto_compare_every_natural_pair_and_show_verdicts(monkeypatch):
    storage.save_profile("web", PROFILE)
    fetched = [{"id": "i1", "source_id": "s", "source": "Cool", "title": "TickerQ 1.0", "url": "https://t.dev",
                "summary": "jobs", "published": "2026-11-17T00:00:00+00:00"}]
    monkeypatch.setattr(collect, "collect", lambda srcs, now=None: (list(fetched), []))
    monkeypatch.setattr(ai, "complete", lambda prompt, **kw: fake_ai(prompt, **kw))
    report = digest.run_radar("web", now=NOW)
    assert digest.auto_pairs(report, PROFILE) == [("TickerQ", "Hangfire")]  # Gemini 4 has no rival in the profile

    started, finished = [], []
    done = digest.compare_all("web", "2026-W47", workers=1, on_start=started.append,
                              on_finish=lambda key, err: finished.append((key, err)))
    assert done == {"total": 2, "failed": 0}
    assert started == ["tickerq|hangfire", "market|gemini 4"]  # stack pairs first, then AI market
    assert finished == [("tickerq|hangfire", None), ("market|gemini 4", None)]
    market = digest.cached_market("web", "2026-W47")["gemini 4"]
    assert [r["name"] for r in market["rivals"]] == ["GPT-6.2"]  # uncited competitor dropped
    assert market["confidence"] == "high" and not market["insufficient"] and len(market["sources"]) == 2
    assert digest.compare_all("web", "2026-W47") == {"total": 0, "failed": 0}  # cached: no second AI call

    text = "\n".join(digest.render_telegram(report, digest.cached_comparisons("web", "2026-W47"), lang="vi",
                                             market=digest.cached_market("web", "2026-W47")))
    assert "↳ So với: GPT-6.2" in text  # market rivals under the AI model
    assert "↳ vs Hangfire: 🟡 THỬ NGHIỆM" in text and "So với stack" in text

    def broken(prompt, **kw):
        raise ai.AIError("down")
    (storage.user_dir("web") / "comparisons" / "2026-W47.json").unlink()
    (storage.user_dir("web") / "market" / "2026-W47.json").unlink()
    monkeypatch.setattr(ai, "complete", broken)
    failures = []
    assert digest.compare_all("web", "2026-W47", on_finish=lambda k, e: failures.append(e))["failed"] == 2
    assert failures and failures[0] and digest.cached_comparisons("web", "2026-W47") == {}  # retried next run


def test_market_comparison_rules():
    t = tech("Gemini 4", "llm-provider-sdk")
    out = compare.finalize_market(t, {"confidence": "high", "rivals": [
        {"name": f"R{i}", "pros": [{"text": "a", "sources": [1]}], "cons": [{"text": "b", "sources": [1]}]} for i in range(7)],
        "sources": [{"n": 1, "title": "Vendor blog", "url": "https://v.dev", "independent": False}]})
    assert len(out["rivals"]) == compare.MAX_RIVALS  # 3-5 rivals, never more
    assert out["insufficient"] and out["confidence"] == "low"  # one source is not enough
    none = compare.finalize_market(t, {"rivals": [{"name": "X", "pros": [{"text": "a"}]}], "sources": []})
    assert none["rivals"] == [] and none["sources"] == []


def test_market_item_waits_for_a_run_already_in_flight(monkeypatch):
    storage.save_profile("web", PROFILE)
    report = {"week": "2026-W47", "ai_news": [{"name": "Gemini 4", "category": "llm-provider-sdk", "group": "models", "summary": "", "items": []}],
              "stats": {"items": 0, "sources": 0}, "week_label": "x", "items": {}}
    digest.save_report("web", report)
    calls, gate = [], threading.Event()

    def slow(tech, items, **kw):
        calls.append(1)
        gate.wait(2)
        return {"new": tech["name"], "rivals": []}
    monkeypatch.setattr(compare, "compare_market", slow)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(digest.market_item, "web", "2026-W47", "Gemini 4")
        time.sleep(0.1)
        second = pool.submit(digest.market_item, "web", "2026-W47", "gemini 4")
        time.sleep(0.1)
        gate.set()
        assert first.result()["new"] == second.result()["new"] == "Gemini 4"
    assert len(calls) == 1
    with pytest.raises(ValueError):
        digest.market_item("web", "2026-W47", "Not AI news")


def test_new_models_are_not_paired_with_an_sdk():
    profile = prof.clean({"skills": [skill("Anthropic SDK", "llm-provider-sdk", "any", "advanced")]})
    report = {"ai_news": [{"name": "Gemini 4", "category": "llm-provider-sdk", "rivals": ["Anthropic SDK"]}],
              "stack": [{"name": "Granite 4.1", "category": "llm-provider-sdk", "rivals": ["Anthropic SDK"]}]}
    assert digest.auto_pairs(report, profile) == []  # a model vs an SDK means nothing


def test_ai_news_keeps_rivals_for_the_compare_tab():
    profile = prof.clean({"skills": [skill("Claude Code", "ai-coding-tool", "any", "advanced")]})
    report = {"ai_news": [{"name": "Codex CLI", "category": "ai-coding-tool", "rivals": ["Claude Code"]}],
              "stack": [{"name": "Old", "rivals": ["Claude Code"]}]}  # pre-taxonomy entry: skipped
    assert digest.auto_pairs(report, profile) == [("Codex CLI", "Claude Code")]


def test_run_radar_needs_profile():
    with pytest.raises(ValueError, match="profile") as err:
        digest.run_radar("nobody", now=NOW)
    assert err.value.text("vi") == "Chưa có hồ sơ kỹ năng." and err.value.text("ja-JP").startswith("スキル")


def test_version_is_not_repeated_when_already_in_the_name():
    def first_line(b):
        report = {"week": "2026-W47", "stats": {"items": 1, "sources": 1}, "updates": [b]}
        return "\n".join(digest.render_telegram(report, lang="en"))
    assert "<b>GPT-6.2 Astra</b>:" in first_line({"name": "GPT-6.2 Astra", "version": "6.2", "summary": "x", "links": []})
    assert "<b>Codex 0.170.0</b>" in first_line({"name": "Codex", "version": "0.170.0", "summary": "x"})


def test_links_are_one_per_source():
    links = [{"source": "A", "url": "1"}, {"source": "A", "url": "2"}, {"source": "B", "url": "3"},
             {"source": "C", "url": "4"}, {"source": "D", "url": "5"}]
    assert [l["url"] for l in digest.dedupe_links(links)] == ["1", "3", "4"]


def test_pack_respects_telegram_limit():
    from stackscout import render
    msgs = render.pack(["a" * 3000, "b" * 3000, "\n".join(["c" * 100] * 80)], 3900)
    assert len(msgs) >= 3 and all(len(m) <= 3900 for m in msgs)


# ---------------------------------------------------------------- notify

DIGEST = {"week": "2026-W47", "language": "ja", "stats": {"items": 3, "sources": 2}, "errors": [],
          "ai_news": [{"name": "Gemini 4", "group": "models", "summary": "New *model* <b>", "rivals": [],
                       "links": [{"url": "https://blog.google/g4", "source": "Gemini Blog", "official": True}]}],
          "stack": [{"name": "TickerQ", "summary": "jobs", "rivals": ["Hangfire"], "links": []}],
          "updates": [], "other_ecosystem": [], "new_areas": [], "themes": []}


def test_notify_chat_and_send(monkeypatch):
    monkeypatch.delenv("STACKSCOUT_TELEGRAM_CHAT_ID", raising=False)
    assert notify.chat_for(12345) == "12345" and notify.chat_for("web") is None
    monkeypatch.setenv("STACKSCOUT_TELEGRAM_CHAT_ID", "999")
    assert notify.chat_for("web") == "999"

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    n = notify.send_report(DIGEST, "999", token="t", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert n == len(sent) == 1 and sent[0]["parse_mode"] == "HTML" and sent[0]["chat_id"] == "999"
    assert "テックレーダー — 2026年 第47週" in sent[0]["text"]  # the report's language (ja)
    assert "New *model* &lt;b&gt;" in sent[0]["text"]  # escaped for Telegram HTML

    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"ok": False, "description": "chat not found"})))
    with pytest.raises(notify.NotifyError, match="chat not found"):
        notify.send_report(DIGEST, "1", token="t", client=bad)


def test_digest_goes_to_every_configured_channel(monkeypatch):
    for name in ("TELEGRAM_BOT_TOKEN", "STACKSCOUT_TELEGRAM_CHAT_ID", "SMTP_HOST", "STACKSCOUT_EMAIL_TO",
                 "STACKSCOUT_SLACK_WEBHOOK_URL", "STACKSCOUT_DISCORD_WEBHOOK_URL", "STACKSCOUT_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)
    assert notify.configured("web") == []
    monkeypatch.setenv("STACKSCOUT_SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setenv("STACKSCOUT_DISCORD_WEBHOOK_URL", "https://discord.test/api/webhooks/1/y")
    monkeypatch.setenv("STACKSCOUT_WEBHOOK_URL", "https://n8n.test/hook")
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("STACKSCOUT_EMAIL_TO", "me@example.test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    assert notify.configured("web") == ["email", "slack", "discord", "webhook"]  # no Telegram chat for the web user
    assert notify.configured(12345) == ["telegram"]  # bot users: their own chat only

    posts = {}

    def handler(request):
        posts.setdefault(request.url.host, []).append(json.loads(request.content))
        if request.url.host == "discord.test" and len(posts["discord.test"]) == 1:
            return httpx.Response(429, json={"retry_after": 0})  # rate limited once: retried
        return httpx.Response(204 if request.url.host == "discord.test" else 200, text="ok")

    mails = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self, context):
            mails.append("tls")
        def send_message(self, msg):
            mails.append(msg)
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)

    result = notify.send_digest("web", DIGEST, lang="en", comparisons={"tickerq|hangfire": {"current": "Hangfire", "recommendation": "trial"}},
                                client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result == {"email": None, "slack": None, "discord": None, "webhook": None}
    slack = posts["hooks.slack.test"][0]["text"]
    assert "*1. SAME KIND AS YOUR STACK*" in slack and "↳ vs Hangfire: 🟡 TRIAL" in slack and "&lt;b&gt;" in slack
    discord = posts["discord.test"][-1]
    assert discord["flags"] == 4 and "New \\*model\\*" in discord["content"] and "(<https://blog.google/g4>)" in discord["content"]
    hook = posts["n8n.test"][0]
    assert hook["source"] == "stackscout" and hook["lang"] == "en" and hook["sections"][0]["title"].startswith("NEW AI")
    assert mails[0] == "tls" and mails[1]["Subject"] == "StackScout — Week 47, 2026" and mails[1]["To"] == "me@example.test"
    assert mails[1].get_body(("html",)).get_content().count("<b>TickerQ</b>") == 1

    def down(request):
        return httpx.Response(500, text="boom")
    failed = notify.send_digest("web", DIGEST, channels=["slack", "webhook"], client=httpx.Client(transport=httpx.MockTransport(down)))
    assert set(failed) == {"slack", "webhook"} and all("500" in e for e in failed.values())  # one failure never stops the others


# ---------------------------------------------------------------- import (milestone 6)

def test_parse_import_accepts_fenced_yaml_and_rejects_junk():
    text = "```yaml\nperson:\n  role: dev\nskills:\n  - name: Go\n    category: language\n    ecosystem: go\n```"
    assert prof.parse_import(text)["skills"][0]["name"] == "Go"
    for bad in ("skills: [", "just: text", "!!python/object:os.system {}"):
        with pytest.raises(ValueError):
            prof.parse_import(bad)


def test_schedule_next_run_is_the_coming_weekday():
    from stackscout import scheduler
    tz = timezone.utc
    wed = datetime(2026, 11, 18, 9, 0, tzinfo=tz)
    assert scheduler.next_run(wed, "mon", "08:00") == datetime(2026, 11, 23, 8, 0, tzinfo=tz)
    assert scheduler.next_run(wed, "wed", "10:30") == datetime(2026, 11, 18, 10, 30, tzinfo=tz)  # later today
    assert scheduler.next_run(wed, "wed", "08:00") == datetime(2026, 11, 25, 8, 0, tzinfo=tz)  # already passed


def test_digest_shows_no_stack_verdict_under_a_new_model():
    report = {"week": "2026-W47", "stats": {"items": 1, "sources": 1},
              "ai_news": [{"name": "Gemini 4", "group": "models", "category": "llm-provider-sdk", "rivals": ["Anthropic SDK"]}]}
    text = "\n".join(digest.render_telegram(report, {"gemini 4|anthropic sdk": {"current": "Anthropic SDK", "recommendation": "trial"}},
                                           lang="en", market={"gemini 4": {"rivals": [{"name": "GPT-6.2"}]}}))
    assert "vs Anthropic SDK" not in text and "↳ Vs.: GPT-6.2" in text


def test_scheduler_sends_once_per_week_after_the_slot(monkeypatch):
    from stackscout import scheduler
    storage.save_profile("web", PROFILE)
    notify.save_settings("web", {"schedule": {"day": "wed", "time": "08:00"},
                                 "channels": {"slack": {"enabled": True, "url": "https://hooks.slack.com/services/x"}}})
    delivered = []

    def fake_deliver(uid, now=None, send=True):
        delivered.append(uid)
        notify.record(uid, "digest", {"slack": None}, sent_week=collect.week_id(now))
        return {"slack": None}
    monkeypatch.setattr(scheduler, "deliver", fake_deliver)
    tz = timezone.utc
    assert scheduler.tick(datetime(2026, 11, 18, 7, 59, tzinfo=tz)) == []  # Wednesday, before the slot
    assert scheduler.tick(datetime(2026, 11, 18, 8, 1, tzinfo=tz)) == ["web"]
    assert scheduler.tick(datetime(2026, 11, 19, 9, 0, tzinfo=tz)) == []  # already sent this week
    assert scheduler.next_delivery("web", datetime(2026, 11, 19, 9, 0, tzinfo=tz)) == datetime(2026, 11, 25, 8, 0, tzinfo=tz)
    notify.save_settings("web", {"schedule": {"enabled": False}})
    assert scheduler.tick(datetime(2026, 11, 26, 9, 0, tzinfo=tz)) == [] and delivered == ["web"]


def test_notify_settings_fall_back_to_env(monkeypatch):
    monkeypatch.setenv("STACKSCOUT_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/abc")
    assert notify.configured("web") == ["discord"]  # complete from .env and never switched off: on
    view = notify.public_settings("web")["channels"]["discord"]
    assert view["from_env"] == ["url"] and view["values"]["url"]["set"]
    notify.save_settings("web", {"channels": {"discord": {"enabled": False}}})
    assert notify.configured("web") == []


def test_telegram_chat_ids_from_recent_messages():
    def handler(request):
        return httpx.Response(200, json={"ok": True, "result": [
            {"message": {"chat": {"id": 42, "type": "private", "first_name": "An", "last_name": "Le"}}},
            {"my_chat_member": {"chat": {"id": -100, "type": "group", "title": "Team"}}},
            {"message": {"chat": {"id": 42, "type": "private", "first_name": "An"}}}]})
    chats = notify.telegram_chats("1:abc", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert chats == [{"id": "42", "name": "An", "type": "private"}, {"id": "-100", "name": "Team", "type": "group"}]
