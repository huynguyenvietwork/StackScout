"""Deliver the weekly digest (milestone 5): Telegram, email, Slack, Discord
and a generic JSON webhook, each in the reader's language.

Channels are set up on the web page (Notifications tab) and stored in
data/users/<id>/notify.yaml, readable by the owner only. Secrets (bot token,
SMTP password, webhook URLs) are never sent back to the browser: the page
only sees whether they are set and their last 4 characters. Values from
.env still work and fill any field left empty (Docker, admins).

A Telegram bot user gets the digest in their own chat; the web profile gets
it on every channel that is enabled and complete.
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx

from . import render, storage
from .i18n import UserError

log = logging.getLogger(__name__)
CHANNELS = ("telegram", "email", "slack", "discord", "webhook")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SETTINGS_FILE = "notify.yaml"
STATE_FILE = "notify_state.json"
MAX_LOG = 30

# Every field of every channel, with the .env variable that can fill it.
FIELDS: dict[str, dict[str, str]] = {
    "telegram": {"token": "TELEGRAM_BOT_TOKEN", "chat_id": "STACKSCOUT_TELEGRAM_CHAT_ID"},
    "email": {"host": "SMTP_HOST", "port": "SMTP_PORT", "security": "SMTP_SECURITY", "user": "SMTP_USER",
              "password": "SMTP_PASSWORD", "sender": "SMTP_FROM", "to": "STACKSCOUT_EMAIL_TO"},
    "slack": {"url": "STACKSCOUT_SLACK_WEBHOOK_URL"},
    "discord": {"url": "STACKSCOUT_DISCORD_WEBHOOK_URL"},
    "webhook": {"url": "STACKSCOUT_WEBHOOK_URL", "header": "STACKSCOUT_WEBHOOK_HEADER"},
}
REQUIRED = {"telegram": ("token", "chat_id"), "email": ("host", "to"), "slack": ("url",),
            "discord": ("url",), "webhook": ("url",)}
SECRETS = {("telegram", "token"), ("email", "password"), ("slack", "url"), ("discord", "url"),
           ("webhook", "url"), ("webhook", "header")}
SECURITY = ("starttls", "ssl", "none")
FREQUENCIES = ("daily", "weekly", "monthly")
DEFAULT_SCHEDULE = {"enabled": True, "frequency": "weekly", "day": "mon", "monthday": 1, "time": "08:00"}
MAX_SENT_ITEMS = 3000


class NotifyError(RuntimeError):
    pass


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _is_bot_user(user_id) -> bool:
    return str(user_id).lstrip("-").isdigit()


# ---------------------------------------------------------------- settings

def load_settings(user_id) -> dict:
    raw = storage.read_yaml(user_id, SETTINGS_FILE, {}) or {}
    sched = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
    monthday = sched.get("monthday")
    schedule = {
        "enabled": bool(sched.get("enabled", DEFAULT_SCHEDULE["enabled"])),
        "frequency": sched.get("frequency") if sched.get("frequency") in FREQUENCIES else DEFAULT_SCHEDULE["frequency"],
        "day": sched.get("day") if sched.get("day") in DAYS else DEFAULT_SCHEDULE["day"],
        # 1-28: every month has it
        "monthday": monthday if isinstance(monthday, int) and 1 <= monthday <= 28 else DEFAULT_SCHEDULE["monthday"],
        "time": sched.get("time") if isinstance(sched.get("time"), str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", sched["time"])
        else DEFAULT_SCHEDULE["time"],
    }
    channels = {}
    for name, fields in FIELDS.items():
        stored = (raw.get("channels") or {}).get(name)
        stored = stored if isinstance(stored, dict) else {}
        channels[name] = {"enabled": stored.get("enabled"),  # None = never touched
                          **{f: str(stored.get(f) or "").strip() for f in fields}}
    return {"schedule": schedule, "channels": channels}


def _write_settings(user_id, settings: dict) -> None:
    path = storage.write_yaml(user_id, SETTINGS_FILE, settings)
    try:
        os.chmod(path, 0o600)  # secrets inside: owner only
    except OSError:
        pass


def resolve(user_id, channel: str, settings: dict | None = None) -> dict:
    """A channel's effective config: saved values, then .env for empty fields."""
    stored = (settings or load_settings(user_id))["channels"][channel]
    cfg = {f: stored.get(f) or _env(env) for f, env in FIELDS[channel].items()}
    if channel == "telegram" and _is_bot_user(user_id):
        cfg["chat_id"] = str(user_id)  # bot users: their own chat
    complete = all(cfg.get(f) for f in REQUIRED[channel])
    from_env = [f for f, env in FIELDS[channel].items() if not stored.get(f) and _env(env)]
    # Never touched + complete from .env = on; otherwise the switch decides.
    enabled = stored["enabled"] if stored["enabled"] is not None else bool(from_env) and complete
    return {"config": cfg, "complete": complete, "enabled": bool(enabled) and complete, "from_env": from_env}


