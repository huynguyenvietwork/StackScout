"""Classification (AI) and matching against the profile (plain Python).

Step 1: the AI extracts technologies from this week's items into the same
taxonomy as the profile. Step 2 is deliberately not AI: `match()` splits
them into the four groups of the spec with simple, testable rules.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from . import ai, config
from .profile import LEVEL_RANK

log = logging.getLogger(__name__)

BATCH_SIZE = 40
KINDS = ("release", "new", "discussion")
# The prompt forbids generic terms, but models still emit them: enforce it here.
GENERIC_TERMS = {
    "ai", "llm", "llms", "genai", "generative ai", "machine learning", "ml", "agent", "agents",
    "ai agent", "ai agents", "database", "databases", "cloud", "open source", "api", "apis", "saas",
}


# ---------------------------------------------------------------- step 1: AI

def _clean_tech(raw: dict, valid_ids: set[str]) -> dict | None:
    name = raw.get("name").strip() if isinstance(raw.get("name"), str) else ""
    items = [i for i in raw.get("items") or [] if isinstance(i, str) and i in valid_ids]
    if not name or not items or name.casefold() in GENERIC_TERMS:
        return None
    category = str(raw.get("category") or "").lower()
    ecosystem = str(raw.get("ecosystem") or "").lower()
    kind = str(raw.get("kind") or "").lower()
    return {
        "name": name,
        "category": category if category in config.categories() else "other",
        "ecosystem": ecosystem if ecosystem in config.ecosystems() else "any",
        "kind": kind if kind in KINDS else "discussion",
        "version": str(raw.get("version") or "").strip(),
        "summary": str(raw.get("summary") or "").strip(),
        "items": list(dict.fromkeys(items)),
    }


def _classify_batch(batch: list[dict], known: list[str], language: str = "Vietnamese") -> list[dict]:
    payload = [{"id": i["id"], "title": i["title"], "summary": i["summary"][:280], "source": i["source"]}
               for i in batch]
    prompt = ai.render(
        "classify",
        items=json.dumps(payload, ensure_ascii=False),
        known=", ".join(known) or "(none)",
        categories=", ".join(config.categories()),
        ecosystems=", ".join(config.ecosystems()),
        language=language,
    )
    data = ai.complete_json(prompt)
    valid = {i["id"] for i in batch}
    techs = data.get("technologies") if isinstance(data.get("technologies"), list) else []
    return [t for t in (_clean_tech(r, valid) for r in techs if isinstance(r, dict)) if t]


def merge_techs(techs: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for t in techs:
        key = t["name"].casefold()
        if key not in merged:
            merged[key] = {**t, "items": list(t["items"])}
            continue
        m = merged[key]
        m["items"] = list(dict.fromkeys(m["items"] + t["items"]))
        m["version"] = m["version"] or t["version"]
        m["summary"] = m["summary"] or t["summary"]
        if m["kind"] == "discussion" and t["kind"] != "discussion":
            m["kind"] = t["kind"]
    return list(merged.values())


def classify(items: list[dict], profile: dict, *, language: str = "Vietnamese",
             workers: int = 4) -> tuple[list[dict], list[str]]:
    """Returns (technologies, errors). A failed batch is skipped, not fatal."""
    known = [s["name"] for s in profile["skills"]]
    batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    techs: list[dict] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, job in enumerate([pool.submit(_classify_batch, b, known, language) for b in batches], 1):
            try:
                techs.extend(job.result())
            except ai.AIError as exc:
                log.warning("classify batch %d failed: %s", n, exc)
                errors.append(f"Classifying batch {n}/{len(batches)} failed")
    return merge_techs(techs), errors


# ---------------------------------------------------------------- step 2: Python

def ecosystem_match(a: str, b: str) -> bool:
    """Same ecosystem only. "any" pairs with "any" (Dragonfly vs Redis), but not
    with a specific one: a language tagged "any" vs TypeScript is a weak pair."""
    return a == b


def _interesting(tech: dict, interests: list[str]) -> bool:
    text = f"{tech['name']} {tech['summary']}".casefold()
    return any(i.casefold() in text or tech["name"].casefold() in i.casefold() for i in interests)


def _rank_skills(skills: list[dict]) -> list[dict]:
    return sorted(skills, key=lambda s: LEVEL_RANK[s["level"]], reverse=True)


def match(profile: dict, techs: list[dict]) -> dict[str, list[dict]]:
    """Split technologies into the four groups of the spec.

    updates          a tool the user already has (new version, news)
    compare          same category, same ecosystem as a user tool -> find comparisons
    other_ecosystem  same category, different ecosystem -> reference note
    new_areas        category the user has nothing in -> "worth a look"
    """
    skills = profile["skills"]
    interests = profile["person"]["interests"]
    by_name = {s["name"].casefold(): s for s in skills}
    groups: dict[str, list[dict]] = {"updates": [], "compare": [], "other_ecosystem": [], "new_areas": []}

    for t in techs:
        t = {**t, "interest": _interesting(t, interests)}
        if t["name"].casefold() in by_name:
            groups["updates"].append({**t, "skill": by_name[t["name"].casefold()]["name"]})
            continue
        if t["category"] == "other":
            if t["interest"]:
                groups["new_areas"].append(t)
            continue
        same_cat = [s for s in skills if s["category"] == t["category"]]
        same_eco = [s for s in same_cat if ecosystem_match(s["ecosystem"], t["ecosystem"])]
        if same_eco:
            groups["compare"].append({**t, "rivals": [s["name"] for s in _rank_skills(same_eco)]})
        elif same_cat:
            groups["other_ecosystem"].append({**t, "rivals": [s["name"] for s in _rank_skills(same_cat)]})
        else:
            groups["new_areas"].append(t)

    def score(t: dict) -> tuple:
        return (t["interest"], t["kind"] != "discussion", len(t["items"]))

    for group in groups.values():
        group.sort(key=score, reverse=True)
    return groups
