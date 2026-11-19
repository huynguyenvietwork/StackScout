"""Telegram bot: onboarding conversation and profile commands (milestone 1).

Flow for a new user:

    /start -> 4 questions -> AI normalises -> [✅ Đúng rồi] [✏️ Sửa lại]
                                                │             │
                                             save        free-text correction
                                                          -> AI revises -> confirm again

Nothing is written to disk until the user confirms.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import os
import warnings

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from . import digest, i18n, sources, storage
from . import profile as prof
from .ai import AIError
from .bot_text import LANGUAGE_NAMES, tr
from .sources import SourceError

log = logging.getLogger(__name__)

# CallbackQueryHandlers inside a per-chat conversation are intentional here.
warnings.filterwarnings("ignore", message=r".*per_message.*", category=PTBUserWarning)

ROLE, SKILLS, PROJECT, INTERESTS, CONFIRM, REVISE = range(6)
ADD_INPUT, ADD_CONFIRM = range(10, 12)

def _confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn(tr("btn.confirm_ok", lang), callback_data="ob:ok"),
                                  Btn(tr("btn.confirm_edit", lang), callback_data="ob:edit")]])


def _retry_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn(tr("btn.retry", lang), callback_data="ob:retry")]])


def _add_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn(tr("btn.add", lang), callback_data="add:ok"),
                                  Btn(tr("btn.cancel", lang), callback_data="add:cancel")]])


def _skip_kb(data: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn(tr("btn.skip", lang), callback_data=data)]])


# ---------------------------------------------------------------- helpers

@contextlib.asynccontextmanager
async def typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Keep the "typing…" indicator alive while a slow AI call runs."""

    async def loop() -> None:
        with contextlib.suppress(Exception):
            while True:
                await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
                await asyncio.sleep(4)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()


def user_lang(update: Update) -> str:
    """The language to talk to this person in: the one they picked with
    /language (or on the web page), else their Telegram app's language."""
    user = update.effective_user
    if user is None:
        return i18n.FALLBACK
    if storage.language_chosen(user.id):
        return storage.load_settings(user.id)["language"]
    lang = i18n.lang_code(user.language_code)
    # Once they have a profile, remember it, so the AI-written digest uses the
    # same language as the bot (strangers who never got that far leave no file).
    if storage.load_profile(user.id) is not None:
        storage.save_settings(user.id, {"language": lang})
    return lang


async def reply(update: Update, text: str, **kwargs) -> None:
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, **kwargs)


async def clear_buttons(update: Update) -> None:
    """Remove the inline keyboard from the message a button was pressed on."""
    query = update.callback_query
    await query.answer()
    with contextlib.suppress(Exception):
        await query.edit_message_reply_markup(reply_markup=None)


def _allowed_users() -> set[int]:
    raw = os.environ.get("STACKSCOUT_ALLOWED_USERS", "")
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """If STACKSCOUT_ALLOWED_USERS is set, ignore everyone else.

    Every profile step costs an AI call on the host machine, so a public
    bot should not answer strangers.
    """
    allowed = context.bot_data.setdefault("allowed_users", _allowed_users())
    user = update.effective_user
    if allowed and (user is None or user.id not in allowed):
        log.info("ignored update from user %s", user.id if user else None)
        raise ApplicationHandlerStop


# ---------------------------------------------------------------- onboarding

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if storage.load_profile(update.effective_user.id):
        lang = user_lang(update)
        await reply(update, tr("welcome_back", lang) + "\n\n" + tr("help", lang))
        return ConversationHandler.END
    return await begin_onboarding(update, context)


async def begin_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["answers"] = {}
    context.user_data.pop("draft", None)
    lang = user_lang(update)
    await reply(update, tr("ob.intro", lang))
    await reply(update, tr("ob.q1", lang))
    return ROLE


async def got_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["answers"]["role"] = update.message.text.strip()
    await reply(update, tr("ob.q2", user_lang(update)))
    return SKILLS


async def got_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["answers"]["skills"] = update.message.text.strip()
    lang = user_lang(update)
    await reply(update, tr("ob.q3", lang), reply_markup=_skip_kb("ob:skip_project", lang))
    return PROJECT


