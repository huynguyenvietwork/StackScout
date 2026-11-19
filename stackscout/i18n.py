"""User-facing text on the server side, in every supported language.

Errors are raised with a message key (`UserError("source.exists")`) and
translated where they reach a person: the web API, the Telegram bot and the
digests, each in that person's language. The web page has its own
dictionary for the interface (static/index.html).
"""

from __future__ import annotations

from . import config

LANGS = tuple(config.LANGUAGES)  # vi, en, zh, ja, ko
FALLBACK = "en"

MESSAGES: dict[str, dict[str, str]] = {
    # ---- profile
    "profile.missing": {
        "vi": "Chưa có hồ sơ kỹ năng.", "en": "No skill profile yet.", "zh": "还没有技能档案。",
        "ja": "スキルプロフィールがまだありません。", "ko": "아직 스킬 프로필이 없습니다."},
    "profile.needs_skill": {
        "vi": "Hồ sơ cần ít nhất một kỹ năng.", "en": "A profile needs at least one skill.",
        "zh": "档案至少需要一项技能。", "ja": "プロフィールには少なくとも 1 つのスキルが必要です。",
        "ko": "프로필에는 스킬이 하나 이상 필요합니다."},
    "profile.no_such_skill": {
        "vi": "Không có kỹ năng này.", "en": "No such skill.", "zh": "没有这项技能。",
        "ja": "このスキルはありません。", "ko": "해당 스킬이 없습니다."},
    "import.too_large": {
        "vi": "File quá lớn.", "en": "The file is too large.", "zh": "文件太大。",
        "ja": "ファイルが大きすぎます。", "ko": "파일이 너무 큽니다."},
    "import.bad_yaml": {
        "vi": "YAML không hợp lệ: {problem}", "en": "Invalid YAML: {problem}", "zh": "YAML 无效：{problem}",
        "ja": "YAML が正しくありません: {problem}", "ko": "YAML이 올바르지 않습니다: {problem}"},
    "import.no_skills": {
        "vi": "Không tìm thấy kỹ năng nào. Kiểm tra file có đúng cấu trúc trong prompt không.",
        "en": "No skills found. Check that the file follows the structure in the prompt.",
        "zh": "没有找到任何技能。请检查文件是否符合提示词中的结构。",
        "ja": "スキルが見つかりません。ファイルがプロンプトの構造どおりか確認してください。",
        "ko": "스킬을 찾지 못했습니다. 파일이 프롬프트의 구조를 따르는지 확인하세요."},
    # ---- sources
    "source.not_found": {
        "vi": "Không tìm thấy nguồn này.", "en": "Source not found.", "zh": "找不到这个信息源。",
        "ja": "このソースが見つかりません。", "ko": "이 소스를 찾을 수 없습니다."},
    "source.exists": {
        "vi": "Nguồn này đã có trong danh sách của bạn.", "en": "This source is already in your list.",
        "zh": "这个信息源已在你的列表中。", "ja": "このソースはすでに一覧にあります。", "ko": "이 소스는 이미 목록에 있습니다."},
    "source.bad_url": {
        "vi": "Link không hợp lệ.", "en": "Invalid link.", "zh": "链接无效。", "ja": "リンクが正しくありません。",
        "ko": "링크가 올바르지 않습니다."},
    "source.unknown_host": {
        "vi": "Không tìm thấy tên miền {host}.", "en": "Domain {host} not found.", "zh": "找不到域名 {host}。",
        "ja": "ドメイン {host} が見つかりません。", "ko": "도메인 {host}을(를) 찾을 수 없습니다."},
    "source.private_host": {
        "vi": "Chỉ hỗ trợ link công khai trên Internet.", "en": "Only public Internet links are supported.",
        "zh": "只支持公开的互联网链接。", "ja": "公開されたインターネット上のリンクのみ対応しています。",
        "ko": "공개 인터넷 링크만 지원합니다."},
    "source.too_large": {
        "vi": "Trang quá lớn để đọc.", "en": "The page is too large to read.", "zh": "页面太大，无法读取。",
        "ja": "ページが大きすぎて読み込めません。", "ko": "페이지가 너무 커서 읽을 수 없습니다."},
    "source.unreachable": {
        "vi": "Không mở được link: {error}", "en": "Could not open the link: {error}", "zh": "无法打开链接：{error}",
        "ja": "リンクを開けませんでした: {error}", "ko": "링크를 열 수 없습니다: {error}"},
    "source.no_feed": {
        "vi": "Không tìm thấy RSS/Atom ở link này. Thử dán link trang blog, link RSS trực tiếp, hoặc link repo GitHub.",
        "en": "No RSS/Atom feed found at this link. Try the blog's page, a direct RSS link or a GitHub repo link.",
        "zh": "此链接没有找到 RSS/Atom。请尝试博客页面、RSS 直链或 GitHub 仓库链接。",
        "ja": "このリンクに RSS/Atom が見つかりません。ブログのページ、RSS の直接リンク、または GitHub リポジトリのリンクを試してください。",
        "ko": "이 링크에서 RSS/Atom을 찾지 못했습니다. 블로그 페이지, RSS 직접 링크 또는 GitHub 저장소 링크를 사용해 보세요."},
    "source.releases": {
        "vi": "{repo} (bản phát hành)", "en": "{repo} (releases)", "zh": "{repo}（版本发布）",
        "ja": "{repo}（リリース）", "ko": "{repo} (릴리스)"},
    "source.none_enabled": {
        "vi": "Bạn chưa bật nguồn tin nào.", "en": "You have no source turned on.", "zh": "你还没有开启任何信息源。",
        "ja": "有効なソースがありません。", "ko": "켜진 소스가 없습니다."},
    # ---- radar & comparisons
    "radar.running": {
        "vi": "Radar đang chạy, đợi chút nhé.", "en": "The radar is already running, hang on.",
        "zh": "雷达正在运行，请稍候。", "ja": "レーダーは実行中です。少しお待ちください。", "ko": "레이더가 실행 중입니다. 잠시 기다려 주세요."},
    "radar.failed": {
        "vi": "Chạy radar thất bại. Xem log của server để biết chi tiết.",
        "en": "The radar run failed. See the server log for details.", "zh": "雷达运行失败。详情请查看服务器日志。",
        "ja": "レーダーの実行に失敗しました。詳細はサーバーのログを確認してください。",
        "ko": "레이더 실행에 실패했습니다. 자세한 내용은 서버 로그를 확인하세요."},
    "report.missing": {
        "vi": "Không có bản tin tuần này.", "en": "There is no digest for this week.", "zh": "没有这一周的简报。",
        "ja": "この週のダイジェストはありません。", "ko": "이번 주 다이제스트가 없습니다."},
    "compare.unknown_tech": {
        "vi": "Không tìm thấy công nghệ này trong bản tin (bản tin cũ: hãy chạy lại radar).",
        "en": "This technology is not in the digest (old digest: run the radar again).",
        "zh": "简报中没有这项技术（旧简报：请重新运行雷达）。",
        "ja": "この技術はダイジェストにありません（古いダイジェストの場合はレーダーを再実行してください）。",
        "ko": "다이제스트에 이 기술이 없습니다(오래된 다이제스트라면 레이더를 다시 실행하세요)."},
    "compare.not_in_profile": {
        "vi": "Công cụ này không có trong hồ sơ của bạn.", "en": "This tool is not in your profile.",
        "zh": "你的档案中没有这个工具。", "ja": "このツールはプロフィールにありません。", "ko": "이 도구는 프로필에 없습니다."},
    "market.unknown_tech": {
        "vi": "Không tìm thấy model hoặc công cụ AI này trong bản tin.",
        "en": "This AI model or tool is not in the digest.", "zh": "简报中没有这个 AI 模型或工具。",
        "ja": "この AI モデル／ツールはダイジェストにありません。", "ko": "다이제스트에 이 AI 모델 또는 도구가 없습니다."},
    "ai.failed": {
        "vi": "AI chưa xử lý được lúc này. Thử lại sau ít phút nhé.",
        "en": "The AI could not process this right now. Try again in a few minutes.",
        "zh": "AI 暂时无法处理，请几分钟后重试。", "ja": "AI が今は処理できませんでした。数分後にもう一度お試しください。",
        "ko": "지금은 AI가 처리하지 못했습니다. 몇 분 후 다시 시도하세요."},
    "request.invalid": {
        "vi": "Dữ liệu gửi lên không hợp lệ ({problems}).", "en": "Invalid request ({problems}).",
        "zh": "提交的数据无效（{problems}）。", "ja": "送信されたデータが正しくありません（{problems}）。",
        "ko": "요청 데이터가 올바르지 않습니다({problems})."},
    "settings.bad_language": {
        "vi": "Ngôn ngữ không được hỗ trợ.", "en": "Unsupported language.", "zh": "不支持该语言。",
        "ja": "対応していない言語です。", "ko": "지원하지 않는 언어입니다."},
    # ---- notifications
    "notify.need_token": {
        "vi": "Dán bot token trước đã.", "en": "Paste the bot token first.", "zh": "请先粘贴机器人令牌。",
        "ja": "先にボットトークンを貼り付けてください。", "ko": "먼저 봇 토큰을 붙여 넣으세요."},
    "notify.need_fields": {
        "vi": "Điền các ô bắt buộc rồi lưu trước đã.", "en": "Fill in the required fields and save first.",
        "zh": "请先填写必填项并保存。", "ja": "必須項目を入力して保存してください。", "ko": "필수 항목을 입력하고 먼저 저장하세요."},
    "notify.bad_slack": {
        "vi": "URL webhook của Slack phải bắt đầu bằng https://hooks.slack.com/", "en": "Slack webhook URLs start with https://hooks.slack.com/",
        "zh": "Slack webhook URL 必须以 https://hooks.slack.com/ 开头", "ja": "Slack の Webhook URL は https://hooks.slack.com/ で始まります",
        "ko": "Slack 웹후크 URL은 https://hooks.slack.com/ 으로 시작해야 합니다"},
    "notify.bad_discord": {
        "vi": "URL webhook của Discord phải bắt đầu bằng https://discord.com/api/webhooks/", "en": "Discord webhook URLs start with https://discord.com/api/webhooks/",
        "zh": "Discord webhook URL 必须以 https://discord.com/api/webhooks/ 开头", "ja": "Discord の Webhook URL は https://discord.com/api/webhooks/ で始まります",
        "ko": "Discord 웹후크 URL은 https://discord.com/api/webhooks/ 로 시작해야 합니다"},
    "notify.bad_url": {
        "vi": "URL phải bắt đầu bằng https:// (hoặc http:// cho dịch vụ trên máy).", "en": "The URL must start with https:// (or http:// for a local service).",
        "zh": "URL 必须以 https:// 开头（本地服务可用 http://）。", "ja": "URL は https://（ローカルのサービスなら http://）で始めてください。",
        "ko": "URL은 https://(로컬 서비스는 http://)로 시작해야 합니다."},
    "notify.bad_value": {
        "vi": "Giá trị không hợp lệ: {field}", "en": "Invalid value: {field}", "zh": "无效的值：{field}",
        "ja": "値が正しくありません: {field}", "ko": "올바르지 않은 값: {field}"},
    "notify.not_configured": {
        "vi": "Chưa cấu hình kênh thông báo nào. Xem phần “Notifications” trong README.",
        "en": "No notification channel is configured. See “Notifications” in the README.",
        "zh": "尚未配置任何通知渠道。请参阅 README 中的“Notifications”部分。",
        "ja": "通知チャネルが設定されていません。README の「Notifications」を参照してください。",
        "ko": "설정된 알림 채널이 없습니다. README의 ‘Notifications’ 항목을 참고하세요."},
}


def lang_code(language: str | None) -> str:
    """Normalise "en-US", "zh_CN", "ja" ... to a supported code."""
    code = (language or "").replace("_", "-").split("-")[0].lower()
    return code if code in LANGS else FALLBACK


def t(key: str, lang: str | None = None, **params) -> str:
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(lang_code(lang)) or entry[FALLBACK]
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text


class UserError(ValueError):
    """An error meant for the person using StackScout: a message key, shown in
    their language with `text(lang)`. `str()` is the English text (logs)."""

    def __init__(self, key: str, **params):
        self.key, self.params = key, params
        super().__init__(t(key, FALLBACK, **params))

    def text(self, lang: str | None) -> str:
        return t(self.key, lang, **self.params)


def error_text(exc: Exception, lang: str | None) -> str:
    return exc.text(lang) if isinstance(exc, UserError) else str(exc)
