"""StackScout entry point.

    uv run main.py web      # local web UI on http://127.0.0.1:8000
    uv run main.py bot      # run the Telegram bot (long polling)
    uv run main.py digest   # build and send this week's digest (milestones 3-5)
    uv run main.py schedule # stay running and send the digest every week (Docker)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv


def run_bot() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set (copy .env.example to .env).", file=sys.stderr)
        return 1
    from stackscout.bot import build_application

    if not os.environ.get("STACKSCOUT_ALLOWED_USERS"):
        logging.warning("STACKSCOUT_ALLOWED_USERS is empty: anyone who finds the bot can use it")
    build_application(token).run_polling()
    return 0


def run_web(host: str, port: int) -> int:
    import uvicorn

    from stackscout.web import create_app

    print(f"StackScout web: http://{host}:{port}", flush=True)
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
    return 0


def run_digest(user: str | None, send: bool) -> int:
    """Weekly job (cron): build every user's radar, then send it on every configured channel."""
    from stackscout import digest, notify, storage

    users = [user] if user else storage.list_users()
    if not users:
        print("No profiles yet: create one with `main.py web` or the bot first.", file=sys.stderr)
        return 1
    failed = 0
    for uid in users:
        try:
            report = digest.run_radar(uid, progress=lambda m, u=uid: logging.info("[%s] %s", u, m))
        except Exception:  # noqa: BLE001 - one user must not stop the others
            logging.exception("[%s] radar failed", uid)
            failed += 1
            continue
        logging.info("[%s] %s ready: %s", uid, report["week"], report["stats"])
        # Same comparisons as the web "So với stack" tab, so the digest can show the verdicts.
        try:
            done = digest.compare_all(uid, report["week"])
            logging.info("[%s] compared %d technologies with the stack (%d failed)", uid, done["total"], done["failed"])
        except Exception:  # noqa: BLE001 - the digest still goes out without verdicts
            logging.exception("[%s] comparisons failed", uid)
        if not send:
            continue
        if not notify.configured(uid):
            logging.warning("[%s] not sent: no notification channel configured (see .env.example)", uid)
            continue
        week = report["week"]
        results = notify.send_digest(uid, report, comparisons=digest.cached_comparisons(uid, week),
                                     market=digest.cached_market(uid, week), lang=storage.load_settings(uid)["language"])
        for channel, error in results.items():
            if error:
                failed += 1
            else:
                logging.info("[%s] digest sent on %s", uid, channel)
    return 1 if failed else 0


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def next_run(now, day: str, at: str):
    """The next datetime (in now's timezone) on weekday `day` at "HH:MM"."""
    from datetime import timedelta

    hour, minute = (int(x) for x in at.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    target += timedelta(days=(DAYS.index(day) - now.weekday()) % 7)
    return target if target > now else target + timedelta(days=7)


def run_schedule(day: str, at: str) -> int:
    """Stay running and send the digest every week: for Docker, where there is no cron."""
    import time
    from datetime import datetime

    while True:
        now = datetime.now().astimezone()
        when = next_run(now, day, at)
        logging.info("next digest: %s", when.isoformat(timespec="minutes"))
        time.sleep(max(1.0, (when - now).total_seconds()))
        run_digest(None, send=True)


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="stackscout", description="New tech, matched to your stack.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bot", help="run the Telegram bot")
    web = sub.add_parser("web", help="run the local web UI")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    dg = sub.add_parser("digest", help="build and send the weekly digest (run it from cron)")
    dg.add_argument("--user", help="only this user id (default: every profile)")
    dg.add_argument("--no-send", action="store_true", help="build the reports without sending them")
    sc = sub.add_parser("schedule", help="stay running and send the digest every week (for Docker)")
    sc.add_argument("--day", choices=DAYS, default=os.environ.get("STACKSCOUT_DIGEST_DAY", "mon"))
    sc.add_argument("--at", default=os.environ.get("STACKSCOUT_DIGEST_TIME", "08:00"), help="local time, HH:MM")
    args = parser.parse_args()

    if args.command == "bot":
        return run_bot()
    if args.command == "web":
        return run_web(args.host, args.port)
    if args.command == "schedule":
        return run_schedule(args.day, args.at)
    return run_digest(args.user, send=not args.no_send)


if __name__ == "__main__":
    sys.exit(main())