def configured(user_id) -> list[str]:
    """Channels that will receive this user's digest."""
    if _is_bot_user(user_id):
        return ["telegram"] if _env("TELEGRAM_BOT_TOKEN") else []
    settings = load_settings(user_id)
    return [c for c in CHANNELS if resolve(user_id, c, settings)["enabled"]]


def _hint(value: str) -> str:
    return "••••" + value[-4:] if len(value) > 8 else "••••"


def public_settings(user_id) -> dict:
    """What the page may see: secrets only as set/unset and their last 4 characters."""
    settings = load_settings(user_id)
    channels = {}
    for name, fields in FIELDS.items():
        r = resolve(user_id, name, settings)
        values = {}
        for f in fields:
            v = r["config"].get(f) or ""
            values[f] = {"set": bool(v), "hint": _hint(v)} if (name, f) in SECRETS else v
        stored_enabled = settings["channels"][name]["enabled"]
        channels[name] = {"enabled": r["enabled"], "switch": stored_enabled if stored_enabled is not None else r["enabled"],
                          "complete": r["complete"], "from_env": r["from_env"], "values": values}
    return {"schedule": settings["schedule"], "channels": channels}


def _check_url(channel: str, url: str) -> None:
    if not url:
        return
    if channel == "slack" and not url.startswith("https://hooks.slack.com/"):
        raise UserError("notify.bad_slack")
    if channel == "discord" and not re.match(r"^https://(discord|discordapp)\.com/api/webhooks/", url):
        raise UserError("notify.bad_discord")
    if channel == "webhook" and not re.match(r"^https?://\S+$", url):
        raise UserError("notify.bad_url")


