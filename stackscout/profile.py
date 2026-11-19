"""Skill profiles: AI normalisation, validation, merging and display.

A profile is a plain dict with the same shape as the YAML in
prompts/extract_profile.md:

    person:   {role: str, interests: [str]}
    skills:   [{name, category, ecosystem, level}]

Everything coming from the AI or from an imported file goes through
`clean()`, so the rest of the code can trust the shape and the taxonomy.

Privacy: a profile holds technology, tool and framework names and how well
the person knows them, nothing about their work. Projects, repo names, what
they are for, `used_in` and `evidence` from older profiles or imported files
are dropped by `clean()`, which also scrubs anything that looks like a URL,
email, IP, hostname or secret from the free-text fields.
"""

from __future__ import annotations

import copy
import html
import json
import re
from typing import Any

import yaml

from .i18n import UserError
from . import ai, config

LEVEL_RANK = {level: i for i, level in enumerate(config.LEVELS)}
LEVEL_LABEL = {"beginner": "mới làm quen", "intermediate": "khá", "advanced": "thành thạo"}
DEFAULT_LEVEL = "intermediate"

# What must never be stored, whatever the AI or an imported file says.
_SENSITIVE = [
    re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I),                      # URLs
    re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b"),                         # emails
    re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b"),                       # IPv4
    re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|vn|app|cloud|internal|local|ai|co)\b(?::\d+)?", re.I),
    re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{24,}\b"),             # tokens, keys, long ids
]


def scrub(text: str) -> str:
    """Remove URLs, emails, IPs, hostnames and secret-looking strings."""
    for pattern in _SENSITIVE:
        text = pattern.sub("", text)
    text = re.sub(r"\s+([,.;:)])", r"\1", re.sub(r"\(\s*\)", "", text))
    return " ".join(text.split()).strip(" ,;:-")




def empty_profile() -> dict:
    return {"person": {"role": "", "interests": []}, "skills": []}


# ---------------------------------------------------------------- validation

def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _str(item)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


def _union(a: list[str], b: list[str]) -> list[str]:
    return _str_list(a + b)


def _dicts(value: Any) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _clean_skill(item: dict) -> dict | None:
    name = _str(item.get("name"))
    if not name:
        return None
    category = _str(item.get("category")).lower()
    ecosystem = _str(item.get("ecosystem")).lower()
    level = _str(item.get("level")).lower()
    return {
        "name": name,
        "category": category if category in config.categories() else "other",
        "ecosystem": ecosystem if ecosystem in config.ecosystems() else "any",
        "level": level if level in LEVEL_RANK else DEFAULT_LEVEL,
    }


def _merge_skill(base: dict, new: dict) -> None:
    """Fold `new` into `base` (same technology) in place."""
    if LEVEL_RANK[new["level"]] > LEVEL_RANK[base["level"]]:
        base["level"] = new["level"]
    if base["category"] == "other" and new["category"] != "other":
        base["category"] = new["category"]
    if base["ecosystem"] == "any" and new["ecosystem"] != "any":
        base["ecosystem"] = new["ecosystem"]


def _merge_into(target: list[dict], items: list[dict], merge_fn) -> None:
    index = {item["name"].casefold(): item for item in target}
    for item in items:
        key = item["name"].casefold()
        if key in index:
            merge_fn(index[key], item)
        else:
            index[key] = item
            target.append(item)


def clean(raw: Any) -> dict:
    """Coerce untrusted profile data into a valid profile.

    Unknown categories become "other", unknown ecosystems "any", unknown
    levels "intermediate"; entries without a name are dropped and
    duplicates (case-insensitive) are merged.
    """
    raw = raw if isinstance(raw, dict) else {}
    person = raw.get("person") if isinstance(raw.get("person"), dict) else {}
    profile = empty_profile()
    profile["person"]["role"] = scrub(_str(person.get("role")))
    profile["person"]["interests"] = [x for x in map(scrub, _str_list(person.get("interests"))) if x]

    skills = [s for s in map(_clean_skill, _dicts(raw.get("skills"))) if s]
    _merge_into(profile["skills"], skills, _merge_skill)
    return profile


def merge(base: Any, incoming: Any) -> dict:
    """Combine two profiles without losing anything from `base`.

    Used for /add and for importing a dev-generated YAML: imported data
    adds to what the user typed, it never overwrites it.
    """
    result = copy.deepcopy(clean(base))
    other = clean(incoming)
    if not result["person"]["role"]:
        result["person"]["role"] = other["person"]["role"]
    result["person"]["interests"] = _union(result["person"]["interests"], other["person"]["interests"])
    _merge_into(result["skills"], other["skills"], _merge_skill)
    return result


MAX_IMPORT_CHARS = 200_000


