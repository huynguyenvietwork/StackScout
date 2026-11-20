"""`main.py doctor` checks this machine can run StackScout and says how to fix
what is missing; `main.py setup` creates .env and asks for the API key in the
terminal (hidden input), so the key never goes through a chat with an AI
assistant.
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
import socket
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import ai, config, notify, storage

ENV_FILE = config.ROOT / ".env"
ENV_EXAMPLE = config.ROOT / ".env.example"
WEB_USER = "web"
PORT = 8000
ICONS = {"ok": "✅", "warn": "⚠️ ", "fail": "❌", "info": "•"}


@dataclass
class Check:
    status: str  # ok | warn | fail | info
    name: str
    detail: str
    fix: str = ""


def in_docker() -> bool:
    return os.environ.get("STACKSCOUT_IN_DOCKER") == "1" or Path("/.dockerenv").exists()


# ---------------------------------------------------------------- checks

def check_python() -> Check:
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= (3, 11):
        return Check("ok", "Python", version)
    return Check("fail", "Python", f"{version} is too old", "install Python 3.11+ (uv does it: `uv python install 3.12`)")


def check_env_file(path: Path = ENV_FILE) -> Check:
    if in_docker():
        return Check("ok", "Settings", "from the container environment (.env on the host)")
    if not path.exists():
        if ai.backend() == "cli":  # the claude CLI needs no settings at all
            return Check("info", "Settings", "no .env file (not needed with the claude CLI)",
                         "for an API key or notification defaults: `uv run main.py setup`")
        return Check("warn", "Settings", "no .env file",
                     "run `uv run main.py setup` (or `cp .env.example .env` and edit it)")
    if os.name == "posix" and path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        return Check("warn", "Settings", ".env is readable by other users", f"chmod 600 {path.name}")
    return Check("ok", "Settings", ".env (owner-only)")


def check_ai(online: bool = False) -> Check:
    if ai.backend() == "api":
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            fix = ("pass it to the container: `docker run … -e ANTHROPIC_API_KEY …` with the key exported "
                   "in your shell, or ANTHROPIC_API_KEY=… in .env for docker compose") if in_docker() else \
                "run `uv run main.py setup` in your own terminal, or put the key in .env yourself"
            return Check("fail", "AI backend", "Anthropic API selected but ANTHROPIC_API_KEY is empty", fix)
        model = os.environ.get("STACKSCOUT_MODEL") or ai.DEFAULT_MODEL
        if not key.startswith("sk-ant-"):
            return Check("warn", "AI backend", "ANTHROPIC_API_KEY does not look like an Anthropic key (sk-ant-…)",
                         "copy the key again from https://platform.claude.com/settings/keys")
        if online:
            problem = _api_online_problem(model)
            if problem:
                return Check("fail", "AI backend", problem, "check the key, its workspace and billing")
            return Check("ok", "AI backend", f"Anthropic API, {model}: key accepted")
        return Check("ok", "AI backend", f"Anthropic API, {model} (add --online to test the key)")

    cmd = ai._command("")[0]
    path = shutil.which(cmd)
    if not path:
        if in_docker():
            return Check("fail", "AI backend", "no ANTHROPIC_API_KEY (the claude CLI is not in the image)",
                         "set ANTHROPIC_API_KEY in .env on the host, then `docker compose up -d` again")
        return Check("fail", "AI backend", f"no ANTHROPIC_API_KEY and no `{cmd}` CLI found",
                     "either run `uv run main.py setup` to add an Anthropic API key, "
                     "or install Claude Code (https://code.claude.com) and log in")
    if online:
        try:
            ai.complete("Reply with the single word OK.", timeout=120)
        except ai.AIError as exc:
            return Check("fail", "AI backend", f"`{cmd}` did not answer: {exc}",
                         f"run `{cmd}` once in a terminal and log in")
        return Check("ok", "AI backend", f"{cmd} CLI answered ({path})")
    return Check("ok", "AI backend", f"{cmd} CLI at {path} (it must be logged in; --online tests it)")


def _api_online_problem(model: str) -> str | None:
    """A free call that proves the key works and can use the model. None = fine."""
    import anthropic

    try:
        anthropic.Anthropic(timeout=20.0, max_retries=1).models.retrieve(model)
    except anthropic.AuthenticationError:
        return "the API key was rejected"
    except anthropic.PermissionDeniedError:
        return f"this key cannot use {model}"
    except anthropic.NotFoundError:
        return f"model {model} not found for this key (set STACKSCOUT_MODEL)"
    except anthropic.APIConnectionError:
        return "cannot reach api.anthropic.com (network or proxy)"
    except anthropic.APIStatusError as exc:
        return f"Anthropic API error {exc.status_code}"
    return None


def check_storage() -> Check:
    for folder in (config.data_dir(), config.reports_dir()):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder):
                pass
        except OSError as exc:
            fix = ("use the named volumes from docker-compose.yml" if in_docker()
                   else f"make {folder} writable for this user")
            return Check("fail", "Storage", f"cannot write to {folder}: {exc.strerror or exc}", fix)
    return Check("ok", "Storage", f"{config.data_dir()} and {config.reports_dir()} are writable")


def check_port(port: int = PORT) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return Check("warn", "Port", f"{port} is in use (StackScout already running?)",
                         f"open http://127.0.0.1:{port}, or start on another port: `uv run main.py web --port {port + 1}`")
    return Check("ok", "Port", f"{port} is free")


def check_profile() -> Check:
    profile = storage.load_profile(WEB_USER)
    if not profile or not profile.get("skills"):
        return Check("info", "Profile", "none yet", "open the web UI and describe your stack (about 2 minutes)")
    return Check("ok", "Profile", f"{len(profile['skills'])} skills")


def check_notifications() -> Check:
    channels = notify.configured(WEB_USER)
    if not channels:
        return Check("info", "Notifications", "no channel yet (optional)", "Notifications tab in the web UI")
    return Check("ok", "Notifications", ", ".join(channels))


def run_checks(online: bool = False) -> list[Check]:
    checks = [check_python(), check_env_file(), check_ai(online), check_storage()]
    if not in_docker():
        checks.append(check_port())
    for optional in (check_profile, check_notifications):
        try:
            checks.append(optional())
        except Exception as exc:  # noqa: BLE001 - optional checks never break the report
            checks.append(Check("warn", optional.__name__.removeprefix("check_").title(), f"could not read: {exc}"))
    return checks


def report(checks: list[Check], out=sys.stdout) -> int:
    print("StackScout doctor", file=out)
    for c in checks:
        print(f"  {ICONS[c.status]} {c.name}: {c.detail}", file=out)
        if c.fix and c.status != "ok":
            print(f"     → {c.fix}", file=out)
    failed = sum(c.status == "fail" for c in checks)
    if failed:
        print(f"\n{failed} problem(s) to fix, then run `main.py doctor` again.", file=out)
        return 1
    port_busy = any(c.name == "Port" and c.status != "ok" for c in checks)
    port = PORT + 1 if port_busy else PORT
    if in_docker():
        start = "docker compose up -d"
    else:
        start = "uv run main.py web" + (f" --port {port}" if port_busy else "")
    print(f"\nReady. Start with `{start}`, then open http://127.0.0.1:{port}", file=out)
    return 0


def doctor(online: bool = False) -> int:
    return report(run_checks(online))


# ---------------------------------------------------------------- setup

def set_env(path: Path, key: str, value: str) -> None:
    """Set KEY=value in a .env file: replaces the first `KEY=` or `# KEY=` line, else appends."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def setup(env_file: Path = ENV_FILE) -> int:
    if in_docker():
        print("Inside Docker: put ANTHROPIC_API_KEY in .env on the host instead.")
        return 1
    if not sys.stdin.isatty():
        print("`setup` asks for your API key with hidden input, so it needs a real terminal.\n"
              f"Run `uv run main.py setup` in your own terminal, or open {env_file} and set ANTHROPIC_API_KEY=...")
        return 1
    if not env_file.exists():
        env_file.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Created {env_file.name} from {ENV_EXAMPLE.name}")
    if os.name == "posix":
        env_file.chmod(0o600)

    use_cli = False
    if shutil.which("claude"):
        answer = input("AI backend: [1] Anthropic API key  [2] Claude Code CLI already logged in  (1/2) [2]: ")
        use_cli = answer.strip() != "1"
    if use_cli:
        set_env(env_file, "STACKSCOUT_AI_BACKEND", "cli")
        os.environ["STACKSCOUT_AI_BACKEND"] = "cli"
        print("Using the Claude Code CLI.")
    else:
        print("Create a key at https://platform.claude.com/settings/keys")
        key = getpass.getpass("Anthropic API key (hidden, Enter to skip): ").strip()
        if key:
            set_env(env_file, "ANTHROPIC_API_KEY", key)
            set_env(env_file, "STACKSCOUT_AI_BACKEND", "api")
            os.environ["ANTHROPIC_API_KEY"] = key
            os.environ["STACKSCOUT_AI_BACKEND"] = "api"
            print(f"Saved to {env_file.name} (owner-only).")
    print()
    return doctor(online=not use_cli)
