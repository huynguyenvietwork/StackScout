"""Weekly delivery without cron: run the radar and send the digest when each
person's slot (Notifications tab: day + time, server local time) has passed
this week, once per week.

The web server runs `loop()` in a background thread; `main.py schedule` runs
it alone (Docker, or a machine without the web UI).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from . import collect, digest, notify, storage

log = logging.getLogger(__name__)
TICK_SECONDS = 60
_lock = threading.Lock()


def _slot(now: datetime, day: str, at: str) -> datetime:
    """This week's delivery time (the week starts on Monday)."""
    hour, minute = (int(x) for x in at.split(":"))
    monday = (now - timedelta(days=now.weekday())).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return monday + timedelta(days=notify.DAYS.index(day))


def next_run(now: datetime, day: str, at: str) -> datetime:
    """The next slot strictly after `now`."""
    slot = _slot(now, day, at)
    return slot if slot > now else slot + timedelta(days=7)


def next_delivery(user_id, now: datetime | None = None) -> datetime | None:
    """When this person's next digest goes out, or None if it won't."""
    now = now or datetime.now().astimezone()
    sched = notify.load_settings(user_id)["schedule"]
    if not sched["enabled"] or not notify.configured(user_id):
        return None
    slot = _slot(now, sched["day"], sched["time"])
    sent_this_week = notify.load_state(user_id)["last_week"] == collect.week_id(now)
    if slot <= now and not sent_this_week:
        return now  # overdue: the next tick sends it
    return slot if slot > now else slot + timedelta(days=7)


def due(user_id, now: datetime) -> bool:
    sched = notify.load_settings(user_id)["schedule"]
    return (sched["enabled"] and bool(notify.configured(user_id))
            and now >= _slot(now, sched["day"], sched["time"])
            and notify.load_state(user_id)["last_week"] != collect.week_id(now))


def deliver(user_id, *, now: datetime | None = None, send: bool = True) -> dict[str, str | None]:
    """Run this week's radar and comparisons, then send the digest. Returns {channel: error}."""
    now = now or datetime.now().astimezone()
    report = digest.run_radar(user_id, progress=lambda s: log.info("[%s] %s", user_id, s))
    week = report["week"]
    try:
        digest.compare_all(user_id, week)
    except Exception:  # noqa: BLE001 - the digest still goes out without verdicts
        log.exception("[%s] comparisons failed", user_id)
    if not send:
        return {}
    results = notify.send_digest(user_id, report, comparisons=digest.cached_comparisons(user_id, week),
                                 market=digest.cached_market(user_id, week),
                                 lang=storage.load_settings(user_id)["language"])
    notify.record(user_id, "digest", results, week=week, sent_week=collect.week_id(now))
    return results


def tick(now: datetime | None = None) -> list[str]:
    """Deliver to everyone whose slot has passed. Returns the users served."""
    now = now or datetime.now().astimezone()
    if not _lock.acquire(blocking=False):
        return []  # the previous tick is still running a radar
    served = []
    try:
        for uid in storage.list_users():
            try:
                if due(uid, now):
                    log.info("[%s] weekly digest due", uid)
                    deliver(uid, now=now)
                    served.append(uid)
            except Exception:  # noqa: BLE001 - one person must not stop the others
                log.exception("[%s] scheduled delivery failed", uid)
                notify.record(uid, "digest", {"radar": "failed, see the server log"}, sent_week=collect.week_id(now))
    finally:
        _lock.release()
    return served


def loop(stop: threading.Event | None = None) -> None:
    stop = stop or threading.Event()
    log.info("scheduler started")
    while not stop.is_set():
        tick()
        stop.wait(TICK_SECONDS)


def start_background() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=loop, args=(stop,), name="scheduler", daemon=True).start()
    return stop
