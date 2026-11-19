"""The weekly digest as messages for every channel, in the reader's language.

`build()` turns a report (plus the week's cached comparisons) into a
channel-neutral model; `telegram()`, `email()`, `slack()`, `discord()` and
`webhook()` format that model. Adding a channel means adding one formatter.
"""

from __future__ import annotations

import html
from typing import Callable

from . import i18n

AI_GROUP_ORDER = ("models", "coding", "agents")
# New models are compared with rival models (market), never with an SDK of the stack.
MODEL_CATEGORIES = frozenset({"llm-provider-sdk", "local-llm-inference"})
# Reports written before group codes stored the Vietnamese label.
AI_GROUP_FROM_VI = {"Model mới": "models", "Công cụ AI lập trình": "coding", "Agent & framework": "agents"}
ECOSYSTEM_LABEL = {"dotnet": ".NET", "node": "Node.js", "python": "Python", "jvm": "JVM", "go": "Go",
                   "rust": "Rust", "frontend": "Frontend", "mobile": "Mobile", "cloud": "Cloud", "any": ""}

TEXT: dict[str, dict[str, str]] = {
    "week": {"vi": "Tuần {w}/{y}", "en": "Week {w}, {y}", "zh": "{y} 年第 {w} 周", "ja": "{y}年 第{w}週", "ko": "{y}년 {w}주차"},
    "day": {"vi": "Ngày {d}/{m}/{y}", "en": "{mon} {d}, {y}", "zh": "{y}年{m}月{d}日", "ja": "{y}年{m}月{d}日", "ko": "{y}년 {m}월 {d}일"},
    "month": {"vi": "Tháng {m}/{y}", "en": "{month} {y}", "zh": "{y}年{m}月", "ja": "{y}年{m}月", "ko": "{y}년 {m}월"},
    "title": {"vi": "TECH RADAR — {week}", "en": "TECH RADAR — {week}", "zh": "技术雷达 — {week}",
              "ja": "テックレーダー — {week}", "ko": "테크 레이더 — {week}"},
    "intro": {"vi": "Đã đọc {items} tin từ {sources} nguồn của bạn.",
              "en": "Read {items} items from your {sources} sources.",
              "zh": "已从你的 {sources} 个信息源读取 {items} 条内容。",
              "ja": "あなたの {sources} 件のソースから {items} 件を読みました。",
              "ko": "내 소스 {sources}곳에서 {items}건을 읽었습니다."},
    "sec.ai": {"vi": "MODEL & CÔNG CỤ AI MỚI TUẦN NÀY", "en": "NEW AI MODELS & TOOLS THIS WEEK",
               "zh": "本周新 AI 模型与工具", "ja": "今週の新しい AI モデルとツール", "ko": "이번 주 새 AI 모델과 도구"},
    "group.models": {"vi": "Model mới", "en": "New models", "zh": "新模型", "ja": "新しいモデル", "ko": "새 모델"},
    "group.coding": {"vi": "Công cụ AI lập trình", "en": "AI coding tools", "zh": "AI 编程工具",
                     "ja": "AI コーディングツール", "ko": "AI 코딩 도구"},
    "group.agents": {"vi": "Agent & framework", "en": "Agents & frameworks", "zh": "智能体与框架",
                     "ja": "エージェントとフレームワーク", "ko": "에이전트와 프레임워크"},
    "sec.stack": {"vi": "1. CÙNG LOẠI VỚI STACK CỦA BẠN", "en": "1. SAME KIND AS YOUR STACK",
                  "zh": "1. 与你的技术栈同类", "ja": "1. あなたのスタックと同種", "ko": "1. 내 스택과 같은 종류"},
    "stack.empty": {"vi": "Tuần này chưa có công cụ mới cùng loại với stack của bạn.",
                    "en": "No new tool of the same kind as your stack this week.",
                    "zh": "本周没有与你技术栈同类的新工具。", "ja": "今週はあなたのスタックと同種の新しいツールはありません。",
                    "ko": "이번 주에는 내 스택과 같은 종류의 새 도구가 없습니다."},
    "stack.web": {"vi": "Chi tiết hơn/kém và nguồn: tab “So với stack” trên web.",
                  "en": "Pros, cons and sources: the “Vs. my stack” tab on the web.",
                  "zh": "优缺点与来源：见网页上的“对比技术栈”标签页。",
                  "ja": "長所・短所と出典：Web の「スタックと比較」タブ。",
                  "ko": "장단점과 출처: 웹의 ‘스택과 비교’ 탭."},
    "same_kind": {"vi": "cùng loại {tool}", "en": "same kind as {tool}", "zh": "与 {tool} 同类",
                  "ja": "{tool} と同種", "ko": "{tool}와(과) 같은 종류"},
    "vs_rivals": {"vi": "↳ So với: {names}", "en": "↳ Vs.: {names}", "zh": "↳ 对比：{names}",
                  "ja": "↳ 比較：{names}", "ko": "↳ 비교: {names}"},
    "sec.updates": {"vi": "2. CẬP NHẬT CÔNG CỤ BẠN ĐANG DÙNG", "en": "2. UPDATES TO TOOLS YOU USE",
                    "zh": "2. 你正在使用的工具有更新", "ja": "2. 使っているツールの更新", "ko": "2. 사용 중인 도구의 업데이트"},
    "sec.other": {"vi": "3. CÙNG LOẠI Ở HỆ SINH THÁI KHÁC", "en": "3. SAME KIND, OTHER ECOSYSTEMS",
                  "zh": "3. 其他生态中的同类", "ja": "3. 他のエコシステムの同種", "ko": "3. 다른 생태계의 같은 종류"},
    "sec.new": {"vi": "4. LĨNH VỰC MỚI ĐÁNG CHÚ Ý", "en": "4. NEW AREAS WORTH A LOOK",
                "zh": "4. 值得关注的新领域", "ja": "4. 注目の新分野", "ko": "4. 주목할 새 분야"},
    "sec.themes": {"vi": "5. TỔNG HỢP TUẦN TỪ NGUỒN CỦA BẠN", "en": "5. THIS WEEK FROM YOUR SOURCES",
                   "zh": "5. 本周信息源综述", "ja": "5. 今週のソースまとめ", "ko": "5. 이번 주 소스 요약"},
    "empty": {"vi": "Không có gì đáng kể tuần này.", "en": "Nothing notable this week.", "zh": "本周没有值得注意的内容。",
              "ja": "今週は特にありません。", "ko": "이번 주에는 특별한 소식이 없습니다."},
    "themes.empty": {"vi": "Chưa tổng hợp được tuần này.", "en": "No roundup this week.", "zh": "本周暂无综述。",
                     "ja": "今週のまとめはありません。", "ko": "이번 주 요약이 없습니다."},
    "official": {"vi": "chính chủ", "en": "first-party", "zh": "官方", "ja": "公式", "ko": "공식"},
    "rec.adopt": {"vi": "🟢 NÊN CHUYỂN", "en": "🟢 ADOPT", "zh": "🟢 建议采用", "ja": "🟢 採用推奨", "ko": "🟢 도입 권장"},
    "rec.trial": {"vi": "🟡 THỬ NGHIỆM", "en": "🟡 TRIAL", "zh": "🟡 试用", "ja": "🟡 試用", "ko": "🟡 시범 적용"},
    "rec.watch": {"vi": "🔵 THEO DÕI", "en": "🔵 WATCH", "zh": "🔵 关注", "ja": "🔵 注視", "ko": "🔵 주시"},
    "rec.ignore": {"vi": "⚪ BỎ QUA", "en": "⚪ SKIP", "zh": "⚪ 忽略", "ja": "⚪ 見送り", "ko": "⚪ 무시"},
    "rec.insufficient": {"vi": "🔵 CHƯA ĐỦ DỮ LIỆU, THEO DÕI TIẾP", "en": "🔵 NOT ENOUGH DATA, KEEP WATCHING",
                         "zh": "🔵 数据不足，继续关注", "ja": "🔵 データ不足、引き続き注視", "ko": "🔵 데이터 부족, 계속 주시"},
    "subject": {"vi": "StackScout — {week}", "en": "StackScout — {week}", "zh": "StackScout — {week}",
                "ja": "StackScout — {week}", "ko": "StackScout — {week}"},
}


