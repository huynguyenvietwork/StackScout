"""Paths and the fixed taxonomy loaded from config/."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"

LEVELS = ("beginner", "intermediate", "advanced")

# UI + AI output languages: code -> name the model is asked to write in.
LANGUAGES = {
    "vi": "Vietnamese",
    "en": "English",
    "zh": "Simplified Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}
DEFAULT_LANGUAGE = "en"  # until the person picks one (the web page proposes the browser's)


def data_dir() -> Path:
    return Path(os.environ.get("STACKSCOUT_DATA_DIR") or ROOT / "data")


def reports_dir() -> Path:
    return Path(os.environ.get("STACKSCOUT_REPORTS_DIR") or ROOT / "reports")


@lru_cache
def _categories_file() -> dict:
    return yaml.safe_load((CONFIG_DIR / "categories.yaml").read_text(encoding="utf-8"))


@lru_cache
def categories() -> dict[str, str]:
    """Category id -> Vietnamese label (bot, Telegram), in display order."""
    return {c["id"]: c["label"] for c in _categories_file()["categories"]}


@lru_cache
def category_labels() -> dict[str, dict[str, str]]:
    """Category id -> {"vi": ..., "en": ...} for the web UI."""
    return {c["id"]: {"vi": c["label"], "en": c.get("label_en", c["id"])} for c in _categories_file()["categories"]}


@lru_cache
def ecosystems() -> tuple[str, ...]:
    return tuple(_categories_file()["ecosystems"])


@lru_cache
def _industries_file() -> dict:
    return yaml.safe_load((CONFIG_DIR / "industries.yaml").read_text(encoding="utf-8"))


def industries() -> dict:
    return _industries_file()["industries"]


def catalog_version() -> int:
    return int(_industries_file().get("catalog_version", 1))