def save_settings(user_id, patch: dict) -> dict:
    """Merge a change from the page. A secret sent as "" keeps the stored one;
    null clears it. Raises ValueError with a readable message."""
    settings = load_settings(user_id)
    sched = patch.get("schedule")
    if isinstance(sched, dict):
        if "enabled" in sched:
            settings["schedule"]["enabled"] = bool(sched["enabled"])
        if "frequency" in sched:
            if sched["frequency"] not in FREQUENCIES:
                raise UserError("notify.bad_value", field="frequency")
            settings["schedule"]["frequency"] = sched["frequency"]
        if "monthday" in sched:
            if not isinstance(sched["monthday"], int) or not 1 <= sched["monthday"] <= 28:
                raise UserError("notify.bad_value", field="monthday")
            settings["schedule"]["monthday"] = sched["monthday"]
        if "day" in sched:
            if sched["day"] not in DAYS:
                raise UserError("notify.bad_value", field="day")
            settings["schedule"]["day"] = sched["day"]
        if "time" in sched:
            if not isinstance(sched["time"], str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", sched["time"]):
                raise UserError("notify.bad_value", field="time")
            settings["schedule"]["time"] = sched["time"]
    for name, change in (patch.get("channels") or {}).items():
        if name not in FIELDS or not isinstance(change, dict):
            continue
        current = settings["channels"][name]
        if "enabled" in change:
            current["enabled"] = bool(change["enabled"])
        for f in FIELDS[name]:
            if f not in change:
                continue
            value = change[f]
            if value is None:
                current[f] = ""
                continue
            value = str(value).strip()[:2000]
            if not value and (name, f) in SECRETS:
                continue  # left empty on the page: keep the stored secret
            if f == "url":
                _check_url(name, value)
            if f == "port" and value and not value.isdigit():
                raise UserError("notify.bad_value", field="port")
            if f == "security" and value and value not in SECURITY:
                raise UserError("notify.bad_value", field="security")
            current[f] = value
    _write_settings(user_id, settings)
    return public_settings(user_id)


# ---------------------------------------------------------------- delivery log

def load_state(user_id) -> dict:
    state = storage.read_json(storage.user_dir(user_id) / STATE_FILE, {}) or {}
    return {"last_period": state.get("last_period") or state.get("last_week"),
            "sent_items": state.get("sent_items") or [], "log": state.get("log") or []}


def record(user_id, kind: str, results: dict[str, str | None], week: str | None = None,
           period: str | None = None, sent_items: list[str] | None = None) -> None:
    """Log a delivery. `period` = the schedule period it covers (once per period);
    `sent_items` = item ids now delivered (a daily digest only sends new ones)."""
    state = load_state(user_id)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["log"] = ([{"at": at, "kind": kind, "channel": c, "ok": e is None, "error": e, "week": week}
                     for c, e in results.items()] + state["log"])[:MAX_LOG]
    if period:
        state["last_period"] = period
    if sent_items:
        state["sent_items"] = (list(dict.fromkeys(sent_items + state["sent_items"])))[:MAX_SENT_ITEMS]
    storage.write_json(storage.user_dir(user_id) / STATE_FILE, state)


# ---------------------------------------------------------------- channels

def _post(client: httpx.Client, url: str, payload: dict, headers: dict | None = None) -> httpx.Response:
    resp = client.post(url, json=payload, headers=headers or {})
    if resp.status_code == 429:  # Discord/Slack rate limit: wait once, as told
        try:
            wait = float(resp.headers.get("retry-after") or resp.json().get("retry_after") or 1)
        except ValueError:
            wait = 1.0
        time.sleep(min(wait, 10))
        resp = client.post(url, json=payload, headers=headers or {})
    return resp


def _telegram_texts(cfg: dict, texts: list[str], client: httpx.Client) -> int:
    if not cfg.get("token"):
        raise NotifyError("Telegram bot token is missing")
    for text in texts:
        resp = client.post(f"https://api.telegram.org/bot{cfg['token']}/sendMessage",
                           json={"chat_id": cfg.get("chat_id"), "text": text, "parse_mode": "HTML",
                                 "disable_web_page_preview": True})
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("ok"):
            raise NotifyError(f"Telegram refused the message: {data.get('description') or resp.status_code}")
    return len(texts)


def _hook(channel: str, cfg: dict, payloads: list[dict], client: httpx.Client) -> int:
    headers = {}
    if channel == "webhook" and cfg.get("header"):
        name, _, value = cfg["header"].partition(":")
        headers = {name.strip(): value.strip()} if value else {"Authorization": cfg["header"]}
    for payload in payloads:
        resp = _post(client, cfg["url"], payload, headers)
        if resp.status_code >= 300:
            raise NotifyError(f"{channel.capitalize()} refused the message: {resp.status_code} {resp.text[:200]}")
    return len(payloads)


def _email(cfg: dict, subject: str, text: str, page: str | None) -> int:
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, cfg["to"]
    msg["From"] = cfg.get("sender") or cfg.get("user") or cfg["to"]
    msg.set_content(text)
    if page:
        msg.add_alternative(page, subtype="html")
    port = int(cfg.get("port") or 587)
    security = (cfg.get("security") or ("ssl" if port == 465 else "starttls")).lower()
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(cfg["host"], port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(cfg["host"], port, timeout=30)
        with server:
            if security == "starttls":
                server.starttls(context=context)
            if cfg.get("user"):
                server.login(cfg["user"], cfg.get("password") or "")
            server.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotifyError(f"Email not sent: {exc}") from exc
    return 1


def _deliver(channel: str, cfg: dict, model: dict, client: httpx.Client) -> int:
    if channel == "telegram":
        return _telegram_texts(cfg, render.telegram(model), client)
    if channel == "email":
        subject, text, page = render.email(model)
        return _email(cfg, subject, text, page)
    if channel == "slack":
        return _hook("slack", cfg, [{"text": t, "unfurl_links": False, "unfurl_media": False}
                                    for t in render.slack(model)], client)
    if channel == "discord":
        # flags 4 = SUPPRESS_EMBEDS: no link preview cards under the digest
        return _hook("discord", cfg, [{"content": t, "flags": 4, "allowed_mentions": {"parse": []}}
                                      for t in render.discord(model)], client)
    return _hook("webhook", cfg, [render.webhook(model)], client)


TEST_TEXT = {
    "vi": "StackScout: kết nối thành công ✅ Bản tin hằng tuần sẽ được gửi tới đây.",
    "en": "StackScout: connected ✅ Your weekly digest will arrive here.",
    "zh": "StackScout：连接成功 ✅ 每周简报将发送到这里。",
    "ja": "StackScout：接続しました ✅ 毎週のダイジェストがここに届きます。",
    "ko": "StackScout: 연결되었습니다 ✅ 주간 다이제스트가 여기로 전송됩니다.",
}


def send_test(user_id, channel: str, lang: str = "en", client: httpx.Client | None = None) -> None:
    """A short message on one channel, with the saved settings. Raises NotifyError."""
    r = resolve(user_id, channel)
    if not r["complete"]:
        raise UserError("notify.need_fields")
    text = TEST_TEXT.get(lang, TEST_TEXT["en"])
    own = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        cfg = r["config"]
        if channel == "telegram":
            _telegram_texts(cfg, [text], client)
        elif channel == "email":
            _email(cfg, "StackScout ✅", text, None)
        elif channel == "slack":
            _hook("slack", cfg, [{"text": text}], client)
        elif channel == "discord":
            _hook("discord", cfg, [{"content": text}], client)
        else:
            _hook("webhook", cfg, [{"source": "stackscout", "test": True, "text": text}], client)
    except httpx.HTTPError as exc:
        raise NotifyError(f"Could not reach {channel}: {exc}") from exc
    finally:
        if own:
            client.close()


def telegram_chats(token: str, client: httpx.Client | None = None) -> list[dict]:
    """Chats that recently wrote to the bot (after pressing Start), to pick a chat id."""
    own = client is None
    client = client or httpx.Client(timeout=20.0)
    try:
        resp = client.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 100})
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NotifyError(f"Could not reach Telegram: {exc}") from exc
    finally:
        if own:
            client.close()
    if not data.get("ok"):
        raise NotifyError(f"Telegram: {data.get('description') or resp.status_code}")
    chats: dict[str, dict] = {}
    for update in data.get("result") or []:
        for key in ("message", "channel_post", "my_chat_member", "edited_message"):
            chat = (update.get(key) or {}).get("chat")
            if chat:
                name = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) \
                    or chat.get("username") or str(chat["id"])
                chats[str(chat["id"])] = {"id": str(chat["id"]), "name": name, "type": chat.get("type", "")}
    return list(chats.values())


