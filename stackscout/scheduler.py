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


WINDOW_DAYS = {"daily": 7, "weekly": 7, "monthly": 31}


def period_id(now: datetime, frequency: str) -> str:
    """The period one delivery covers: "2026-11-19", "2026-W47" or "2026-11"."""
    if frequency == "daily":
        return now.date().isoformat()
    if frequency == "monthly":
        return now.strftime("%Y-%m")
    return collect.week_id(now)


def _slot(now: datetime, sched: dict) -> datetime:
    """This period's delivery time."""
    hour, minute = (int(x) for x in sched["time"].split(":"))
    base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if sched["frequency"] == "daily":
        return base
    if sched["frequency"] == "monthly":
        return base.replace(day=sched["monthday"])
    return base - timedelta(days=now.weekday()) + timedelta(days=notify.DAYS.index(sched["day"]))


def _following(slot: datetime, frequency: str, monthday: int) -> datetime:
    if frequency == "daily":
        return slot + timedelta(days=1)
    if frequency == "monthly":
        year, month = (slot.year + 1, 1) if slot.month == 12 else (slot.year, slot.month + 1)
        return slot.replace(year=year, month=month, day=monthday)
    return slot + timedelta(days=7)


def next_run(now: datetime, sched: dict) -> datetime:
    """The next slot strictly after `now`."""
    slot = _slot(now, sched)
    return slot if slot > now else _following(slot, sched["frequency"], sched["monthday"])


def next_delivery(user_id, now: datetime | None = None) -> datetime | None:
    """When this person's next digest goes out, or None if it won't."""
    now = now or datetime.now().astimezone()
    sched = notify.load_settings(user_id)["schedule"]
    if not sched["enabled"] or not notify.configured(user_id):
        return None
    if due(user_id, now):
        return now  # overdue: the next tick sends it
    return next_run(now, sched)


def due(user_id, now: datetime) -> bool:
    sched = notify.load_settings(user_id)["schedule"]
    return (sched["enabled"] and bool(notify.configured(user_id))
            and now >= _slot(now, sched)
            and notify.load_state(user_id)["last_period"] != period_id(now, sched["frequency"]))


def only_new(report: dict, sent: set[str]) -> dict | None:
    """The report without what earlier digests already sent (daily digests). None = nothing new."""
    out = dict(report)
    for key in digest.REPORT_SECTIONS:
        out[key] = [b for b in report.get(key) or [] if any(i not in sent for i in b.get("items") or [])]
    if not any(out[key] for key in digest.REPORT_SECTIONS):
        return None
    return out


def delivered_items(report: dict) -> list[str]:
    return [i for key in digest.REPORT_SECTIONS for b in report.get(key) or [] for i in b.get("items") or []]


def deliver(user_id, *, now: datetime | None = None, send: bool = True) -> dict[str, str | None]:
    """Run the radar and comparisons, then send the digest for this period. Returns {channel: error}."""
    now = now or datetime.now().astimezone()
    sched = notify.load_settings(user_id)["schedule"]
    frequency = sched["frequency"]
    report = digest.run_radar(user_id, progress=lambda s: log.info("[%s] %s", user_id, s),
                              window_days=WINDOW_DAYS[frequency])
    week = report["week"]
    try:
        digest.compare_all(user_id, week)
    except Exception:  # noqa: BLE001 - the digest still goes out without verdicts
        log.exception("[%s] comparisons failed", user_id)
    if not send:
        return {}
    period = period_id(now, frequency)
    if frequency == "daily":
        fresh = only_new(report, set(notify.load_state(user_id)["sent_items"]))
        if fresh is None:  # nothing since the last digest: no message today
            notify.record(user_id, "empty", {"-": None}, week=week, period=period)
            return {}
        report = fresh
    results = notify.send_digest(user_id, report, comparisons=digest.cached_comparisons(user_id, week),
                                 market=digest.cached_market(user_id, week),
                                 lang=storage.load_settings(user_id)["language"], period=frequency, when=now)
    sent = delivered_items(report) if any(e is None for e in results.values()) else []
    notify.record(user_id, "digest", results, week=week, period=period, sent_items=sent)
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
                sched = notify.load_settings(uid)["schedule"]
                notify.record(uid, "digest", {"radar": "failed, see the server log"},
                              period=period_id(now, sched["frequency"]))
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
