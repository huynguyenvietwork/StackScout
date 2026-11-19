import re

from stackscout import bot_text, config, i18n, render

LANGS = set(config.LANGUAGES)


def test_server_dictionaries_cover_every_language():
    for name, table in (("i18n", i18n.MESSAGES), ("render", render.TEXT), ("bot", bot_text.TEXT)):
        for key, entry in table.items():
            assert set(entry) == LANGS, f"{name}: {key} misses {LANGS - set(entry)}"


def test_web_page_dictionary_covers_every_language():
    page = (config.ROOT / "stackscout" / "static" / "index.html").read_text(encoding="utf-8")
    keys = {}
    for lang in LANGS:
        start = page.index(f"\n{lang}: {{\n")
        block = page[start: page.index("\n}", start + 5)]
        keys[lang] = set(re.findall(r'"([\w.]+)":', block))
    for lang in LANGS:
        assert keys[lang] == keys["vi"], f"{lang}: missing {sorted(keys['vi'] - keys[lang])[:5]}"


def test_lang_code_and_user_errors():
    assert i18n.lang_code("ja-JP") == "ja" and i18n.lang_code("fr") == "en" and i18n.lang_code(None) == "en"
    err = i18n.UserError("source.unknown_host", host="x.test")
    assert str(err) == "Domain x.test not found." and err.text("vi") == "Không tìm thấy tên miền x.test."
