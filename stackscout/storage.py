"""Per-user files under data/users/<telegram_user_id>/."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import yaml

from . import config
from .profile import clean


_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def user_dir(user_id: int | str) -> Path:
    """Telegram users are keyed by their numeric id, the web UI by a name."""
    key = str(user_id)
    if not _USER_ID.match(key):
        raise ValueError(f"invalid user id: {key!r}")
    return config.data_dir() / "users" / key


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_profile(user_id: int | str) -> dict | None:
    path = user_dir(user_id) / "profile.yaml"
    if not path.exists():
        return None
    return clean(yaml.safe_load(path.read_text(encoding="utf-8")))


def save_profile(user_id: int | str, profile: dict) -> Path:
    path = user_dir(user_id) / "profile.yaml"
    text = yaml.safe_dump(clean(profile), allow_unicode=True, sort_keys=False, width=100)
    _write_atomic(path, text)
    return path


def load_settings(user_id: int | str) -> dict:
    data = read_yaml(user_id, "settings.yaml", {}) or {}
    language = data.get("language")
    return {"language": language if language in config.LANGUAGES else config.DEFAULT_LANGUAGE}


def language_chosen(user_id: int | str) -> bool:
    """Whether the person has picked a language (else the default is a guess)."""
    data = read_yaml(user_id, "settings.yaml", {}) or {}
    return data.get("language") in config.LANGUAGES


def save_settings(user_id: int | str, settings: dict) -> dict:
    clean_settings = load_settings(user_id)
    if settings.get("language") in config.LANGUAGES:
        clean_settings["language"] = settings["language"]
    write_yaml(user_id, "settings.yaml", clean_settings)
    return clean_settings


def output_language(user_id: int | str) -> str:
    """The language name AI-written text should use for this user."""
    return config.LANGUAGES[load_settings(user_id)["language"]]


def list_users() -> list[str]:
    """Every user that has a saved profile."""
    root = config.data_dir() / "users"
    if not root.is_dir():
        return []
    return sorted(p.parent.name for p in root.glob("*/profile.yaml") if _USER_ID.match(p.parent.name))


def read_yaml(user_id: int | str, name: str, default=None):
    path = user_dir(user_id) / name
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(user_id: int | str, name: str, data) -> Path:
    path = user_dir(user_id) / name
    _write_atomic(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100))
    return path


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> Path:
    _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1))
    return path


def reports_dir(user_id: int | str) -> Path:
    return config.reports_dir() / str(user_dir(user_id).name)
