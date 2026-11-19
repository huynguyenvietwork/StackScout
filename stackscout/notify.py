"""Deliver the weekly digest (milestone 5): Telegram, email, Slack, Discord
and a generic JSON webhook, each in the reader's language.

Channels are configured in .env (see .env.example), never through the web
page, so no secret travels through the browser. A Telegram bot user gets the
digest in their own chat; the web profile gets it on every configured channel.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
import time
from email.message import EmailMessage

import httpx

from . import render

log = logging.getLogger(__name__)
CHANNELS = ("telegram", "email", "slack", "discord", "webhook")


class NotifyError(RuntimeError):
    pass


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def chat_for(user_id) -> str | None:
    """Telegram users are their own chat; the web user needs STACKSCOUT_TELEGRAM_CHAT_ID."""
    uid = str(user_id)
    if uid.lstrip("-").isdigit():
        return uid
    return _env("STACKSCOUT_TELEGRAM_CHAT_ID") or None


def configured(user_id) -> list[str]:
    """Channels that will receive this user's digest."""
    if str(user_id).lstrip("-").isdigit():  # a Telegram bot user
        return ["telegram"] if _env("TELEGRAM_BOT_TOKEN") else []
    found = []
    if _env("TELEGRAM_BOT_TOKEN") and chat_for(user_id):
        found.append("telegram")
    if _env("SMTP_HOST") and _env("STACKSCOUT_EMAIL_TO"):
        found.append("email")
    if _env("STACKSCOUT_SLACK_WEBHOOK_URL"):
        found.append("slack")
    if _env("STACKSCOUT_DISCORD_WEBHOOK_URL"):
        found.append("discord")
    if _env("STACKSCOUT_WEBHOOK_URL"):
        found.append("webhook")
    return found


# ---------------------------------------------------------------- channels

def _post(client: httpx.Client, url: str, payload: dict) -> httpx.Response:
    resp = client.post(url, json=payload)
    if resp.status_code == 429:  # Discord/Slack rate limit: wait once, as told
        try:
            wait = float(resp.headers.get("retry-after") or resp.json().get("retry_after") or 1)
        except ValueError:
            wait = 1.0
        time.sleep(min(wait, 10))
        resp = client.post(url, json=payload)
    return resp


def send_telegram(model: dict, chat_id: str, client: httpx.Client, token: str | None = None) -> int:
    token = token or _env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise NotifyError("TELEGRAM_BOT_TOKEN is not set in .env")
    sent = 0
    for text in render.telegram(model):
        resp = client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                           json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                 "disable_web_page_preview": True})
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not data.get("ok"):
            raise NotifyError(f"Telegram refused the message: {data.get('description') or resp.status_code}")
        sent += 1
    return sent


def send_slack(model: dict, url: str, client: httpx.Client) -> int:
    messages = render.slack(model)
    for text in messages:
        resp = _post(client, url, {"text": text, "unfurl_links": False, "unfurl_media": False})
        if resp.status_code >= 300:
            raise NotifyError(f"Slack refused the message: {resp.status_code} {resp.text[:200]}")
    return len(messages)


def send_discord(model: dict, url: str, client: httpx.Client) -> int:
    messages = render.discord(model)
    for text in messages:
        # flags 4 = SUPPRESS_EMBEDS: no link preview cards under the digest
        resp = _post(client, url, {"content": text, "flags": 4, "allowed_mentions": {"parse": []}})
        if resp.status_code >= 300:
            raise NotifyError(f"Discord refused the message: {resp.status_code} {resp.text[:200]}")
    return len(messages)


def send_webhook(model: dict, url: str, client: httpx.Client) -> int:
    resp = _post(client, url, render.webhook(model))
    if resp.status_code >= 300:
        raise NotifyError(f"Webhook refused the digest: {resp.status_code} {resp.text[:200]}")
    return 1


def send_email(model: dict, to: str) -> int:
    subject, text, page = render.email(model)
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = _env("SMTP_FROM") or _env("SMTP_USER")
    msg.set_content(text)
    msg.add_alternative(page, subtype="html")
    host, user, password = _env("SMTP_HOST"), _env("SMTP_USER"), _env("SMTP_PASSWORD")
    port = int(_env("SMTP_PORT") or 587)
    security = (_env("SMTP_SECURITY") or ("ssl" if port == 465 else "starttls")).lower()
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            if security == "starttls":
                server.starttls(context=context)
            if user:
                server.login(user, password)
            server.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotifyError(f"Email not sent: {exc}") from exc
    return 1


# ---------------------------------------------------------------- one digest, every channel

def send_digest(user_id, report: dict, *, comparisons: dict | None = None, market: dict | None = None,
                lang: str | None = None, client: httpx.Client | None = None,
                channels: list[str] | None = None) -> dict[str, str | None]:
    """Send a report on every configured channel. Returns {channel: error or None};
    one failing channel never stops the others."""
    model = render.build(report, comparisons, market, lang)
    targets = channels if channels is not None else configured(user_id)
    own = client is None
    client = client or httpx.Client(timeout=30.0)
    senders = {
        "telegram": lambda: send_telegram(model, chat_for(user_id) or "", client),
        "email": lambda: send_email(model, _env("STACKSCOUT_EMAIL_TO")),
        "slack": lambda: send_slack(model, _env("STACKSCOUT_SLACK_WEBHOOK_URL"), client),
        "discord": lambda: send_discord(model, _env("STACKSCOUT_DISCORD_WEBHOOK_URL"), client),
        "webhook": lambda: send_webhook(model, _env("STACKSCOUT_WEBHOOK_URL"), client),
    }
    results: dict[str, str | None] = {}
    try:
        for channel in targets:
            try:
                senders[channel]()
                results[channel] = None
            except (NotifyError, httpx.HTTPError) as exc:
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
        return send_telegram(render.build(report, comparisons, None, lang), chat_id, client, token)
    finally:
        if own:
            client.close()
