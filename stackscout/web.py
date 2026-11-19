"""Local web UI: the same profile flow as the Telegram bot, in a browser.

Runs on 127.0.0.1 only and serves one profile (STACKSCOUT_WEB_USER,
default "web"). Set it to your Telegram user id to share one profile
between the bot and the web page.

The draft lives in the browser until the user confirms; only the
confirm/add/remove endpoints write to disk, and everything written goes
through profile.clean().
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import config, digest, i18n, notify, scheduler, sources, storage
from . import profile as prof
from .ai import AIError
from .sources import SourceError

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
# Long enough to paste a whole stack description or CV section; the
# page enforces the same limits with maxlength (see static/index.html).
MAX_SHORT = 4000
MAX_LONG = 20000


class Answers(BaseModel):
    role: str = Field("", max_length=MAX_SHORT)
    skills: str = Field(..., min_length=1, max_length=MAX_LONG)
    project: str = Field("", max_length=MAX_LONG)
    interests: str = Field("", max_length=MAX_SHORT)


class Revision(BaseModel):
    draft: dict
    correction: str = Field(..., min_length=1, max_length=MAX_SHORT)


class ProfileIn(BaseModel):
    profile: dict


class SkillText(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_SHORT)


class SkillsIn(BaseModel):
    skills: list[dict] = Field(..., min_length=1, max_length=200)


class PersonIn(BaseModel):
    role: str = Field("", max_length=MAX_SHORT)
    interests: list[str] = Field(default_factory=list, max_length=50)


class ImportIn(BaseModel):
    yaml: str = Field(..., min_length=1, max_length=prof.MAX_IMPORT_CHARS)


class SourceIn(BaseModel):
    url: str = Field(..., min_length=3, max_length=2000)


class SettingsIn(BaseModel):
    language: str = Field(..., max_length=8)


class CompareIn(BaseModel):
    week: str = Field(..., pattern=r"^\d{4}-W\d{2}$")
    name: str = Field(..., min_length=1, max_length=200)
    against: str = Field(..., min_length=1, max_length=200)


class WeekIn(BaseModel):
    week: str = Field(..., pattern=r"^\d{4}-W\d{2}$")


class MarketIn(BaseModel):
    week: str = Field(..., pattern=r"^\d{4}-W\d{2}$")
    name: str = Field(..., min_length=1, max_length=200)


class NotifyIn(BaseModel):
    schedule: dict | None = None
    channels: dict | None = None


class TokenIn(BaseModel):
    token: str = Field("", max_length=200)


class SourceToggle(BaseModel):
    enabled: bool


class ClientLog(BaseModel):
    message: str = Field(..., max_length=2000)
    detail: str = Field("", max_length=8000)


def create_app(user_id: str | None = None) -> FastAPI:
    uid = user_id or os.environ.get("STACKSCOUT_WEB_USER") or "web"
    storage.user_dir(uid)  # fail fast on an invalid id
    app = FastAPI(title="StackScout", docs_url=None, redoc_url=None, openapi_url=None)

    def lang() -> str:
        return storage.load_settings(uid)["language"]

    def fail(status: int, key: str, **params) -> HTTPException:
        """An HTTP error whose message is in the person's language."""
        return HTTPException(status_code=status, detail=i18n.t(key, lang(), **params))

    def user_error(status: int, exc: Exception) -> HTTPException:
        return HTTPException(status_code=status, detail=i18n.error_text(exc, lang()))

    def _ai(fn, *args):
        try:
            return fn(*args)
        except AIError as exc:
            log.exception("AI step failed")
            raise fail(502, "ai.failed") from exc

    @app.middleware("http")
    async def log_api_calls(request: Request, call_next):
        # One line per API call, so a failure seen in the browser can always
        # be matched to what the server did (or show it never arrived).
        start = time.monotonic()
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            log.log(level, "%s %s -> %s (%.1fs)", request.method, request.url.path,
                    response.status_code, time.monotonic() - start)
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:]) or 'body'}: {e['msg']}" for e in exc.errors()
        )
        log.warning("invalid request to %s: %s", request.url.path, problems)
        return JSONResponse(status_code=422, content={"detail": i18n.t("request.invalid", lang(), problems=problems)})

    @app.post("/api/client-log", status_code=204)
    def client_log(body: ClientLog) -> Response:
        log.error("browser error: %s\n%s", body.message, body.detail)
        return Response(status_code=204)

    def current() -> dict:
        profile = storage.load_profile(uid)
        if profile is None:
            raise fail(404, "profile.missing")
        return profile

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/meta")
    def meta() -> dict:
        return {
            "categories": [{"id": k, "label": v, "labels": config.category_labels()[k]}
                           for k, v in config.categories().items()],
            "levels": prof.LEVEL_LABEL,
            "languages": list(config.LANGUAGES),
        }

    @app.get("/api/profile")
    def get_profile() -> dict:
        return {"profile": storage.load_profile(uid)}

    # Sync endpoints: FastAPI runs them in a thread pool, so a 20 s AI call
    # does not block the server.
    @app.post("/api/profile/draft")
    def draft(answers: Answers) -> dict:
        return {"profile": _ai(prof.build_from_answers, answers.model_dump())}

    @app.post("/api/profile/revise")
    def revise(body: Revision) -> dict:
        draft = prof.clean(body.draft)
        if draft["skills"]:
            return {"profile": _ai(prof.revise, draft, body.correction)}
        # Nothing recognised yet: treat the text as the skills answer.
        answers = {"role": draft["person"]["role"], "skills": body.correction}
        return {"profile": _ai(prof.build_from_answers, answers)}

    @app.put("/api/profile")
    def save(body: ProfileIn) -> dict:
        cleaned = prof.clean(body.profile)
        if not cleaned["skills"]:
            raise fail(422, "profile.needs_skill")
        storage.save_profile(uid, cleaned)
        return {"profile": cleaned}

    @app.post("/api/skills/preview")
    def preview_skills(body: SkillText) -> dict:
        profile = current()
        candidate = _ai(prof.skills_from_text, body.text)
        return {"skills": prof.new_skills(profile, candidate)}

    @app.post("/api/skills")
    def add_skills(body: SkillsIn) -> dict:
        merged = prof.merge(current(), {"skills": body.skills})
        storage.save_profile(uid, merged)
        return {"profile": merged}

    @app.delete("/api/skills/{name}")
    def remove_skill(name: str) -> dict:
        profile = current()
        if not prof.remove_skill(profile, name):
            raise fail(404, "profile.no_such_skill")
        storage.save_profile(uid, profile)
        return {"profile": profile}

    @app.patch("/api/profile/person")
    def update_person(body: PersonIn) -> dict:
        profile = current()
        profile["person"] = {"role": body.role, "interests": body.interests}
        cleaned = prof.clean(profile)
        storage.save_profile(uid, cleaned)
        return {"profile": cleaned}

    # ---- milestone 6: import a profile generated from code or a CV
    @app.get("/api/profile/import/prompt")
    def import_prompt() -> dict:
        return {"prompt": (config.PROMPTS_DIR / "extract_profile.md").read_text(encoding="utf-8")}

    @app.post("/api/profile/import/preview")
    def import_preview(body: ImportIn) -> dict:
        try:
            imported = prof.parse_import(body.yaml)
        except ValueError as exc:
            raise user_error(422, exc) from exc
        # clean() keeps technology names and levels only: repo names, projects and
        # what they are for never reach the stored profile.
        base = storage.load_profile(uid) or prof.empty_profile()
        # Imported data is merged into what the user typed, never overwrites it.
        return {"profile": prof.merge(base, imported), "added": prof.new_skills(base, imported)}

    # ---- milestone 2: sources
    def _sources_call(fn, *args) -> dict:
        try:
            return fn(*args)
        except SourceError as exc:
            raise user_error(422, exc) from exc

    @app.get("/api/sources")
    def list_sources() -> dict:
        return sources.load(uid)

    @app.post("/api/sources")
    def add_source(body: SourceIn) -> dict:
        added = _sources_call(sources.add, uid, body.url)
        return {"added": added, **sources.load(uid)}

    @app.patch("/api/sources/{source_id}")
    def toggle_source(source_id: str, body: SourceToggle) -> dict:
        return _sources_call(sources.set_enabled, uid, source_id, body.enabled)

    @app.delete("/api/sources/{source_id}")
    def delete_source(source_id: str) -> dict:
        return _sources_call(sources.remove, uid, source_id)

    @app.post("/api/sources/reset")
    def reset_sources() -> dict:
        return sources.reset(uid)

    # ---- milestones 3-5: the weekly radar, run in a background thread
    job = {"running": False, "step": "", "error": None, "week": None, "started_at": None}
    job_lock = threading.Lock()

    def _run_job() -> None:
        def progress(message: str) -> None:
            job["step"] = message

        try:
            job["week"] = digest.run_radar(uid, progress=progress)["week"]
        except ValueError as exc:  # user-facing (no profile, no sources)
            job["error"] = i18n.error_text(exc, lang())
        except Exception:  # noqa: BLE001
            log.exception("radar run failed")
            job["error"] = i18n.t("radar.failed", lang())
        finally:
            job["running"] = False
        if job["week"]:
            try:  # fill the "So với stack" tab without waiting for a click
                start_auto(job["week"])
            except Exception:  # noqa: BLE001 - the report itself is ready
                log.exception("could not start automatic comparisons")

    @app.post("/api/radar/run", status_code=202)
    def run_radar() -> dict:
        current()
        with job_lock:
            if job["running"]:
                raise fail(409, "radar.running")
            job.update(running=True, step="start", error=None, week=None,
                       started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        threading.Thread(target=_run_job, name="radar", daemon=True).start()
        return dict(job)

    @app.get("/api/radar/status")
    def radar_status() -> dict:
        return dict(job)

    # ---- settings: UI language = language of AI-written content
    @app.get("/api/settings")
    def get_settings() -> dict:
        # "chosen": false means the language is only the default; the page then
        # proposes the browser's language instead.
        return {**storage.load_settings(uid), "chosen": storage.language_chosen(uid)}

    @app.put("/api/settings")
    def put_settings(body: SettingsIn) -> dict:
        if body.language not in config.LANGUAGES:
            raise fail(422, "settings.bad_language")
        return storage.save_settings(uid, {"language": body.language})

    # ---- "So với stack": every natural pair is compared automatically in the
    # background; the reader can still ask for any other tool (POST /api/compare).
    auto = {"running": False, "week": None, "total": 0, "done": 0, "active": [], "failed": {}}
    auto_lock = threading.Lock()

    def _auto_started(key: str) -> None:
        with auto_lock:
            auto["active"].append(key)

    def _auto_finished(key: str, error: str | None) -> None:
        with auto_lock:
            auto["active"].remove(key)
            auto["done"] += 1
            if error:
                auto["failed"][key] = error

    def _run_auto(week: str) -> None:
        try:
            digest.compare_all(uid, week, on_start=_auto_started, on_finish=_auto_finished)
        except Exception:  # noqa: BLE001
            log.exception("auto comparison failed")
        finally:
            with auto_lock:
                auto["running"] = False
                auto["active"] = []

    def start_auto(week: str) -> dict:
        todo = digest.auto_jobs(uid, week)  # ValueError when there is no such report
        with auto_lock:
            if auto["running"]:
                return dict(auto)
            # Failed pairs are not cached, so they are part of `todo` again: a new run retries them.
            auto.update(running=bool(todo), week=week, total=len(todo), done=0, active=[], failed={})
            if todo:
                threading.Thread(target=_run_auto, args=(week,), name="compare", daemon=True).start()
            return dict(auto)

    def auto_status() -> dict:
        with auto_lock:
            return {**auto, "active": list(auto["active"]), "failed": dict(auto["failed"])}

    @app.post("/api/compare/auto")
    def compare_auto(body: WeekIn) -> dict:
        try:
            start_auto(body.week)
        except ValueError as exc:
            raise user_error(404, exc) from exc
        return auto_status()

    @app.get("/api/compare/auto")
    def compare_auto_status() -> dict:
        return auto_status()

    @app.get("/api/compare")
    def get_comparisons(week: str) -> dict:
        return {"comparisons": digest.cached_comparisons(uid, week)}

    @app.post("/api/compare")
    def compare_item(body: CompareIn) -> dict:
        try:
            result = digest.compare_item(uid, body.week, body.name, body.against)
        except ValueError as exc:
            raise user_error(422, exc) from exc
        except AIError as exc:
            log.exception("comparison failed")
            raise fail(502, "ai.failed") from exc
        return {"key": digest.comparison_key(body.name, result["current"]), "comparison": result}

    # ---- "Model & AI mới": a new model or tool vs its 3-5 strongest competitors
    @app.get("/api/market")
    def get_market(week: str) -> dict:
        return {"market": digest.cached_market(uid, week)}

    @app.post("/api/market")
    def market_item(body: MarketIn) -> dict:
        try:
            result = digest.market_item(uid, body.week, body.name)
        except ValueError as exc:
            raise user_error(422, exc) from exc
        except AIError as exc:
            log.exception("market comparison failed")
            raise fail(502, "ai.failed") from exc
        return {"key": body.name.casefold(), "comparison": result}

    # ---- notifications tab: schedule, channels, tests, delivery log
    def notify_view() -> dict:
        now = datetime.now().astimezone()
        nxt = scheduler.next_delivery(uid, now)
        offset = now.strftime("%z")
        state = notify.load_state(uid)
        return {**notify.public_settings(uid), "next": nxt.isoformat(timespec="minutes") if nxt else None,
                "now": now.isoformat(timespec="minutes"), "tz": f"UTC{offset[:3]}:{offset[3:]}",
                "log": state["log"], "has_report": bool(digest.list_reports(uid))}

    @app.get("/api/notify")
    def get_notify() -> dict:
        return notify_view()

    @app.put("/api/notify")
    def put_notify(body: NotifyIn) -> dict:
        try:
            notify.save_settings(uid, body.model_dump(exclude_none=False, exclude_unset=True))
        except ValueError as exc:
            raise user_error(422, exc) from exc
        return notify_view()

    @app.post("/api/notify/test/{channel}")
    def notify_test_channel(channel: str) -> dict:
        if channel not in notify.CHANNELS:
            raise HTTPException(status_code=404, detail="Unknown channel")
        try:
            notify.send_test(uid, channel, lang())
            notify.record(uid, "test", {channel: None})
        except i18n.UserError as exc:
            raise user_error(422, exc) from exc
        except notify.NotifyError as exc:
            notify.record(uid, "test", {channel: str(exc)})
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return notify_view()

    @app.post("/api/notify/send")
    def notify_send_now() -> dict:
        if not notify.configured(uid):
            raise fail(422, "notify.not_configured")
        weeks = digest.list_reports(uid)
        if not weeks:
            raise fail(404, "report.missing")
        week = weeks[0]
        results = notify.send_digest(uid, digest.load_report(uid, week), lang=lang(),
                                     comparisons=digest.cached_comparisons(uid, week),
                                     market=digest.cached_market(uid, week))
        notify.record(uid, "manual", results, week=week)
        return {**notify_view(), "results": results}

    @app.post("/api/notify/telegram/chats")
    def notify_telegram_chats(body: TokenIn) -> dict:
        token = body.token.strip() or notify.resolve(uid, "telegram")["config"].get("token")
        if not token:
            raise fail(422, "notify.need_token")
        try:
            return {"chats": notify.telegram_chats(token)}
        except notify.NotifyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/reports")
    def reports() -> dict:
        return {"weeks": digest.list_reports(uid)}

    @app.get("/api/reports/{week}")
    def report(week: str) -> dict:
        found = digest.load_report(uid, week)
        if found is None:
            raise fail(404, "report.missing")
        return found

    return app
