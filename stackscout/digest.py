"""Weekly radar: run the pipeline, write the report, render it.

    sources -> collect -> classify (AI) -> match (Python)
            -> industry themes (AI)
            -> report JSON + Telegram text in reports/<user>/<week>.*

Comparisons run after the report is written: `compare_all()` compares every
technology that has a natural rival in the profile (the "So với stack" tab),
and `compare_item()` runs one more when the reader picks another tool. Both
are cached per week, so a comparison costs one AI call.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from .i18n import UserError
from . import ai, classify, collect, compare, config, render, sources, storage

log = logging.getLogger(__name__)

LIMITS = {"ai_news": 10, "stack": 12, "updates": 10, "other_ecosystem": 6, "new_areas": 8}

# "Model & công cụ AI mới": shown to everyone, whatever their profile.
# Groups are codes; the web UI and the digests (render.py) translate them.
AI_GROUPS = {
    "llm-provider-sdk": "models",
    "local-llm-inference": "models",
    "ai-coding-tool": "coding",
    "agent-framework": "agents",
    "agent-protocol": "agents",
}
AI_GROUP_ORDER = ("models", "coding", "agents")
# "llm-provider-sdk" holds both models and SDKs: a new model is never compared
# with an SDK of the stack, only with rival models (market comparison).
MODEL_CATEGORIES = render.MODEL_CATEGORIES
assert MODEL_CATEGORIES == {c for c, g in AI_GROUPS.items() if g == "models"}
MAX_THEME_ITEMS = 150


# Progress stages reported to callers (the web UI translates them).
STAGES = ("collect", "classify", "themes", "done")
Progress = Callable[[str], None]


# ---------------------------------------------------------------- industry themes

def industry_themes(items: list[dict], language: str = "Vietnamese") -> list[dict]:
    """3-5 synthesized themes; links come from collected items only."""
    if not items:
        return []
    by_id = {i["id"]: i for i in items}
    payload = [{"id": i["id"], "title": i["title"], "source": i["source"], "summary": i["summary"][:160]}
               for i in items[:MAX_THEME_ITEMS]]
    try:
        data = ai.complete_json(ai.render("industry_digest", items=json.dumps(payload, ensure_ascii=False),
                                          language=language))
    except ai.AIError as exc:
        log.warning("industry digest failed: %s", exc)
        return []
    themes = []
    for t in data.get("themes") or []:
        if not isinstance(t, dict):
            continue
        links = [_link(by_id[i]) for i in t.get("items") or [] if isinstance(i, str) and i in by_id]
        title = str(t.get("title") or "").strip()
        if title and links:  # a theme without a real link is not reported
            themes.append({"title": title, "summary": str(t.get("summary") or "").strip(),
                           "links": dedupe_links(links, limit=4)})
    return themes[:5]


# ---------------------------------------------------------------- report assembly

def _link(item: dict, official: frozenset[str] = frozenset()) -> dict:
    link = {"title": item["title"], "url": item["url"], "source": item["source"]}
    if item.get("source_id") in official:
        link["official"] = True
    return link


def dedupe_links(links: list[dict], limit: int = 3) -> list[dict]:
    """One link per source (three release notes from the same feed read as noise)."""
    seen: set[str] = set()
    out = []
    for link in links:
        if link["source"] not in seen:
            seen.add(link["source"])
            out.append(link)
    return out[:limit]


def _brief(tech: dict, by_id: dict[str, dict], official: frozenset[str] = frozenset()) -> dict:
    # First-party announcements first, then whoever wrote about it.
    items = sorted((by_id[i] for i in tech["items"] if i in by_id), key=lambda i: i.get("source_id") not in official)
    return {
        "name": tech["name"],
        "version": tech.get("version", ""),
        "kind": tech.get("kind", ""),
        "summary": tech.get("summary", ""),
        "category": tech["category"],
        "category_label": config.categories().get(tech["category"], tech["category"]),
        "ecosystem": tech["ecosystem"],
        "skill": tech.get("skill"),
        "rivals": tech.get("rivals", []),
        "items": [i["id"] for i in items],  # evidence for an on-demand comparison
        "links": dedupe_links([_link(i, official) for i in items]),
    }


def ai_news(techs: list[dict], by_id: dict[str, dict], official: frozenset[str], exclude: set[str]) -> list[dict]:
    """New models and AI tools of the week, first-party announcements first."""
    picked = [t for t in techs
              if t["category"] in AI_GROUPS and t["kind"] in ("new", "release")
              and t["name"].casefold() not in exclude]

    def first_party(t: dict) -> bool:
        return any(by_id[i].get("source_id") in official for i in t["items"] if i in by_id)

    picked.sort(key=lambda t: (first_party(t), len(t["items"])), reverse=True)
    briefs = [{**_brief(t, by_id, official), "group": AI_GROUPS[t["category"]]} for t in picked[: LIMITS["ai_news"]]]
    return sorted(briefs, key=lambda b: AI_GROUP_ORDER.index(b["group"]))  # stable within a group


def run_radar(user_id, *, progress: Progress | None = None, now: datetime | None = None,
              window_days: int = collect.WINDOW_DAYS) -> dict:
    """The week's report. `window_days` = how far back to read (31 for a monthly digest)."""
    progress = progress or (lambda _stage: None)
    now = now or datetime.now(timezone.utc)
    profile = storage.load_profile(user_id)
    if not profile or not profile["skills"]:
        raise UserError("profile.missing")
    active = sources.enabled(sources.load(user_id))
    if not active:
        raise UserError("source.none_enabled")
    week = collect.week_id(now)
    language = storage.output_language(user_id)

    progress("collect")
    items, fetch_errors = collect.collect(active, now=now, window_days=window_days)
    seen_path = storage.user_dir(user_id) / "seen.json"
    seen = storage.read_json(seen_path, {}) or {}
    items = collect.filter_unseen(items, seen, week)
    items.sort(key=lambda i: i["published"], reverse=True)
    by_id = {i["id"]: i for i in items}
    errors = [f"{e['source']}: {e['error']}" for e in fetch_errors]

    progress("classify")
    techs, classify_errors = classify.classify(items, profile, language=language) if items else ([], [])
    errors += classify_errors
    groups = classify.match(profile, techs)

    progress("themes")
    themes = industry_themes(items, language)

    # Each technology appears once: "your tool's update" wins, then new
    # models/AI tools get their own section instead of "new areas".
    official = frozenset(s["id"] for s in active if s.get("official"))
    updated = {t["name"].casefold() for t in groups["updates"]}
    # New AI tools and agent frameworks can be compared with the reader's own
    # (Codex CLI vs Claude Code); new *models* only with rival models (market
    # comparison), never with an SDK that happens to share the category.
    groups["compare"] = [t for t in groups["compare"] if t["category"] not in MODEL_CATEGORIES]
    rivals = {t["name"].casefold(): t["rivals"] for t in groups["compare"]}
    techs = [{**t, "rivals": rivals.get(t["name"].casefold(), [])} for t in techs]
    ai = ai_news(techs, by_id, official, exclude=updated)
    in_ai = {b["name"].casefold() for b in ai}
    for key in ("compare", "other_ecosystem", "new_areas"):
        groups[key] = [t for t in groups[key] if t["name"].casefold() not in in_ai]

    report = {
        "user": str(user_id),
        "week": week,
        "week_label": f"Tuần {int(week.split('-W')[1])}/{week.split('-W')[0]}",
        "generated_at": now.isoformat(timespec="seconds"),
        "language": storage.load_settings(user_id)["language"],
        "stats": {"items": len(items), "sources": len(active), "technologies": len(techs)},
        "errors": errors,
        "ai_news": ai,
        "stack": [_brief(t, by_id, official) for t in groups["compare"][: LIMITS["stack"]]],
        "updates": [_brief(t, by_id, official) for t in groups["updates"][: LIMITS["updates"]]],
        "other_ecosystem": [_brief(t, by_id, official) for t in groups["other_ecosystem"][: LIMITS["other_ecosystem"]]],
        "new_areas": [_brief(t, by_id, official) for t in groups["new_areas"][: LIMITS["new_areas"]]],
        "themes": themes,
        # Evidence for on-demand comparisons (what the reader's sources said this week).
        "items": {i["id"]: {"title": i["title"], "url": i["url"], "source": i["source"],
                            "summary": i["summary"][:400]} for i in items},
    }
    save_report(user_id, report)
    storage.write_json(seen_path, collect.mark_seen(items, seen, week))
    progress("done")
    return report