async def got_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await clear_buttons(update)
        context.user_data["answers"]["project"] = ""
    else:
        context.user_data["answers"]["project"] = update.message.text.strip()
    lang = user_lang(update)
    await reply(update, tr("ob.q4", lang), reply_markup=_skip_kb("ob:skip_interests", lang))
    return INTERESTS


async def got_interests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await clear_buttons(update)
        context.user_data["answers"]["interests"] = ""
    else:
        context.user_data["answers"]["interests"] = update.message.text.strip()
    return await build_draft(update, context)


async def build_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = user_lang(update)
    await reply(update, tr("ob.building", lang))
    answers = context.user_data["answers"]
    try:
        async with typing(update, context):
            draft = await asyncio.to_thread(prof.build_from_answers, answers)
    except AIError:
        log.exception("profile normalisation failed")
        await reply(update, tr("ai_failed", lang), reply_markup=_retry_kb(lang))
        return CONFIRM
    return await show_draft(update, context, draft)


async def show_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, draft: dict) -> int:
    context.user_data["draft"] = draft
    lang = user_lang(update)
    if not draft["skills"]:
        await reply(update, tr("ob.no_skills", lang))
        return REVISE
    await reply(
        update,
        tr("ob.draft", lang, profile=prof.format_profile(draft, lang=lang)),
        reply_markup=_confirm_kb(lang),
    )
    return CONFIRM


async def confirm_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await clear_buttons(update)
    draft = context.user_data.pop("draft", None)
    lang = user_lang(update)
    if not draft:
        await reply(update, tr("ob.expired", lang))
        return ConversationHandler.END
    storage.save_profile(update.effective_user.id, draft)
    context.user_data.pop("answers", None)
    await reply(update, tr("ob.saved", lang))
    return ConversationHandler.END


async def confirm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await clear_buttons(update)
    await reply(update, tr("ob.edit_prompt", user_lang(update)))
    return REVISE


async def confirm_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await clear_buttons(update)
    if context.user_data.get("draft"):
        # A revision failed: the draft is intact, just show it again.
        return await show_draft(update, context, context.user_data["draft"])
    if not context.user_data.get("answers"):
        await reply(update, tr("ob.expired", user_lang(update)))
        return ConversationHandler.END
    return await build_draft(update, context)


