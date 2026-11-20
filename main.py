"""StackScout entry point.

    uv run main.py web      # local web UI on http://127.0.0.1:8000
    uv run main.py bot      # run the Telegram bot (long polling)
    uv run main.py digest   # build and send this week's digest (milestones 3-5)
    uv run main.py schedule # send digests on schedule without the web UI
    uv run main.py setup    # create .env, ask for the API key (hidden), then check
    uv run main.py doctor   # check this machine can run StackScout
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
    if os.environ.get("STACKSCOUT_SCHEDULER", "on").lower() != "off":
        from stackscout import scheduler

        scheduler.start_background()  # weekly digests, as set in the Notifications tab
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
    return 0


def run_digest(user: str | None, send: bool) -> int:
    """Build every profile's radar now and send it on its channels (ignores the schedule)."""
    from stackscout import notify, scheduler, storage

    users = [user] if user else storage.list_users()
    if not users:
        print("No profiles yet: create one with `main.py web` or the bot first.", file=sys.stderr)
        return 1
    failed = 0
    for uid in users:
        if send and not notify.configured(uid):
            logging.warning("[%s] no notification channel: building the radar only", uid)
        try:
            results = scheduler.deliver(uid, send=send and bool(notify.configured(uid)))
        except Exception:  # noqa: BLE001 - one user must not stop the others
            logging.exception("[%s] radar failed", uid)
            failed += 1
            continue
        for channel, error in results.items():
            if error:
                failed += 1
            else:
                logging.info("[%s] digest sent on %s", uid, channel)
    return 1 if failed else 0


def run_schedule() -> int:
    """Stay running and send each digest at the time set in the Notifications tab."""
    from stackscout import scheduler

    scheduler.loop()
    return 0


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
    sub.add_parser("schedule", help="stay running and send each digest on its schedule (without the web UI)")
    sub.add_parser("setup", help="create .env and enter the API key in the terminal (hidden), then check")
    doc = sub.add_parser("doctor", help="check this machine can run StackScout, and how to fix what is missing")
    doc.add_argument("--online", action="store_true", help="also test the API key or the CLI (free for an API key)")
    args = parser.parse_args()

    if args.command in ("setup", "doctor"):
        logging.getLogger().setLevel(logging.WARNING)  # keep the checklist readable
        from stackscout import doctor

        return doctor.setup() if args.command == "setup" else doctor.doctor(online=args.online)
    if args.command == "bot":
        return run_bot()
    if args.command == "web":
        return run_web(args.host, args.port)
    if args.command == "schedule":
        return run_schedule()
    return run_digest(args.user, send=not args.no_send)


if __name__ == "__main__":
    sys.exit(main())