def tr(key: str, lang: str, **params) -> str:
    entry = TEXT[key]
    return (entry.get(lang) or entry["en"]).format(**params)


def week_label(week: str, lang: str) -> str:
    y, w = week.split("-W")
    return tr("week", i18n.lang_code(lang), w=int(w), y=y)


# ---------------------------------------------------------------- channel-neutral model

def _item(b: dict, detail: str = "", verdicts: list[str] | None = None) -> dict:
    version = b.get("version") or ""
    first = (b.get("links") or [None])[0]
    return {
        "name": b["name"] + (f" {version}" if version and version not in b["name"] else ""),
        "detail": detail,
        "summary": b.get("summary") or "",
        "link": {"url": first["url"], "label": first.get("source") or "link", "official": bool(first.get("official"))}
        if first else None,
        "verdicts": verdicts or [],
    }


def _stack_verdict(b: dict, comparisons: dict, lang: str) -> list[str]:
    if b.get("category") in MODEL_CATEGORIES:
        return []
    for rival in b.get("rivals") or []:
        c = comparisons.get(f"{b['name'].casefold()}|{rival.casefold()}")
        if c:
            return [f"↳ vs {c['current']}: {tr('rec.' + c['recommendation'], lang)}"]
    return []


def _market_verdict(b: dict, market: dict, lang: str) -> list[str]:
    m = market.get(b["name"].casefold())
    names = [r["name"] for r in (m or {}).get("rivals") or []]
    return [tr("vs_rivals", lang, names=", ".join(names))] if names else []


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")