def parse_import(text: str) -> dict:
    """Read a profile YAML produced by prompts/extract_profile.md (milestone 6).

    Accepts it pasted straight from a chat, ``` fences included. Raises
    ValueError with a user-facing message.
    """
    if len(text) > MAX_IMPORT_CHARS:
        raise UserError("import.too_large")
    body = re.sub(r"^\s*```[a-zA-Z]*\s*\n|\n\s*```\s*$", "", text.strip())
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise UserError("import.bad_yaml", problem=str(getattr(exc, "problem", None) or exc)) from exc
    imported = clean(data)
    if not imported["skills"]:
        raise UserError("import.no_skills")
    return imported


def remove_skill(profile: dict, name: str) -> bool:
    key = name.casefold()
    before = len(profile["skills"])
    profile["skills"] = [s for s in profile["skills"] if s["name"].casefold() != key]
    return len(profile["skills"]) < before


def new_skills(profile: dict, candidate: dict) -> list[dict]:
    """Skills in `candidate` that `profile` does not have yet."""
    have = {s["name"].casefold() for s in profile["skills"]}
    return [s for s in candidate["skills"] if s["name"].casefold() not in have]


# ---------------------------------------------------------------- AI steps

def _taxonomy() -> dict[str, str]:
    return {
        "categories": ", ".join(config.categories()),
        "ecosystems": ", ".join(config.ecosystems()),
    }


def build_from_answers(answers: dict[str, str]) -> dict:
    """Turn the four onboarding answers into a clean profile (one AI call)."""
    prompt = ai.render(
        "normalize_profile",
        role=answers.get("role", ""),
        skills=answers.get("skills", ""),
        project=answers.get("project", ""),
        interests=answers.get("interests", ""),
        **_taxonomy(),
    )
    return clean(ai.complete_json(prompt))


def revise(profile: dict, correction: str) -> dict:
    """Apply a free-text correction ("bỏ Docker, thêm Redis") to a draft."""
    prompt = ai.render(
        "revise_profile",
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
        correction=correction,
        **_taxonomy(),
    )
    return clean(ai.complete_json(prompt))


def skills_from_text(text: str) -> dict:
    """Normalise a free-text list of skills into a skills-only profile."""
    parsed = build_from_answers({"skills": text})
    return {**empty_profile(), "skills": parsed["skills"]}


# ---------------------------------------------------------------- display

# Level labels per language; LEVEL_LABEL (top of file) stays the Vietnamese set.
LEVEL_LABELS = {
    "vi": LEVEL_LABEL,
    "en": {"beginner": "beginner", "intermediate": "intermediate", "advanced": "advanced"},
    "zh": {"beginner": "入门", "intermediate": "熟悉", "advanced": "精通"},
    "ja": {"beginner": "入門", "intermediate": "中級", "advanced": "上級"},
    "ko": {"beginner": "입문", "intermediate": "중급", "advanced": "능숙"},
}
_HEADINGS = {
    "role": {"vi": "Công việc", "en": "Role", "zh": "职业", "ja": "仕事", "ko": "직무"},
    "skills": {"vi": "Kỹ năng", "en": "Skills", "zh": "技能", "ja": "スキル", "ko": "스킬"},
    "interests": {"vi": "Muốn theo dõi", "en": "Interested in", "zh": "想关注",
                  "ja": "気になるテーマ", "ko": "관심 주제"},
    "none": {"vi": "(chưa có)", "en": "(none yet)", "zh": "（暂无）", "ja": "（未設定）", "ko": "(아직 없음)"},
}


def _display_lang(lang: str | None) -> str:
    return lang if lang in LEVEL_LABELS else "en"


def format_skill_list(skills: list[dict], lang: str = "vi") -> str:
    """HTML lines grouped by user-facing category label."""
    lang = _display_lang(lang)
    levels = LEVEL_LABELS[lang]
    lines = []
    for category, labels in config.category_labels().items():
        label = labels["vi"] if lang == "vi" else labels["en"]
        group = [s for s in skills if s["category"] == category]
        if group:
            names = ", ".join(
                f"{html.escape(s['name'])} <i>({levels[s['level']]})</i>" for s in group
            )
            lines.append(f"• <b>{html.escape(label)}:</b> {names}")
    return "\n".join(lines)


def format_profile(profile: dict, lang: str = "vi") -> str:
    """Telegram HTML rendering of a profile."""
    lang = _display_lang(lang)
    head = {key: text[lang] for key, text in _HEADINGS.items()}
    person = profile["person"]
    parts = [f"👤 <b>{head['role']}:</b> {html.escape(person['role'] or head['none'])}"]

    parts.append(f"\n🧰 <b>{head['skills']}</b>")
    parts.append(format_skill_list(profile["skills"], lang=lang) or head["none"])

    if person["interests"]:
        parts.append(f"\n🔭 <b>{head['interests']}:</b> {html.escape(', '.join(person['interests']))}")
    return "\n".join(parts)
