"""Comparison research for the most important pairs (milestone 4, step 3-4).

The AI searches the web, but the rules of the spec are enforced here, in
code, not trusted to the model:
  - every pro/con must cite a source that exists in the source list;
  - fewer than 2 sources -> "insufficient" ("Chưa đủ dữ liệu, theo dõi tiếp");
  - without any independent source, confidence is capped at "medium".
"""

from __future__ import annotations

import json
import logging

from . import ai, config

log = logging.getLogger(__name__)

RECOMMENDATIONS = ("adopt", "trial", "watch", "ignore")
CONFIDENCE = ("low", "medium", "high")
WEB_TOOLS = "WebSearch,WebFetch"
TIMEOUT = 480
MIN_SOURCES = 2
MAX_CLAIMS = 3          # per side: the newsletter shows the most important points only
MAX_CLAIM_CHARS = 240


def _cap(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _reader(profile: dict) -> str:
    """What the comparison needs to judge fit: role and the technologies the
    reader knows, with levels. Nothing about their work (the profile holds none)."""
    return json.dumps(
        {"role": profile["person"]["role"],
         "stack": [f"{s['name']} ({s['level']})" for s in profile["skills"]]},
        ensure_ascii=False,
    )


def _collected(tech: dict, items_by_id: dict[str, dict]) -> str:
    lines = []
    for item_id in tech["items"][:6]:
        if item := items_by_id.get(item_id):
            lines.append(f"- {item['title']} ({item['source']}) {item['url']}\n  {item['summary'][:300]}")
    return "\n".join(lines) or "(none)"


def _sources(data: dict) -> tuple[list[dict], dict[int, int]]:
    """Valid http(s) sources, deduplicated by URL, with the model's numbers mapped to 1..n."""
    sources: list[dict] = []
    renumber: dict[int, int] = {}
    by_url: dict[str, int] = {}
    for s in data.get("sources") or []:
        if not isinstance(s, dict):
            continue
        url = str(s.get("url") or "").strip()
        try:
            n = int(s.get("n"))
        except (TypeError, ValueError):
            continue
        if not url.startswith(("http://", "https://")):
            continue
        if url in by_url:
            renumber[n] = by_url[url]
            continue
        new_n = len(sources) + 1
        renumber[n] = by_url[url] = new_n
        sources.append({"n": new_n, "title": str(s.get("title") or url).strip(), "url": url,
                        "independent": bool(s.get("independent"))})
    return sources, renumber


def _claims(raw, renumber: dict[int, int]) -> list[dict]:
    """Claims that cite at least one valid source; a claim without one is dropped."""
    out = []
    for c in raw or []:
        if not isinstance(c, dict) or not str(c.get("text") or "").strip():
            continue
        refs = set()
        for r in c.get("sources") or []:
            try:
                if int(r) in renumber:
                    refs.add(renumber[int(r)])
            except (TypeError, ValueError):
                pass
        if refs:
            out.append({"text": _cap(str(c["text"]), MAX_CLAIM_CHARS), "sources": sorted(refs)})
    return out[:MAX_CLAIMS]


def _keep_cited(sources: list[dict], claims: list[dict]) -> list[dict]:
    """Keep only sources that back a kept claim, renumbered 1..n in order (claims updated in place)."""
    cited = sorted({n for c in claims for n in c["sources"]})
    compact = {old: new for new, old in enumerate(cited, 1)}
    for c in claims:
        c["sources"] = [compact[n] for n in c["sources"]]
    return [{**s, "n": compact[s["n"]]} for s in sources if s["n"] in compact]


def _confidence(raw, sources: list[dict]) -> str:
    confidence = str(raw or "").lower()
    confidence = confidence if confidence in CONFIDENCE else "low"
    if len(sources) < MIN_SOURCES:
        return "low"
    if not any(s["independent"] for s in sources) and confidence == "high":
        return "medium"
    return confidence


def finalize(tech: dict, rival: str, data: dict) -> dict:
    """Validate the model's answer against the hard rules of the spec."""
    sources, renumber = _sources(data)
    pros, cons = _claims(data.get("pros"), renumber), _claims(data.get("cons"), renumber)
    sources = _keep_cited(sources, pros + cons)

    recommendation = str(data.get("recommendation") or "").lower()
    recommendation = recommendation if recommendation in RECOMMENDATIONS else "watch"
    confidence = _confidence(data.get("confidence"), sources)
    independent = sum(s["independent"] for s in sources)
    if len(sources) < MIN_SOURCES:
        recommendation = "insufficient"

    return {
        "new": tech["name"],
        "current": rival,
        "category": tech["category"],
        "category_label": config.categories().get(tech["category"], tech["category"]),
        "ecosystem": tech["ecosystem"],
        "what_is_new": _cap(str(data.get("what_is_new") or tech.get("summary") or ""), 320),
        "pros": pros,
        "cons": cons,
        "fit": _cap(str(data.get("fit") or ""), 260),
        "recommendation": recommendation,
        "confidence": confidence,
        "sources": sources,
        "independent_sources": independent,
        "items": tech["items"],
    }


def compare_pair(tech: dict, profile: dict, items_by_id: dict[str, dict], *,
                 language: str = "Vietnamese") -> dict:
    """Research `tech` against tech["rivals"][0]. Raises ai.AIError on failure,
    so an on-demand caller can offer a retry instead of caching a non-answer."""
    rival = tech["rivals"][0]
    prompt = ai.render(
        "compare",
        new=tech["name"],
        current=rival,
        category=config.categories().get(tech["category"], tech["category"]),
        ecosystem=tech["ecosystem"],
        reader=_reader(profile),
        collected=_collected(tech, items_by_id),
        language=language,
    )
    data = ai.complete_json(prompt, tools=WEB_TOOLS, timeout=TIMEOUT)
    return finalize(tech, rival, data)


# ---------------------------------------------------------------- market rivals

MAX_RIVALS = 5


def finalize_market(tech: dict, data: dict) -> dict:
    """Same rules as a stack comparison, per competitor: every claim cited,
    a competitor without any cited claim is dropped, at most 5 competitors."""
    sources, renumber = _sources(data)
    rivals = []
    for r in data.get("rivals") or []:
        if not isinstance(r, dict) or not str(r.get("name") or "").strip():
            continue
        pros, cons = _claims(r.get("pros"), renumber), _claims(r.get("cons"), renumber)
        if pros or cons:
            rivals.append({"name": _cap(str(r["name"]), 80), "vendor": _cap(str(r.get("vendor") or ""), 60),
                           "pros": pros, "cons": cons, "verdict": _cap(str(r.get("verdict") or ""), 400)})
    rivals = rivals[:MAX_RIVALS]
    sources = _keep_cited(sources, [c for r in rivals for c in r["pros"] + r["cons"]])
    return {
        "new": tech["name"],
        "category": tech["category"],
        "category_label": config.categories().get(tech["category"], tech["category"]),
        "summary": _cap(str(data.get("summary") or tech.get("summary") or ""), 700),
        "rivals": rivals,
        "insufficient": len(sources) < MIN_SOURCES,
        "confidence": _confidence(data.get("confidence"), sources),
        "sources": sources,
        "independent_sources": sum(s["independent"] for s in sources),
    }


def compare_market(tech: dict, items_by_id: dict[str, dict], *, today: str,
                   language: str = "Vietnamese") -> dict:
    """Compare a new model or AI tool with its 3-5 strongest competitors (web search).
    Raises ai.AIError on failure."""
    prompt = ai.render(
        "market_compare",
        new=tech["name"],
        category=config.categories().get(tech["category"], tech["category"]),
        collected=_collected(tech, items_by_id),
        today=today,
        language=language,
    )
    data = ai.complete_json(prompt, tools=WEB_TOOLS, timeout=TIMEOUT)
    return finalize_market(tech, data)