def period_label(period: str | None, when, week: str, lang: str) -> str:
    """"Tuần 47/2026" for a weekly digest, "Ngày 19/11/2026" daily, "Tháng 11/2026" monthly."""
    if period == "daily" and when:
        return tr("day", lang, d=when.day, m=when.month, y=when.year, mon=MONTHS[when.month - 1][:3])
    if period == "monthly" and when:
        return tr("month", lang, m=when.month, y=when.year, month=MONTHS[when.month - 1])
    return week_label(week, lang)


def build(report: dict, comparisons: dict | None = None, market: dict | None = None, lang: str | None = None,
          *, period: str | None = None, when=None) -> dict:
    lang = i18n.lang_code(lang or report.get("language"))
    comparisons, market = comparisons or {}, market or {}
    week = period_label(period, when, report["week"], lang)
    s = report["stats"]
    sections = []

    ai = report.get("ai_news") or []
    if ai:
        groups = []
        for g in AI_GROUP_ORDER:
            members = [b for b in ai if AI_GROUP_FROM_VI.get(b.get("group"), b.get("group")) == g]
            if members:
                groups.append({"title": tr("group." + g, lang), "items": [
                    _item(b, verdicts=_stack_verdict(b, comparisons, lang) + _market_verdict(b, market, lang))
                    for b in members]})
        sections.append({"title": tr("sec.ai", lang), "groups": groups, "empty": "", "note": ""})

    stack = report.get("stack") or report.get("compare_more") or []
    sections.append({"title": tr("sec.stack", lang), "empty": tr("stack.empty", lang),
                     "note": tr("stack.web", lang) if stack else "",
                     "groups": [{"title": "", "items": [
                         _item(b, tr("same_kind", lang, tool=b["rivals"][0]) if b.get("rivals") else "",
                               _stack_verdict(b, comparisons, lang)) for b in stack]}]})

    def eco(b: dict) -> str:
        label = ECOSYSTEM_LABEL.get(b.get("ecosystem", ""), b.get("ecosystem", ""))
        same = tr("same_kind", lang, tool=b["rivals"][0]) if b.get("rivals") else ""
        return ", ".join(x for x in (label, same) if x)

    plain: tuple[tuple[str, str, Callable[[dict], str]], ...] = (
        ("sec.updates", "updates", lambda b: ""),
        ("sec.other", "other_ecosystem", eco),
        ("sec.new", "new_areas", lambda b: b.get("category_label") or ""),
    )
    for title, key, detail in plain:
        sections.append({"title": tr(title, lang), "empty": tr("empty", lang), "note": "",
                         "groups": [{"title": "", "items": [_item(b, detail(b)) for b in report.get(key) or []]}]})

    return {
        "lang": lang,
        "week": report["week"],
        "subject": tr("subject", lang, week=week),
        "title": tr("title", lang, week=week),
        "intro": tr("intro", lang, items=s["items"], sources=s["sources"]),
        "sections": sections,
        "themes_title": tr("sec.themes", lang),
        "themes_empty": tr("themes.empty", lang),
        "themes": [{"title": t["title"], "summary": t["summary"], "links": t["links"]} for t in report.get("themes") or []],
        "errors": (report.get("errors") or [])[:5],
        "official": tr("official", lang),
    }


# ---------------------------------------------------------------- formatters

def pack(blocks: list[str], limit: int) -> list[str]:
    """Join blocks into messages under a channel's size limit."""
    messages, current = [], ""
    for block in blocks:
        if len(block) > limit:  # a single huge block: cut on line boundaries
            for line in block.split("\n"):
                if current and len(current) + len(line) + 1 > limit:
                    messages.append(current)
                    current = ""
                current = f"{current}\n{line}" if current else line[:limit]
            continue
        if current and len(current) + len(block) + 2 > limit:
            messages.append(current)
            current = ""
        current = f"{current}\n\n{block}" if current else block
    if current:
        messages.append(current)
    return messages