async def got_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Free-text correction, typed after ✏️ or straight at the confirm step."""
    correction = update.message.text.strip()
    draft = context.user_data.get("draft")
    lang = user_lang(update)
    await reply(update, tr("ob.updating", lang))
    try:
        async with typing(update, context):
            if draft and draft["skills"]:
                new_draft = await asyncio.to_thread(prof.revise, draft, correction)
            else:
                # No usable draft yet: treat the text as the skills answer.
                answers = context.user_data.setdefault("answers", {})
                answers["skills"] = correction
                new_draft = await asyncio.to_thread(prof.build_from_answers, answers)
    except AIError:
        log.exception("profile revision failed")
        await reply(update, tr("ai_failed", lang), reply_markup=_retry_kb(lang))
        return CONFIRM
    return await show_draft(update, context, new_draft)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in ("answers", "draft", "add_candidate"):
        context.user_data.pop(key, None)
    await reply(update, tr("cancelled", user_lang(update)))
    return ConversationHandler.END


# ---------------------------------------------------------------- /add

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = user_lang(update)
    if not storage.load_profile(update.effective_user.id):
        await reply(update, tr("no_profile", lang))
        return ConversationHandler.END
    text = " ".join(context.args or []).strip()
    if text:
        return await add_process(update, context, text)
    await reply(update, tr("add.prompt", lang))
    return ADD_INPUT


async def add_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await add_process(update, context, update.message.text.strip())


async def add_process(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    lang = user_lang(update)
    await reply(update, tr("processing", lang))
    try:
        async with typing(update, context):
            candidate = await asyncio.to_thread(prof.skills_from_text, text)
    except AIError:
        log.exception("/add normalisation failed")
        await reply(update, tr("add.ai_failed", lang))
        return ConversationHandler.END

    current = storage.load_profile(update.effective_user.id) or prof.empty_profile()
    fresh = prof.new_skills(current, candidate)
    if not fresh:
        await reply(update, tr("add.nothing_new", lang))
        return ConversationHandler.END
    context.user_data["add_candidate"] = {**prof.empty_profile(), "skills": fresh}
    await reply(
        update,
        tr("add.confirm", lang, skills=prof.format_skill_list(fresh, lang=lang)),
        reply_markup=_add_kb(lang),
    )
    return ADD_CONFIRM


async def add_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await clear_buttons(update)
    candidate = context.user_data.pop("add_candidate", None)
    lang = user_lang(update)
    if not candidate:
        await reply(update, tr("add.expired", lang))
        return ConversationHandler.END
    user_id = update.effective_user.id
    current = storage.load_profile(user_id) or prof.empty_profile()
    storage.save_profile(user_id, prof.merge(current, candidate))
    await reply(update, tr("add.done", lang))
    return ConversationHandler.END


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await clear_buttons(update)
    context.user_data.pop("add_candidate", None)
    await reply(update, tr("profile_unchanged", user_lang(update)))
    return ConversationHandler.END


# ---------------------------------------------------------------- /profile, /remove

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = storage.load_profile(update.effective_user.id)
    lang = user_lang(update)
    if not profile:
        await reply(update, tr("no_profile", lang))
        return
    await reply(update, prof.format_profile(profile, lang=lang) + "\n\n" + tr("profile.footer", lang))


def _short(name: str) -> str:
    return name.encode("utf-8")[:40].decode("utf-8", "ignore")


def _remove_keyboard(profile: dict, lang: str = "vi") -> InlineKeyboardMarkup:
    # Telegram limits callback_data to 64 bytes; buttons carry the list index
    # plus a name check so a stale keyboard can never delete the wrong skill.
    rows = [
        [Btn(f"❌ {s['name']}", callback_data=f"rm:{i}:{_short(s['name'])}")]
        for i, s in enumerate(profile["skills"])
    ]
    rows.append([Btn(tr("btn.done", lang), callback_data="rm-done")])
    return InlineKeyboardMarkup(rows)


async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = storage.load_profile(update.effective_user.id)
    lang = user_lang(update)
    if not profile or not profile["skills"]:
        await reply(update, tr("remove.empty", lang))
        return
    await reply(update, tr("remove.prompt", lang), reply_markup=_remove_keyboard(profile, lang))


async def remove_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    lang = user_lang(update)
    profile = storage.load_profile(user_id)
    _, index, short = query.data.split(":", 2)
    i = int(index)
    if not profile or i >= len(profile["skills"]) or _short(profile["skills"][i]["name"]) != short:
        await query.answer(tr("remove.stale", lang), show_alert=True)
        return
    name = profile["skills"][i]["name"]
    prof.remove_skill(profile, name)
    storage.save_profile(user_id, profile)
    await query.answer(tr("removed", lang, name=name))
    if profile["skills"]:
        await query.edit_message_reply_markup(reply_markup=_remove_keyboard(profile, lang))
    else:
        await query.edit_message_text(tr("remove.all_gone", lang))


async def remove_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(tr("remove.done", user_lang(update)))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, tr("help", user_lang(update)))


# ---------------------------------------------------------------- sources (milestone 2)

MAX_SOURCE_ROWS = 45  # Telegram allows ~100 buttons per message


def _sources_keyboard(data: dict, view: str = "on", lang: str = "vi") -> InlineKeyboardMarkup:
    """Two pages so the catalog never exceeds Telegram's button limit:
    "on" = enabled sources (toggle + delete), "off" = everything else (toggle)."""
    on = [s for s in data["sources"] if s.get("enabled", True)]
    off = [s for s in data["sources"] if not s.get("enabled", True)]

    def label(s: dict) -> str:
        mark = "✅" if s.get("enabled", True) else "⬜"
        return f"{mark} {s['name']}" + (tr("src.official", lang) if s.get("official") else "")

    if view == "on":
        rows = [[Btn(label(s), callback_data=f"src:on:t:{s['id']}"[:64]),
                 Btn("🗑", callback_data=f"src:on:d:{s['id']}"[:64])] for s in on[:MAX_SOURCE_ROWS]]
        if off:
            rows.append([Btn(tr("src.show_off", lang, n=len(off)), callback_data="src:off:v:-")])
    else:
        rows = [[Btn(label(s), callback_data=f"src:off:t:{s['id']}"[:64])] for s in off[:MAX_SOURCE_ROWS]]
        rows.append([Btn(tr("src.back_on", lang, n=len(on)), callback_data="src:on:v:-")])
    return InlineKeyboardMarkup(rows)


async def sources_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = sources.load(update.effective_user.id)
    on = len(sources.enabled(data))
    lang = user_lang(update)
    await reply(update, tr("src.intro", lang, n=on), reply_markup=_sources_keyboard(data, lang=lang))


async def sources_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, view, action, source_id = query.data.split(":", 3)
    user_id = update.effective_user.id
    lang = user_lang(update)
    try:
        data = sources.load(user_id)
        if action == "v":
            await query.answer()
        else:
            source = next(s for s in data["sources"] if s["id"] == source_id)
            if action == "t":
                data = sources.set_enabled(user_id, source_id, not source.get("enabled", True))
                turned_on = not source.get("enabled", True)
                await query.answer(tr("src.turned_on" if turned_on else "src.turned_off", lang))
            else:
                data = sources.remove(user_id, source_id)
                await query.answer(tr("removed", lang, name=source["name"]))
    except (StopIteration, SourceError):
        await query.answer(tr("src.stale", lang), show_alert=True)
        return
    with contextlib.suppress(Exception):
        await query.edit_message_reply_markup(reply_markup=_sources_keyboard(data, view, lang))


async def addsource_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = " ".join(context.args or []).strip()
    lang = user_lang(update)
    if not url:
        await reply(update, tr("addsource.usage", lang))
        return
    try:
        async with typing(update, context):
            added = await asyncio.to_thread(sources.add, update.effective_user.id, url)
    except SourceError as exc:
        await reply(update, f"😕 {html.escape(i18n.error_text(exc, lang))}")
        return
    await reply(update, tr("addsource.added", lang, name=html.escape(added["name"])))


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = user_lang(update)
    await reply(update, tr("reset.confirm", lang),
                reply_markup=InlineKeyboardMarkup([[Btn(tr("btn.reset_yes", lang), callback_data="srcreset:yes"),
                                                    Btn(tr("btn.cancel", lang), callback_data="srcreset:no")]]))


async def reset_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clear_buttons(update)
    lang = user_lang(update)
    if update.callback_query.data.endswith("yes"):
        sources.reset(update.effective_user.id)
        await reply(update, tr("reset.done", lang))
    else:
        await reply(update, tr("reset.cancelled", lang))


# ---------------------------------------------------------------- radar on demand

async def radar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    running: set = context.bot_data.setdefault("radar_running", set())
    lang = user_lang(update)
    if not storage.load_profile(user_id):
        await reply(update, tr("no_profile", lang))
        return
    if user_id in running:
        await reply(update, tr("radar.running", lang))
        return
    running.add(user_id)
    await reply(update, tr("radar.started", lang))
    try:
        async with typing(update, context):
            report = await asyncio.to_thread(digest.run_radar, user_id)
    except ValueError as exc:
        await reply(update, f"😕 {html.escape(i18n.error_text(exc, lang))}")
        return
    except Exception:  # noqa: BLE001
        log.exception("radar failed for %s", user_id)
        await reply(update, tr("radar.failed", lang))
        return
    finally:
        running.discard(user_id)
    for text in digest.render_telegram(report, lang=lang):
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ---------------------------------------------------------------- import (milestone 6)

MAX_IMPORT_BYTES = 200_000


def _import_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn(tr("btn.import_ok", lang), callback_data="imp:ok"),
                                  Btn(tr("btn.cancel", lang), callback_data="imp:cancel")]])


async def import_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    lang = user_lang(update)
    if doc.file_size and doc.file_size > MAX_IMPORT_BYTES:
        await reply(update, tr("import.too_large", lang))
        return
    raw = await (await doc.get_file()).download_as_bytearray()
    try:
        imported = prof.parse_import(bytes(raw).decode("utf-8", "replace"))
    except ValueError as exc:
        await reply(update, f"😕 {html.escape(i18n.error_text(exc, lang))}")
        return
    user_id = update.effective_user.id
    base = storage.load_profile(user_id) or prof.empty_profile()
    added = prof.new_skills(base, imported)
    context.user_data["import_candidate"] = prof.merge(base, imported)
    summary = tr("import.added", lang, n=len(added), skills=prof.format_skill_list(added, lang=lang)) if added \
        else tr("import.nothing_new", lang)
    await reply(update, tr("import.confirm", lang, summary=summary), reply_markup=_import_kb(lang))


async def import_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clear_buttons(update)
    candidate = context.user_data.pop("import_candidate", None)
    lang = user_lang(update)
    if update.callback_query.data == "imp:cancel" or not candidate:
        await reply(update, tr("profile_unchanged", lang))
        return
    storage.save_profile(update.effective_user.id, candidate)
    await reply(update, tr("import.done", lang))


# ---------------------------------------------------------------- /language

def _language_keyboard(current: str) -> InlineKeyboardMarkup:
    # callback_data is "lang:<code>", a few bytes: far under Telegram's 64.
    rows = [[Btn(("✅ " if code == current else "") + name, callback_data=f"lang:{code}")]
            for code, name in LANGUAGE_NAMES.items()]
    return InlineKeyboardMarkup(rows)


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = user_lang(update)
    await reply(update, tr("language.prompt", lang), reply_markup=_language_keyboard(lang))


async def language_pressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await clear_buttons(update)
    code = update.callback_query.data.split(":", 1)[1]
    if code not in LANGUAGE_NAMES:
        return
    storage.save_settings(update.effective_user.id, {"language": code})
    await reply(update, tr("language.saved", code))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text(tr("error.generic", user_lang(update)))


# ---------------------------------------------------------------- wiring

def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()
    text = filters.TEXT & ~filters.COMMAND

    app.add_handler(TypeHandler(Update, gate), group=-1)

    app.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler("start", start),
                CommandHandler("newprofile", begin_onboarding),
            ],
            states={
                ROLE: [MessageHandler(text, got_role)],
                SKILLS: [MessageHandler(text, got_skills)],
                PROJECT: [
                    MessageHandler(text, got_project),
                    CallbackQueryHandler(got_project, pattern="^ob:skip_project$"),
                ],
                INTERESTS: [
                    MessageHandler(text, got_interests),
                    CallbackQueryHandler(got_interests, pattern="^ob:skip_interests$"),
                ],
                CONFIRM: [
                    CallbackQueryHandler(confirm_ok, pattern="^ob:ok$"),
                    CallbackQueryHandler(confirm_edit, pattern="^ob:edit$"),
                    CallbackQueryHandler(confirm_retry, pattern="^ob:retry$"),
                    MessageHandler(text, got_correction),
                ],
                REVISE: [MessageHandler(text, got_correction)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True,
            name="onboarding",
        )
    )
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("add", add_start)],
            states={
                ADD_INPUT: [MessageHandler(text, add_text)],
                ADD_CONFIRM: [
                    CallbackQueryHandler(add_ok, pattern="^add:ok$"),
                    CallbackQueryHandler(add_cancel, pattern="^add:cancel$"),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True,
            name="add_skills",
        )
    )
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("remove", remove_start))
    app.add_handler(CallbackQueryHandler(remove_pressed, pattern=r"^rm:\d+:"))
    app.add_handler(CallbackQueryHandler(remove_done, pattern="^rm-done$"))
    app.add_handler(CommandHandler("sources", sources_cmd))
    app.add_handler(CallbackQueryHandler(sources_pressed, pattern=r"^src:(on|off):[tdv]:"))
    app.add_handler(CommandHandler("addsource", addsource_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CallbackQueryHandler(reset_pressed, pattern=r"^srcreset:"))
    app.add_handler(CommandHandler("radar", radar_cmd, block=False))
    app.add_handler(MessageHandler(
        filters.Document.FileExtension("yaml") | filters.Document.FileExtension("yml"), import_file))
    app.add_handler(CallbackQueryHandler(import_pressed, pattern=r"^imp:"))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CallbackQueryHandler(language_pressed, pattern=r"^lang:[a-z]{2}$"))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_error_handler(on_error)
    return app