# ---------------------------------------------------------------- one digest, every channel

def chat_for(user_id) -> str | None:
    """Telegram users are their own chat; the web user's chat comes from its settings or .env."""
    if _is_bot_user(user_id):
        return str(user_id)
    return resolve(user_id, "telegram")["config"].get("chat_id") or None


def send_digest(user_id, report: dict, *, comparisons: dict | None = None, market: dict | None = None,
                lang: str | None = None, client: httpx.Client | None = None,
                channels: list[str] | None = None, period: str | None = None,
                when: datetime | None = None) -> dict[str, str | None]:
    """Send a report on every enabled channel. Returns {channel: error or None};
    one failing channel never stops the others. `period` (daily/weekly/monthly)
    + `when` name the digest ("Ngày 19/11/2026", "Tháng 11/2026")."""
    model = render.build(report, comparisons, market, lang, period=period, when=when)
    settings = load_settings(user_id)
    targets = channels if channels is not None else configured(user_id)
    own = client is None
    client = client or httpx.Client(timeout=30.0)
    results: dict[str, str | None] = {}
    try:
        for channel in targets:
            try:
                _deliver(channel, resolve(user_id, channel, settings)["config"], model, client)
                results[channel] = None
            except (NotifyError, httpx.HTTPError, KeyError) as exc:
                log.error("[%s] %s failed: %s", user_id, channel, exc)
                results[channel] = str(exc)
    finally:
        if own:
            client.close()
    return results


def send_report(report: dict, chat_id: str, *, token: str | None = None, client: httpx.Client | None = None,
                comparisons: dict | None = None, lang: str | None = None) -> int:
    """Telegram only (the bot's /radar): returns the number of messages sent."""
    own = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        cfg = {"token": token or _env("TELEGRAM_BOT_TOKEN"), "chat_id": chat_id}
        return _telegram_texts(cfg, render.telegram(render.build(report, comparisons, None, lang)), client)
    finally:
        if own:
            client.close()
