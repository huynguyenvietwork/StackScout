"""One function for every AI step: `complete(prompt, tools=...)`.

Two backends:
  - "api": the Anthropic API with an API key (ANTHROPIC_API_KEY). Web search
    and fetch run server-side. Picked automatically when a key is set.
  - "cli": a headless AI CLI (default `claude -p`, already logged in). The
    prompt goes in on stdin, text comes back on stdout; any CLI that behaves
    that way can be plugged in through STACKSCOUT_AI_CMD.
STACKSCOUT_AI_BACKEND=api|cli forces one.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import tempfile
import threading
from pathlib import Path

from .config import PROMPTS_DIR

log = logging.getLogger(__name__)

DEFAULT_CMD = "claude -p --safe-mode --no-session-persistence"
DEFAULT_TIMEOUT = 240
DEFAULT_MODEL = "claude-opus-5-5"
MAX_CONTINUATIONS = 5  # server-side tool loops that pause (pause_turn) and resume
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 10},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 10},
]


class AIError(RuntimeError):
    """The AI CLI failed or returned something we could not use."""


# Running totals for the API backend since the process started (logged per call),
# so the cost of a radar run can be read from the server log.
USAGE = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "web_searches": 0}
_usage_lock = threading.Lock()


def _count(value) -> int:
    return value if isinstance(value, int) else 0


def _record_usage(response) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    tokens_in = _count(getattr(usage, "input_tokens", 0)) + _count(getattr(usage, "cache_read_input_tokens", 0)) \
        + _count(getattr(usage, "cache_creation_input_tokens", 0))
    tokens_out = _count(getattr(usage, "output_tokens", 0))
    searches = _count(getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0))
    with _usage_lock:
        USAGE["calls"] += 1
        USAGE["input_tokens"] += tokens_in
        USAGE["output_tokens"] += tokens_out
        USAGE["web_searches"] += searches
        totals = dict(USAGE)
    log.info("api usage: in=%d out=%d searches=%d | total calls=%d in=%d out=%d searches=%d",
             tokens_in, tokens_out, searches, totals["calls"], totals["input_tokens"],
             totals["output_tokens"], totals["web_searches"])


def render(name: str, **values: str) -> str:
    """Load prompts/<name>.md and fill its {{placeholders}}."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)))
    if missing:
        raise ValueError(f"prompt {name!r} is missing values for: {', '.join(missing)}")
    return text


def _command(tools: str) -> list[str]:
    cmd = shlex.split(os.environ.get("STACKSCOUT_AI_CMD") or DEFAULT_CMD)
    if not cmd:
        raise AIError("STACKSCOUT_AI_CMD is empty")
    # Only the Claude CLI knows --tools; other CLIs get the command as configured.
    if Path(cmd[0]).name == "claude" and "--tools" not in cmd:
        cmd += ["--tools", tools]
        if tools:
            # Print mode cannot ask for permission, so pre-approve exactly
            # the tools this step is allowed to use.
            cmd += ["--allowedTools", *tools.split(",")]
    return cmd


def backend() -> str:
    forced = (os.environ.get("STACKSCOUT_AI_BACKEND") or "").strip().lower()
    if forced in ("api", "cli"):
        return forced
    return "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"


def complete(prompt: str, *, tools: str = "", timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run one prompt and return the raw text answer.

    `tools`: "" (default) means no tools at all, which is what every step that
    only transforms text should use; "WebSearch,WebFetch" allows the web.
    """
    if backend() == "api":
        return _complete_api(prompt, tools=tools, timeout=timeout)
    return _complete_cli(prompt, tools=tools, timeout=timeout)


def _complete_api(prompt: str, *, tools: str, timeout: int) -> str:
    import anthropic  # only needed for this backend

    client = anthropic.Anthropic(timeout=float(timeout), max_retries=2)
    params: dict = {
        "model": os.environ.get("STACKSCOUT_MODEL") or DEFAULT_MODEL,
        "max_tokens": 16000,
        "output_config": {"effort": os.environ.get("STACKSCOUT_EFFORT") or "medium"},
        # A safety decline on one model is retried on a fallback model in the same call.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }
    if "WebSearch" in tools or "WebFetch" in tools:
        params["tools"] = WEB_TOOLS
    messages: list = [{"role": "user", "content": prompt}]
    try:
        response = client.beta.messages.create(messages=messages, **params)
        _record_usage(response)
        for _ in range(MAX_CONTINUATIONS):
            if response.stop_reason != "pause_turn":
                break
            # The server-side search loop paused: send the turn back and it resumes.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
            response = client.beta.messages.create(messages=messages, **params)
            _record_usage(response)
    except anthropic.AuthenticationError as exc:
        raise AIError("Anthropic API key rejected (check ANTHROPIC_API_KEY)") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError(f"cannot reach the Anthropic API: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise AIError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    if response.stop_reason == "refusal":
        raise AIError("the model declined this request")
    if response.stop_reason == "pause_turn":
        raise AIError("web research did not finish")
    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise AIError(f"empty answer from the API (stop_reason={response.stop_reason})")
    return text


def _complete_cli(prompt: str, *, tools: str, timeout: int) -> str:
    cmd = _command(tools)
    # An empty scratch cwd keeps the CLI away from this repo and user data.
    with tempfile.TemporaryDirectory(prefix="stackscout-") as cwd:
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd
            )
        except FileNotFoundError as exc:
            raise AIError(f"AI CLI not found: {cmd[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AIError(f"AI CLI timed out after {timeout}s") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[:500]
        raise AIError(f"AI CLI exited with {proc.returncode}: {detail}")
    return proc.stdout


def parse_json(text: str) -> dict:
    """Pull the JSON object out of a model answer (bare or inside a ``` fence)."""
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        candidate = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            raise AIError(f"no JSON object in AI answer: {text.strip()[:200]!r}")
        candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AIError(f"AI answer is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIError("AI answer is JSON but not an object")
    return data


def complete_json(prompt: str, *, tools: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
    return parse_json(complete(prompt, tools=tools, timeout=timeout))