# ---------------------------------------------------------------- on-demand comparison

REPORT_SECTIONS = ("ai_news", "stack", "updates", "other_ecosystem", "new_areas")
_cache_lock = threading.Lock()


def _comparisons_path(user_id, week: str):
    return storage.user_dir(user_id) / "comparisons" / f"{week}.json"


def comparison_key(name: str, against: str) -> str:
    return f"{name.casefold()}|{against.casefold()}"


def cached_comparisons(user_id, week: str) -> dict:
    if week not in list_reports(user_id):
        return {}
    return storage.read_json(_comparisons_path(user_id, week), {}) or {}


def compare_item(user_id, week: str, name: str, against: str) -> dict:
    """Compare one technology of a weekly report with one tool of the profile.

    Raises ValueError (bad request) or ai.AIError (try again later). Results
    are cached per week, so asking twice costs one AI call.
    """
    report = load_report(user_id, week)
    if report is None:
        raise UserError("report.missing")
    brief = next((b for key in REPORT_SECTIONS for b in report.get(key) or []
                  if b["name"].casefold() == name.casefold()), None)
    if brief is None or "category" not in brief:
        raise UserError("compare.unknown_tech")
    profile = storage.load_profile(user_id)
    skill = next((s for s in (profile or {}).get("skills", []) if s["name"].casefold() == against.casefold()), None)
    if skill is None:
        raise UserError("compare.not_in_profile")

    key = comparison_key(brief["name"], skill["name"])
    with _cache_lock:
        cache = cached_comparisons(user_id, week)
        if key in cache:
            return cache[key]

    tech = {"name": brief["name"], "category": brief["category"], "ecosystem": brief["ecosystem"],
            "summary": brief.get("summary", ""), "items": brief.get("items", []), "rivals": [skill["name"]]}
    result = compare.compare_pair(tech, profile, report.get("items") or {},
                                  language=storage.output_language(user_id))
    result["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _cache_lock:
        cache = cached_comparisons(user_id, week)
        cache[key] = result
        storage.write_json(_comparisons_path(user_id, week), cache)
    return result


def auto_pairs(report: dict, profile: dict | None) -> list[tuple[str, str]]:
    """(technology, its natural rival) for every report entry that has one in the profile."""
    skills = {s["name"].casefold(): s["name"] for s in (profile or {}).get("skills", [])}
    pairs: dict[str, tuple[str, str]] = {}
    for key in ("ai_news", "stack"):
        for b in report.get(key) or []:
            if b.get("category") in MODEL_CATEGORIES:
                continue  # models get the market comparison instead (see run_radar)
            rival = next((skills[r.casefold()] for r in b.get("rivals") or [] if r.casefold() in skills), None)
            if rival and "category" in b:
                pairs.setdefault(b["name"].casefold(), (b["name"], rival))
    return list(pairs.values())


def auto_jobs(user_id, week: str) -> list[tuple[str, Callable[[], dict]]]:
    """Everything the automatic run still has to do for a week, as (key, job):
    stack pairs ("name|rival") first, then market comparisons of new AI models
    and tools ("market|name")."""
    report = load_report(user_id, week)
    if report is None:
        raise UserError("report.missing")
    cache = cached_comparisons(user_id, week)
    market = cached_market(user_id, week)
    jobs: list[tuple[str, Callable[[], dict]]] = [
        (comparison_key(*p), lambda p=p: compare_item(user_id, week, *p))
        for p in auto_pairs(report, storage.load_profile(user_id)) if comparison_key(*p) not in cache]
    jobs += [(market_key(b["name"]), lambda n=b["name"]: market_item(user_id, week, n))
             for b in report.get("ai_news") or []
             if "category" in b and b["name"].casefold() not in market]
    return jobs


def compare_all(user_id, week: str, *, workers: int = 3,
                on_start: Callable[[str], None] | None = None,
                on_finish: Callable[[str, str | None], None] | None = None) -> dict:
    """Run every automatic comparison of a week that is not cached yet.

    A failed one is reported through on_finish(key, error) and skipped; it
    is not cached, so the next run tries it again.
    """
    todo = auto_jobs(user_id, week)

    def one(job: tuple[str, Callable[[], dict]]) -> str | None:
        key, run = job
        if on_start:
            on_start(key)
        error = None
        try:
            run()
        except (ValueError, ai.AIError) as exc:
            log.warning("auto comparison %s failed: %s", key, exc)
            error = str(exc) if isinstance(exc, ValueError) else "AI chưa xử lý được lúc này."
        if on_finish:
            on_finish(key, error)
        return error

    with ThreadPoolExecutor(max_workers=workers) as pool:
        errors = list(pool.map(one, todo))
    return {"total": len(todo), "failed": sum(e is not None for e in errors)}


# ---------------------------------------------------------------- market comparison (new AI models & tools)

def market_key(name: str) -> str:
    return f"market|{name.casefold()}"


def _market_path(user_id, week: str):
    return storage.user_dir(user_id) / "market" / f"{week}.json"


def cached_market(user_id, week: str) -> dict:
    """{technology name (casefolded): market comparison} for a week."""
    if week not in list_reports(user_id):
        return {}
    return storage.read_json(_market_path(user_id, week), {}) or {}


_inflight: dict[str, threading.Event] = {}


def market_item(user_id, week: str, name: str) -> dict:
    """Compare a new AI model or tool of the week with its 3-5 strongest
    competitors. Cached per week; a click while the automatic run is already
    on it waits for that run instead of paying twice."""
    report = load_report(user_id, week)
    if report is None:
        raise UserError("report.missing")
    brief = next((b for b in report.get("ai_news") or [] if b["name"].casefold() == name.casefold()), None)
    if brief is None or "category" not in brief:
        raise UserError("market.unknown_tech")
    key = brief["name"].casefold()
    flight = f"{user_id}|{week}|{key}"
    while True:
        with _cache_lock:
            cache = cached_market(user_id, week)
            if key in cache:
                return cache[key]
            waiting = _inflight.get(flight)
            if waiting is None:
                _inflight[flight] = threading.Event()
                break
        waiting.wait(timeout=compare.TIMEOUT + 60)
        with _cache_lock:
            cache = cached_market(user_id, week)
        if key in cache:
            return cache[key]
        raise ai.AIError("market comparison failed in another request")
    try:
        tech = {"name": brief["name"], "category": brief["category"], "ecosystem": brief.get("ecosystem", "any"),
                "summary": brief.get("summary", ""), "items": brief.get("items", [])}
        result = compare.compare_market(tech, report.get("items") or {}, today=datetime.now(timezone.utc).date().isoformat(),
                                        language=storage.output_language(user_id))
        result["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with _cache_lock:
            cache = cached_market(user_id, week)
            cache[key] = result
            storage.write_json(_market_path(user_id, week), cache)
        return result
    finally:
        with _cache_lock:
            _inflight.pop(flight).set()


# ---------------------------------------------------------------- storage

def save_report(user_id, report: dict) -> None:
    folder = storage.reports_dir(user_id)
    storage.write_json(folder / f"{report['week']}.json", report)
    (folder / f"{report['week']}.txt").write_text("\n\n".join(render_telegram(report)), encoding="utf-8")


def list_reports(user_id) -> list[str]:
    folder = storage.reports_dir(user_id)
    return sorted((p.stem for p in folder.glob("*-W*.json")), reverse=True) if folder.is_dir() else []


def load_report(user_id, week: str) -> dict | None:
    if week not in list_reports(user_id):
        return None
    return storage.read_json(storage.reports_dir(user_id) / f"{week}.json")


# ---------------------------------------------------------------- rendering (see render.py)

def render_telegram(report: dict, comparisons: dict | None = None, lang: str | None = None,
                    market: dict | None = None) -> list[str]:
    """The weekly digest as Telegram HTML messages, in `lang` (default: the report's language)."""
    return render.telegram(render.build(report, comparisons, market, lang))