def _blocks(model: dict, *, bold: Callable[[str], str], esc: Callable[[str], str],
            link: Callable[[str, str], str], heading: Callable[[str], str]) -> list[str]:
    """The digest as text blocks, given how a channel writes bold, links and headings."""
    def line(it: dict) -> str:
        detail = f" ({esc(it['detail'])})" if it["detail"] else ""
        url = it["link"]
        ref = (f" → {link(url['url'], url['label'])}" + (f" ({model['official']})" if url["official"] else "")) if url else ""
        out = f"• {bold(esc(it['name']))}{detail}: {esc(it['summary'])}{ref}"
        return out + "".join(f"\n   {esc(v)}" for v in it["verdicts"])

    blocks = [f"📡 {bold(esc(model['title']))}\n{esc(model['intro'])}"]
    for sec in model["sections"]:
        lines = [heading(sec["title"])]
        items = [it for g in sec["groups"] for it in g["items"]]
        for g in sec["groups"]:
            if g["title"] and g["items"]:
                lines.append(bold(esc(g["title"])))
            lines += [line(it) for it in g["items"]]
        if not items:
            lines.append(esc(sec["empty"]))
        if sec["note"]:
            lines.append(esc(sec["note"]))
        blocks.append("\n".join(lines))
    themes = "\n\n".join(
        f"◆ {bold(esc(t['title']))}: {esc(t['summary'])}\n→ "
        + " · ".join(link(x["url"], x.get("source") or "link") for x in t["links"])
        for t in model["themes"]) or esc(model["themes_empty"])
    blocks.append(f"{heading(model['themes_title'])}\n{themes}")
    if model["errors"]:
        blocks.append("⚠️ " + "; ".join(esc(e) for e in model["errors"]))
    return blocks


def _html_esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _html_link(url: str, text: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{_html_esc(text)}</a>'


def telegram(model: dict, limit: int = 3900) -> list[str]:
    """Telegram HTML messages (4096-character limit per message)."""
    return pack(_blocks(model, bold=lambda s: f"<b>{s}</b>", esc=_html_esc, link=_html_link,
                        heading=lambda s: f"━━ {_html_esc(s)} ━━"), limit)


def _slack_esc(text: str) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack(model: dict, limit: int = 3500) -> list[str]:
    """Slack mrkdwn messages for an incoming webhook."""
    return pack(_blocks(model, bold=lambda s: f"*{s}*", esc=_slack_esc,
                        link=lambda u, t: f"<{u}|{_slack_esc(t).replace('|', '¦')}>",
                        heading=lambda s: f"*{_slack_esc(s)}*"), limit)


def _md_esc(text: str) -> str:
    out = str(text or "")
    for ch in "\\*_~`|>[]":
        out = out.replace(ch, "\\" + ch)
    return out


def discord(model: dict, limit: int = 1900) -> list[str]:
    """Discord markdown messages (2000-character limit; <url> hides link previews)."""
    return pack(_blocks(model, bold=lambda s: f"**{s}**", esc=_md_esc,
                        link=lambda u, t: f"[{_md_esc(t)}](<{u}>)",
                        heading=lambda s: f"__**{_md_esc(s)}**__"), limit)


def email(model: dict) -> tuple[str, str, str]:
    """(subject, plain text, HTML) for one email."""
    text = "\n\n".join(_blocks(model, bold=lambda s: s, esc=lambda s: str(s or ""),
                               link=lambda u, t: f"{t} <{u}>", heading=lambda s: s.upper()))
    body = "<br><br>".join(b.replace("\n", "<br>") for b in _blocks(
        model, bold=lambda s: f"<b>{s}</b>", esc=_html_esc, link=_html_link,
        heading=lambda s: f'<span style="font-size:15px;font-weight:700;color:#1d4ed8">{_html_esc(s)}</span>'))
    page = (f'<!doctype html><html lang="{model["lang"]}"><body style="font-family:-apple-system,Segoe UI,Roboto,'
            f'Helvetica,Arial,sans-serif;font-size:14px;line-height:1.55;color:#111827;max-width:720px">{body}</body></html>')
    return model["subject"], text, page


def webhook(model: dict) -> dict:
    """The model itself, for any service that takes JSON (n8n, Zapier, Make, ntfy bridges...)."""
    return {"source": "stackscout", **model}
