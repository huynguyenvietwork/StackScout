from telegram.ext import ConversationHandler

from stackscout import bot, storage


def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(tmp_path))
    assert storage.load_profile(42) is None
    profile = {
        "person": {"role": "Kỹ sư dữ liệu", "interests": ["DuckDB"]},
        "skills": [{"name": "Python", "category": "language", "ecosystem": "python", "level": "advanced"}],
    }
    path = storage.save_profile(42, profile)
    assert path == tmp_path / "users" / "42" / "profile.yaml"
    assert "Kỹ sư dữ liệu" in path.read_text(encoding="utf-8")  # unicode kept readable
    loaded = storage.load_profile(42)
    assert loaded["skills"][0]["name"] == "Python"
    assert set(loaded["skills"][0]) == {"name", "category", "ecosystem", "level"}
    assert not list(path.parent.glob(".profile.yaml.*"))  # no temp files left behind


def test_remove_callback_data_fits_telegram_limit():
    long_name = "Một-thư-viện-có-tên-rất-dài-" * 5
    kb = bot._remove_keyboard({"skills": [{"name": long_name}]})
    data = kb.inline_keyboard[0][0].callback_data
    assert len(data.encode("utf-8")) <= 64
    assert data.split(":", 2)[2] == bot._short(long_name)


def test_build_application_registers_handlers():
    app = bot.build_application("123456:TEST-TOKEN")
    convs = [h for h in app.handlers[0] if isinstance(h, ConversationHandler)]
    assert {c.name for c in convs} == {"onboarding", "add_skills"}
    commands = {cmd for h in app.handlers[0] for cmd in getattr(h, "commands", ())}
    assert {"profile", "remove", "help", "cancel"} <= commands
    assert -1 in app.handlers  # access gate runs before everything else


def test_sources_keyboard_stays_under_telegram_button_limit():
    from stackscout import sources
    data = {"sources": sources.default_sources()}
    for view in ("on", "off"):
        kb = bot._sources_keyboard(data, view)
        buttons = [b for row in kb.inline_keyboard for b in row]
        assert len(buttons) <= 100
        assert all(len(b.callback_data.encode()) <= 64 for b in buttons)


# ---------------------------------------------------------------- languages

import asyncio
from types import SimpleNamespace

from stackscout import bot_text, i18n


class _FakeMessage:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kwargs):
        self.sent.append(text)


class _FakeQuery:
    def __init__(self, data):
        self.data = data

    async def answer(self, *args, **kwargs):
        pass

    async def edit_message_reply_markup(self, **kwargs):
        pass


def _update(user_id=7, language_code=None, data=None):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, language_code=language_code),
        effective_message=_FakeMessage(),
        callback_query=_FakeQuery(data) if data else None,
    )


def test_every_bot_text_has_all_languages():
    for key, entry in bot_text.TEXT.items():
        assert set(entry) == set(i18n.LANGS), key
    assert set(bot_text.LANGUAGE_NAMES) == set(i18n.LANGS)


def test_tr_renders_in_each_language_and_falls_back_to_english():
    assert bot_text.tr("addsource.added", "en", name="Blog") == "✅ Added <b>Blog</b>. See: /sources"
    assert bot_text.tr("addsource.added", "ja", name="Blog") == "✅ <b>Blog</b> を追加しました。確認：/sources"
    assert bot_text.tr("no_profile", "vi") == "Bạn chưa có hồ sơ. Gõ /start để tạo nhé."
    assert bot_text.tr("no_profile", "fr") == bot_text.tr("no_profile", "en")
    assert bot_text.tr("no_profile", None) == bot_text.tr("no_profile", "en")


def test_user_lang_uses_saved_setting_else_telegram_language(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(tmp_path))
    assert bot.user_lang(_update(language_code="ja-JP")) == "ja"
    assert bot.user_lang(_update(language_code="fr")) == "en"
    assert bot.user_lang(_update(language_code=None)) == "en"
    storage.save_settings(7, {"language": "ko"})
    assert bot.user_lang(_update(language_code="ja-JP")) == "ko"


def test_language_command_saves_setting_and_answers_in_new_language(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKSCOUT_DATA_DIR", str(tmp_path))
    upd = _update(language_code="en", data="lang:zh")
    asyncio.run(bot.language_pressed(upd, SimpleNamespace()))
    assert storage.language_chosen(7)
    assert storage.load_settings(7)["language"] == "zh"
    assert upd.effective_message.sent == [bot_text.tr("language.saved", "zh")]

    upd = _update(language_code="en")
    asyncio.run(bot.help_cmd(upd, SimpleNamespace()))
    assert upd.effective_message.sent == [bot_text.tr("help", "zh")]


def test_language_keyboard_and_handler_registered():
    kb = bot._language_keyboard("ja")
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == [f"lang:{c}" for c in bot_text.LANGUAGE_NAMES]
    assert all(len(b.callback_data.encode()) <= 64 for b in buttons)
    assert any(b.text.startswith("✅ ") and b.callback_data == "lang:ja" for b in buttons)
    app = bot.build_application("123456:TEST-TOKEN")
    commands = {cmd for h in app.handlers[0] for cmd in getattr(h, "commands", ())}
    assert "language" in commands
