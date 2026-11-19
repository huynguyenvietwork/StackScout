"""Every message, button label and hint the Telegram bot sends, in each
supported language (vi, en, zh, ja, ko).

`tr(key, lang, **params)` picks the text for `lang` (unknown or missing ->
English) and fills `{params}`. Texts are Telegram HTML: user-provided values
must be `html.escape`d by the caller before they are passed in.
"""

from __future__ import annotations

from . import i18n

FALLBACK = "en"

# Shown on the /language buttons, each in its own language.
LANGUAGE_NAMES = {
    "vi": "Tiếng Việt",
    "en": "English",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
}

TEXT: dict[str, dict[str, str]] = {
    # ---------------------------------------------------------------- buttons
    "btn.confirm_ok": {
        "vi": "✅ Đúng rồi", "en": "✅ Looks right", "zh": "✅ 没错", "ja": "✅ 合っています", "ko": "✅ 맞아요"},
    "btn.confirm_edit": {
        "vi": "✏️ Sửa lại", "en": "✏️ Edit", "zh": "✏️ 修改", "ja": "✏️ 修正する", "ko": "✏️ 수정하기"},
    "btn.retry": {
        "vi": "🔁 Thử lại", "en": "🔁 Try again", "zh": "🔁 重试", "ja": "🔁 再試行", "ko": "🔁 다시 시도"},
    "btn.add": {
        "vi": "✅ Thêm", "en": "✅ Add", "zh": "✅ 添加", "ja": "✅ 追加", "ko": "✅ 추가"},
    "btn.cancel": {
        "vi": "✖️ Huỷ", "en": "✖️ Cancel", "zh": "✖️ 取消", "ja": "✖️ キャンセル", "ko": "✖️ 취소"},
    "btn.skip": {
        "vi": "⏭ Bỏ qua", "en": "⏭ Skip", "zh": "⏭ 跳过", "ja": "⏭ スキップ", "ko": "⏭ 건너뛰기"},
    "btn.done": {
        "vi": "✔️ Xong", "en": "✔️ Done", "zh": "✔️ 完成", "ja": "✔️ 完了", "ko": "✔️ 완료"},
    "btn.reset_yes": {
        "vi": "✅ Quay về mặc định", "en": "✅ Reset to default", "zh": "✅ 恢复默认",
        "ja": "✅ デフォルトに戻す", "ko": "✅ 기본값으로 되돌리기"},
    "btn.import_ok": {
        "vi": "✅ Gộp vào hồ sơ", "en": "✅ Merge into profile", "zh": "✅ 合并到档案",
        "ja": "✅ プロフィールに統合", "ko": "✅ 프로필에 합치기"},

    # ---------------------------------------------------------------- help & general
    "help": {
        "vi": (
            "<b>StackScout</b>: công nghệ mới, đối chiếu với stack của bạn.\n\n"
            "/profile: xem hồ sơ kỹ năng\n"
            "/add: thêm kỹ năng\n"
            "/remove: xoá kỹ năng\n"
            "/newprofile: tạo lại hồ sơ từ đầu\n"
            "/sources: xem, bật/tắt, xoá nguồn tin\n"
            "/addsource &lt;link&gt;: thêm nguồn (blog, RSS, repo GitHub)\n"
            "/reset: quay về bộ nguồn mặc định\n"
            "/radar: chạy bản tin tuần này ngay\n"
            "/language: đổi ngôn ngữ\n"
            "Gửi file .yaml: nhập hồ sơ tạo từ code hoặc CV\n"
            "/cancel: huỷ thao tác đang làm"
        ),
        "en": (
            "<b>StackScout</b>: new tech, matched against your stack.\n\n"
            "/profile: view your skill profile\n"
            "/add: add skills\n"
            "/remove: remove skills\n"
            "/newprofile: rebuild your profile from scratch\n"
            "/sources: view, turn on/off or delete sources\n"
            "/addsource &lt;link&gt;: add a source (blog, RSS, GitHub repo)\n"
            "/reset: go back to the default sources\n"
            "/radar: run this week's digest now\n"
            "/language: change language\n"
            "Send a .yaml file: import a profile made from your code or CV\n"
            "/cancel: cancel what you're doing"
        ),
        "zh": (
            "<b>StackScout</b>：新技术，对照你的技术栈。\n\n"
            "/profile：查看技能档案\n"
            "/add：添加技能\n"
            "/remove：删除技能\n"
            "/newprofile：从头重建档案\n"
            "/sources：查看、开关、删除信息源\n"
            "/addsource &lt;链接&gt;：添加信息源（博客、RSS、GitHub 仓库）\n"
            "/reset：恢复默认信息源\n"
            "/radar：立即生成本周简报\n"
            "/language：切换语言\n"
            "发送 .yaml 文件：导入根据代码或简历生成的档案\n"
            "/cancel：取消当前操作"
        ),
        "ja": (
            "<b>StackScout</b>：新しい技術を、あなたのスタックと照らし合わせてお届けします。\n\n"
            "/profile：スキルプロフィールを見る\n"
            "/add：スキルを追加\n"
            "/remove：スキルを削除\n"
            "/newprofile：プロフィールを最初から作り直す\n"
            "/sources：ソースの確認・オン/オフ・削除\n"
            "/addsource &lt;リンク&gt;：ソースを追加（ブログ、RSS、GitHub リポジトリ）\n"
            "/reset：デフォルトのソースに戻す\n"
            "/radar：今週のダイジェストを今すぐ作成\n"
            "/language：言語を変更\n"
            ".yaml ファイルを送信：コードや履歴書から作ったプロフィールを取り込む\n"
            "/cancel：操作をキャンセル"
        ),
        "ko": (
            "<b>StackScout</b>: 새로운 기술을 내 스택과 비교해 알려 드려요.\n\n"
            "/profile: 스킬 프로필 보기\n"
            "/add: 스킬 추가\n"
            "/remove: 스킬 삭제\n"
            "/newprofile: 프로필 처음부터 다시 만들기\n"
            "/sources: 소스 보기, 켜기/끄기, 삭제\n"
            "/addsource &lt;링크&gt;: 소스 추가 (블로그, RSS, GitHub 저장소)\n"
            "/reset: 기본 소스로 되돌리기\n"
            "/radar: 이번 주 다이제스트 바로 실행\n"
            "/language: 언어 변경\n"
            ".yaml 파일 보내기: 코드나 이력서로 만든 프로필 가져오기\n"
            "/cancel: 진행 중인 작업 취소"
        ),
    },
    "welcome_back": {
        "vi": "👋 Chào bạn quay lại!", "en": "👋 Welcome back!", "zh": "👋 欢迎回来！",
        "ja": "👋 おかえりなさい！", "ko": "👋 다시 오신 걸 환영해요!"},
    "ai_failed": {
        "vi": "😕 Mình chưa xử lý được lúc này. Bấm <b>Thử lại</b> sau ít phút nhé.",
        "en": "😕 I couldn't process that right now. Tap <b>Try again</b> in a few minutes.",
        "zh": "😕 暂时没能处理。过几分钟再点<b>重试</b>吧。",
        "ja": "😕 今はうまく処理できませんでした。数分後に<b>再試行</b>を押してください。",
        "ko": "😕 지금은 처리하지 못했어요. 몇 분 뒤에 <b>다시 시도</b>를 눌러 주세요."},
    "cancelled": {
        "vi": "Đã huỷ. Gõ /help để xem các lệnh.",
        "en": "Cancelled. Type /help to see the commands.",
        "zh": "已取消。输入 /help 查看命令。",
        "ja": "キャンセルしました。/help でコマンド一覧を見られます。",
        "ko": "취소했어요. /help 를 입력하면 명령어를 볼 수 있어요."},
    "no_profile": {
        "vi": "Bạn chưa có hồ sơ. Gõ /start để tạo nhé.",
        "en": "You don't have a profile yet. Type /start to create one.",
        "zh": "你还没有档案。输入 /start 来创建吧。",
        "ja": "まだプロフィールがありません。/start で作成してください。",
        "ko": "아직 프로필이 없어요. /start 를 입력해 만들어 주세요."},
    "processing": {
        "vi": "⏳ Đang xử lý…", "en": "⏳ Working on it…", "zh": "⏳ 处理中…",
        "ja": "⏳ 処理しています…", "ko": "⏳ 처리하는 중…"},
    "profile_unchanged": {
        "vi": "Đã huỷ, hồ sơ giữ nguyên.",
        "en": "Cancelled, your profile is unchanged.",
        "zh": "已取消，档案保持不变。",
        "ja": "キャンセルしました。プロフィールはそのままです。",
        "ko": "취소했어요. 프로필은 그대로예요."},
    "removed": {
        "vi": "Đã xoá {name}", "en": "Removed {name}", "zh": "已删除 {name}",
        "ja": "{name} を削除しました", "ko": "삭제했어요: {name}"},
    "error.generic": {
        "vi": "😕 Có lỗi xảy ra. Thử lại giúp mình nhé.",
        "en": "😕 Something went wrong. Please try again.",
        "zh": "😕 出错了，请再试一次。",
        "ja": "😕 エラーが発生しました。もう一度お試しください。",
        "ko": "😕 오류가 발생했어요. 다시 시도해 주세요."},

    # ---------------------------------------------------------------- onboarding
    "ob.intro": {
        "vi": (
            "👋 Chào bạn! Mình là <b>StackScout</b>. Mỗi tuần mình gửi bạn những công nghệ mới "
            "đáng chú ý, <b>đối chiếu với những gì bạn đang dùng</b>.\n\n"
            "Trả lời 4 câu ngắn để mình hiểu bạn nhé (khoảng 2 phút)."
        ),
        "en": (
            "👋 Hi! I'm <b>StackScout</b>. Every week I send you notable new tech, "
            "<b>matched against what you already use</b>.\n\n"
            "Answer 4 quick questions so I can get to know you (about 2 minutes)."
        ),
        "zh": (
            "👋 你好！我是 <b>StackScout</b>。每周我会给你推送值得关注的新技术，"
            "<b>并对照你正在用的技术</b>。\n\n"
            "回答 4 个简短的问题，让我了解一下你吧（大约 2 分钟）。"
        ),
        "ja": (
            "👋 こんにちは！<b>StackScout</b> です。毎週、注目の新しい技術を"
            "<b>あなたが今使っているものと照らし合わせて</b>お届けします。\n\n"
            "まずは 4 つの短い質問に答えてください（2 分ほどです）。"
        ),
        "ko": (
            "👋 안녕하세요! 저는 <b>StackScout</b>예요. 매주 주목할 만한 새 기술을 "
            "<b>지금 쓰고 계신 기술과 비교해서</b> 보내 드려요.\n\n"
            "짧은 질문 4개에 답해 주세요 (2분 정도 걸려요)."
        ),
    },
    "ob.q1": {
        "vi": "<b>1/4.</b> Bạn đang làm công việc gì?\n"
              "<i>Ví dụ: lập trình viên backend, sinh viên CNTT, data analyst, designer…</i>",
        "en": "<b>1/4.</b> What do you do?\n"
              "<i>e.g. backend developer, CS student, data analyst, designer…</i>",
        "zh": "<b>1/4.</b> 你现在做什么工作？\n"
              "<i>例如：后端开发、计算机专业学生、数据分析师、设计师…</i>",
        "ja": "<b>1/4.</b> どんなお仕事をしていますか？\n"
              "<i>例：バックエンドエンジニア、情報系の学生、データアナリスト、デザイナー…</i>",
        "ko": "<b>1/4.</b> 어떤 일을 하고 계세요?\n"
              "<i>예: 백엔드 개발자, 컴퓨터공학과 학생, 데이터 분석가, 디자이너…</i>",
    },
    "ob.q2": {
        "vi": "<b>2/4.</b> Bạn hay dùng ngôn ngữ, công nghệ, thư viện, công cụ nào?\n"
              "Cứ liệt kê thoải mái, viết tắt hay sai chính tả cũng không sao.\n"
              "<i>Ví dụ: c#, .net, entity framework, postgres, docker, react, excel</i>",
        "en": "<b>2/4.</b> Which languages, technologies, libraries and tools do you use?\n"
              "Just list them; abbreviations and typos are fine.\n"
              "<i>e.g. c#, .net, entity framework, postgres, docker, react, excel</i>",
        "zh": "<b>2/4.</b> 你常用哪些语言、技术、库和工具？\n"
              "随便列出来就行，缩写或拼错都没关系。\n"
              "<i>例如：c#, .net, entity framework, postgres, docker, react, excel</i>",
        "ja": "<b>2/4.</b> よく使う言語・技術・ライブラリ・ツールは？\n"
              "思いつくまま並べてください。略語やスペルミスも大丈夫です。\n"
              "<i>例：c#, .net, entity framework, postgres, docker, react, excel</i>",
        "ko": "<b>2/4.</b> 자주 쓰는 언어, 기술, 라이브러리, 도구는 뭔가요?\n"
              "편하게 나열해 주세요. 줄임말이나 오타도 괜찮아요.\n"
              "<i>예: c#, .net, entity framework, postgres, docker, react, excel</i>",
    },
    "ob.q3": {
        "vi": "<b>3/4.</b> Bạn đang làm dự án gì? Kể ngắn gọn là được.",
        "en": "<b>3/4.</b> What are you working on? A short description is enough.",
        "zh": "<b>3/4.</b> 你在做什么项目？简单说说就行。",
        "ja": "<b>3/4.</b> 今どんなプロジェクトに取り組んでいますか？簡単で大丈夫です。",
        "ko": "<b>3/4.</b> 어떤 프로젝트를 하고 계세요? 짧게 말씀해 주시면 돼요.",
    },
    "ob.q4": {
        "vi": "<b>4/4.</b> Bạn muốn theo dõi thêm chủ đề nào?\n"
              "<i>Ví dụ: AI agent, Rust, vector database, DevOps</i>",
        "en": "<b>4/4.</b> Any other topics you want to follow?\n"
              "<i>e.g. AI agents, Rust, vector databases, DevOps</i>",
        "zh": "<b>4/4.</b> 还想关注哪些主题？\n"
              "<i>例如：AI agent、Rust、向量数据库、DevOps</i>",
        "ja": "<b>4/4.</b> ほかにフォローしたいテーマはありますか？\n"
              "<i>例：AI エージェント、Rust、ベクトルデータベース、DevOps</i>",
        "ko": "<b>4/4.</b> 더 지켜보고 싶은 주제가 있나요?\n"
              "<i>예: AI 에이전트, Rust, 벡터 데이터베이스, DevOps</i>",
    },
    "ob.building": {
        "vi": "⏳ Đang sắp xếp hồ sơ của bạn…", "en": "⏳ Putting your profile together…",
        "zh": "⏳ 正在整理你的档案…", "ja": "⏳ プロフィールをまとめています…",
        "ko": "⏳ 프로필을 정리하고 있어요…"},
    "ob.no_skills": {
        "vi": "🤔 Mình chưa nhận ra công cụ hay công nghệ nào bạn dùng. "
              "Gõ lại giúp mình danh sách nhé, ví dụ: <i>python, excel, figma</i>",
        "en": "🤔 I couldn't spot any tools or technologies you use. "
              "Could you type the list again? e.g. <i>python, excel, figma</i>",
        "zh": "🤔 我没认出你用的工具或技术。请重新输入一下列表，例如：<i>python, excel, figma</i>",
        "ja": "🤔 使っているツールや技術が見つかりませんでした。"
              "もう一度リストを入力してください。例：<i>python, excel, figma</i>",
        "ko": "🤔 사용하시는 도구나 기술을 찾지 못했어요. "
              "목록을 다시 입력해 주세요. 예: <i>python, excel, figma</i>",
    },
    "ob.draft": {
        "vi": "Mình hiểu hồ sơ của bạn như sau:\n\n{profile}\n\n<b>Đúng chưa?</b>",
        "en": "Here's your profile as I understand it:\n\n{profile}\n\n<b>Is this right?</b>",
        "zh": "我理解的你的档案如下：\n\n{profile}\n\n<b>对吗？</b>",
        "ja": "あなたのプロフィールをこうまとめました：\n\n{profile}\n\n<b>合っていますか？</b>",
        "ko": "프로필을 이렇게 정리해 봤어요:\n\n{profile}\n\n<b>맞나요?</b>",
    },
    "ob.expired": {
        "vi": "Phiên này đã hết hạn, gõ /newprofile để làm lại nhé.",
        "en": "This session has expired. Type /newprofile to start over.",
        "zh": "本次会话已过期，输入 /newprofile 重新开始吧。",
        "ja": "このセッションは期限切れです。/newprofile でやり直してください。",
        "ko": "세션이 만료됐어요. /newprofile 을 입력해 다시 시작해 주세요.",
    },
    "ob.saved": {
        "vi": "✅ Đã lưu hồ sơ! Bản tin hằng tuần sẽ dựa trên hồ sơ này.\n\n"
              "Bạn có thể chỉnh lại bất cứ lúc nào:\n"
              "/profile: xem · /add: thêm · /remove: xoá",
        "en": "✅ Profile saved! Your weekly digest will be based on it.\n\n"
              "You can change it any time:\n"
              "/profile: view · /add: add · /remove: remove",
        "zh": "✅ 档案已保存！每周简报会以它为准。\n\n"
              "随时可以修改：\n"
              "/profile：查看 · /add：添加 · /remove：删除",
        "ja": "✅ プロフィールを保存しました！毎週のダイジェストはこれをもとに作ります。\n\n"
              "いつでも変更できます：\n"
              "/profile：見る · /add：追加 · /remove：削除",
        "ko": "✅ 프로필을 저장했어요! 매주 다이제스트는 이 프로필을 기준으로 만들어져요.\n\n"
              "언제든 수정할 수 있어요:\n"
              "/profile: 보기 · /add: 추가 · /remove: 삭제",
    },
    "ob.edit_prompt": {
        "vi": "✏️ Bạn muốn sửa gì? Cứ gõ tự nhiên.\n"
              "<i>Ví dụ: bỏ Docker, thêm Redis; React mình dùng thành thạo; mình là tech lead</i>",
        "en": "✏️ What should I change? Just say it naturally.\n"
              "<i>e.g. drop Docker, add Redis; I'm advanced in React; I'm a tech lead</i>",
        "zh": "✏️ 想改什么？直接说就行。\n"
              "<i>例如：去掉 Docker，加上 Redis；React 我很熟练；我是技术负责人</i>",
        "ja": "✏️ どこを直しますか？普段の言葉で書いてください。\n"
              "<i>例：Docker を外して Redis を追加；React は得意；テックリードです</i>",
        "ko": "✏️ 무엇을 고칠까요? 편하게 적어 주세요.\n"
              "<i>예: Docker 빼고 Redis 추가; React는 능숙해요; 저는 테크 리드예요</i>",
    },
    "ob.updating": {
        "vi": "⏳ Đang cập nhật…", "en": "⏳ Updating…", "zh": "⏳ 正在更新…",
        "ja": "⏳ 更新しています…", "ko": "⏳ 업데이트하는 중…"},

    # ---------------------------------------------------------------- /add, /profile, /remove
    "add.prompt": {
        "vi": "Bạn muốn thêm kỹ năng nào? Liệt kê thoải mái.\n<i>Ví dụ: redis, kafka, terraform</i>",
        "en": "Which skills do you want to add? List as many as you like.\n<i>e.g. redis, kafka, terraform</i>",
        "zh": "想添加哪些技能？随便列出来。\n<i>例如：redis, kafka, terraform</i>",
        "ja": "どのスキルを追加しますか？自由に並べてください。\n<i>例：redis, kafka, terraform</i>",
        "ko": "어떤 스킬을 추가할까요? 편하게 나열해 주세요.\n<i>예: redis, kafka, terraform</i>",
    },
    "add.ai_failed": {
        "vi": "😕 Mình chưa xử lý được lúc này. Thử lại /add sau ít phút nhé.",
        "en": "😕 I couldn't process that right now. Try /add again in a few minutes.",
        "zh": "😕 暂时没能处理，过几分钟再试一次 /add 吧。",
        "ja": "😕 今はうまく処理できませんでした。数分後にもう一度 /add を試してください。",
        "ko": "😕 지금은 처리하지 못했어요. 몇 분 뒤에 /add 를 다시 시도해 주세요.",
    },
    "add.nothing_new": {
        "vi": "Các kỹ năng này đã có trong hồ sơ của bạn rồi. Xem: /profile",
        "en": "These skills are already in your profile. See: /profile",
        "zh": "这些技能已经在你的档案里了。查看：/profile",
        "ja": "これらのスキルはすでにプロフィールにあります。確認：/profile",
        "ko": "이 스킬들은 이미 프로필에 있어요. 보기: /profile",
    },
    "add.confirm": {
        "vi": "Mình sẽ thêm:\n\n{skills}\n\n<b>Đúng chưa?</b>",
        "en": "I'll add:\n\n{skills}\n\n<b>Is this right?</b>",
        "zh": "将添加：\n\n{skills}\n\n<b>对吗？</b>",
        "ja": "次のスキルを追加します：\n\n{skills}\n\n<b>よろしいですか？</b>",
        "ko": "이렇게 추가할게요:\n\n{skills}\n\n<b>맞나요?</b>",
    },
    "add.expired": {
        "vi": "Phiên này đã hết hạn, gõ lại /add nhé.",
        "en": "This session has expired. Type /add again.",
        "zh": "本次会话已过期，请重新输入 /add。",
        "ja": "このセッションは期限切れです。もう一度 /add を送ってください。",
        "ko": "세션이 만료됐어요. /add 를 다시 입력해 주세요.",
    },
    "add.done": {
        "vi": "✅ Đã thêm vào hồ sơ. Xem: /profile",
        "en": "✅ Added to your profile. See: /profile",
        "zh": "✅ 已添加到档案。查看：/profile",
        "ja": "✅ プロフィールに追加しました。確認：/profile",
        "ko": "✅ 프로필에 추가했어요. 보기: /profile",
    },
    "profile.footer": {
        "vi": "/add: thêm · /remove: xoá · /newprofile: làm lại",
        "en": "/add: add · /remove: remove · /newprofile: start over",
        "zh": "/add：添加 · /remove：删除 · /newprofile：重新创建",
        "ja": "/add：追加 · /remove：削除 · /newprofile：作り直す",
        "ko": "/add: 추가 · /remove: 삭제 · /newprofile: 다시 만들기",
    },
    "remove.empty": {
        "vi": "Hồ sơ của bạn chưa có kỹ năng nào. Gõ /start hoặc /add nhé.",
        "en": "Your profile has no skills yet. Type /start or /add.",
        "zh": "你的档案还没有任何技能。输入 /start 或 /add 吧。",
        "ja": "プロフィールにまだスキルがありません。/start か /add を使ってください。",
        "ko": "프로필에 아직 스킬이 없어요. /start 나 /add 를 입력해 주세요.",
    },
    "remove.prompt": {
        "vi": "Bấm vào kỹ năng muốn xoá:", "en": "Tap a skill to remove it:", "zh": "点击要删除的技能：",
        "ja": "削除するスキルをタップしてください：", "ko": "삭제할 스킬을 눌러 주세요:"},
    "remove.stale": {
        "vi": "Danh sách đã thay đổi, mở lại /remove nhé.",
        "en": "The list has changed. Open /remove again.",
        "zh": "列表已变化，请重新打开 /remove。",
        "ja": "一覧が変わりました。もう一度 /remove を開いてください。",
        "ko": "목록이 바뀌었어요. /remove 를 다시 열어 주세요.",
    },
    "remove.all_gone": {
        "vi": "Đã xoá hết kỹ năng. Thêm lại bằng /add nhé.",
        "en": "All skills removed. Add some back with /add.",
        "zh": "所有技能都已删除。用 /add 重新添加吧。",
        "ja": "スキルをすべて削除しました。/add で追加し直せます。",
        "ko": "스킬을 모두 삭제했어요. /add 로 다시 추가할 수 있어요.",
    },
    "remove.done": {
        "vi": "✔️ Xong. Xem hồ sơ: /profile",
        "en": "✔️ Done. See your profile: /profile",
        "zh": "✔️ 完成。查看档案：/profile",
        "ja": "✔️ 完了。プロフィールを見る：/profile",
        "ko": "✔️ 완료. 프로필 보기: /profile",
    },

    # ---------------------------------------------------------------- sources
    "src.official": {
        "vi": " ·chính thức", "en": " ·official", "zh": " ·官方", "ja": " ·公式", "ko": " ·공식"},
    "src.show_off": {
        "vi": "➕ Xem {n} nguồn đang tắt", "en": "➕ Show {n} sources that are off",
        "zh": "➕ 查看 {n} 个已关闭的信息源", "ja": "➕ オフのソース {n} 件を見る", "ko": "➕ 꺼진 소스 {n}개 보기"},
    "src.back_on": {
        "vi": "◀ Về {n} nguồn đang bật", "en": "◀ Back to {n} sources that are on",
        "zh": "◀ 返回 {n} 个已开启的信息源", "ja": "◀ オンのソース {n} 件に戻る", "ko": "◀ 켜진 소스 {n}개로 돌아가기"},
    "src.intro": {
        "vi": "📰 <b>Nguồn tin của bạn</b>: {n} nguồn đang bật\n"
              "Gồm kênh chính chủ của Anthropic (Claude), OpenAI (Codex), Google (Gemini), các kênh AI "
              "nổi tiếng, và blog chính thức của công nghệ trong hồ sơ của bạn. Nguồn cộng đồng "
              "(Hacker News, repo GitHub mới nổi…) nằm ở mục đang tắt.\n"
              "Bấm tên nguồn để bật/tắt, 🗑 để xoá. Thêm nguồn: /addsource &lt;link&gt;",
        "en": "📰 <b>Your sources</b>: {n} turned on\n"
              "Includes the official channels of Anthropic (Claude), OpenAI (Codex) and Google (Gemini), "
              "well-known AI channels, and the official blogs of the tech in your profile. Community sources "
              "(Hacker News, trending GitHub repos…) are in the “off” list.\n"
              "Tap a source to turn it on/off, 🗑 to delete it. Add a source: /addsource &lt;link&gt;",
        "zh": "📰 <b>你的信息源</b>：已开启 {n} 个\n"
              "包括 Anthropic (Claude)、OpenAI (Codex)、Google (Gemini) 的官方渠道、知名 AI 频道，"
              "以及你档案中技术的官方博客。社区信息源（Hacker News、新兴 GitHub 仓库…）在已关闭列表里。\n"
              "点击信息源名称可开启/关闭，点 🗑 删除。添加信息源：/addsource &lt;链接&gt;",
        "ja": "📰 <b>あなたのソース</b>：{n} 件がオン\n"
              "Anthropic (Claude)、OpenAI (Codex)、Google (Gemini) の公式チャネル、有名な AI チャネル、"
              "プロフィールにある技術の公式ブログが含まれます。コミュニティのソース"
              "（Hacker News、注目の GitHub リポジトリ…）はオフの一覧にあります。\n"
              "ソース名をタップでオン/オフ、🗑 で削除。ソースを追加：/addsource &lt;リンク&gt;",
        "ko": "📰 <b>내 소스</b>: {n}개 켜짐\n"
              "Anthropic (Claude), OpenAI (Codex), Google (Gemini)의 공식 채널, 유명 AI 채널, "
              "그리고 프로필에 있는 기술의 공식 블로그가 들어 있어요. 커뮤니티 소스"
              "(Hacker News, 뜨는 GitHub 저장소…)는 꺼진 목록에 있어요.\n"
              "소스 이름을 누르면 켜기/끄기, 🗑 는 삭제예요. 소스 추가: /addsource &lt;링크&gt;",
    },
    "src.turned_on": {
        "vi": "Đã bật", "en": "Turned on", "zh": "已开启", "ja": "オンにしました", "ko": "켰어요"},
    "src.turned_off": {
        "vi": "Đã tắt", "en": "Turned off", "zh": "已关闭", "ja": "オフにしました", "ko": "껐어요"},
    "src.stale": {
        "vi": "Danh sách đã thay đổi, mở lại /sources nhé.",
        "en": "The list has changed. Open /sources again.",
        "zh": "列表已变化，请重新打开 /sources。",
        "ja": "一覧が変わりました。もう一度 /sources を開いてください。",
        "ko": "목록이 바뀌었어요. /sources 를 다시 열어 주세요.",
    },
    "addsource.usage": {
        "vi": "Dán link sau lệnh, ví dụ:\n/addsource https://blog.cloudflare.com\n"
              "/addsource https://github.com/HangfireIO/Hangfire",
        "en": "Paste a link after the command, e.g.:\n/addsource https://blog.cloudflare.com\n"
              "/addsource https://github.com/HangfireIO/Hangfire",
        "zh": "在命令后面粘贴链接，例如：\n/addsource https://blog.cloudflare.com\n"
              "/addsource https://github.com/HangfireIO/Hangfire",
        "ja": "コマンドの後にリンクを貼ってください。例：\n/addsource https://blog.cloudflare.com\n"
              "/addsource https://github.com/HangfireIO/Hangfire",
        "ko": "명령어 뒤에 링크를 붙여 주세요. 예:\n/addsource https://blog.cloudflare.com\n"
              "/addsource https://github.com/HangfireIO/Hangfire",
    },
    "addsource.added": {
        "vi": "✅ Đã thêm <b>{name}</b>. Xem: /sources",
        "en": "✅ Added <b>{name}</b>. See: /sources",
        "zh": "✅ 已添加 <b>{name}</b>。查看：/sources",
        "ja": "✅ <b>{name}</b> を追加しました。確認：/sources",
        "ko": "✅ <b>{name}</b> 추가했어요. 보기: /sources",
    },
    "reset.confirm": {
        "vi": "Quay về bộ nguồn mặc định (theo hồ sơ của bạn)? "
              "Các nguồn bạn đã thêm và các lựa chọn bật/tắt sẽ bị xoá.",
        "en": "Go back to the default sources (based on your profile)? "
              "Sources you added and your on/off choices will be cleared.",
        "zh": "恢复默认信息源（根据你的档案）？你添加的信息源和开关设置都会被清除。",
        "ja": "デフォルトのソース（プロフィールに基づく）に戻しますか？追加したソースとオン/オフの設定は消えます。",
        "ko": "기본 소스(프로필 기준)로 되돌릴까요? 추가한 소스와 켜기/끄기 설정이 지워져요.",
    },
    "reset.done": {
        "vi": "✅ Đã quay về bộ nguồn mặc định. Xem: /sources",
        "en": "✅ Back to the default sources. See: /sources",
        "zh": "✅ 已恢复默认信息源。查看：/sources",
        "ja": "✅ デフォルトのソースに戻しました。確認：/sources",
        "ko": "✅ 기본 소스로 되돌렸어요. 보기: /sources",
    },
    "reset.cancelled": {
        "vi": "Đã huỷ, danh sách nguồn giữ nguyên.",
        "en": "Cancelled, your sources are unchanged.",
        "zh": "已取消，信息源列表保持不变。",
        "ja": "キャンセルしました。ソースはそのままです。",
        "ko": "취소했어요. 소스 목록은 그대로예요.",
    },

    # ---------------------------------------------------------------- radar
    "radar.running": {
        "vi": "Radar đang chạy cho bạn, đợi chút nhé.",
        "en": "The radar is already running for you, hang on.",
        "zh": "雷达正在为你运行，请稍等。",
        "ja": "レーダーを実行中です。少しお待ちください。",
        "ko": "레이더가 실행 중이에요. 잠시만 기다려 주세요.",
    },
    "radar.started": {
        "vi": "⏳ Đang chạy radar tuần này: gom tin, phân loại, tìm bài so sánh. Mất vài phút…",
        "en": "⏳ Running this week's radar: collecting news, classifying, finding comparisons. "
              "This takes a few minutes…",
        "zh": "⏳ 正在运行本周雷达：收集资讯、分类、查找对比文章。需要几分钟…",
        "ja": "⏳ 今週のレーダーを実行中：ニュース収集、分類、比較記事の検索。数分かかります…",
        "ko": "⏳ 이번 주 레이더를 실행하는 중: 소식 모으기, 분류, 비교 글 찾기. 몇 분 걸려요…",
    },
    "radar.failed": {
        "vi": "😕 Chạy radar thất bại. Thử lại sau nhé.",
        "en": "😕 The radar run failed. Try again later.",
        "zh": "😕 雷达运行失败，稍后再试吧。",
        "ja": "😕 レーダーの実行に失敗しました。あとでもう一度お試しください。",
        "ko": "😕 레이더 실행에 실패했어요. 나중에 다시 시도해 주세요.",
    },

    # ---------------------------------------------------------------- YAML import
    "import.too_large": {
        "vi": "File quá lớn (tối đa 200 KB).", "en": "The file is too large (max 200 KB).",
        "zh": "文件太大（最大 200 KB）。", "ja": "ファイルが大きすぎます（最大 200 KB）。",
        "ko": "파일이 너무 커요 (최대 200 KB)."},
    "import.added": {
        "vi": "Sẽ thêm {n} kỹ năng mới:\n\n{skills}",
        "en": "{n} new skills will be added:\n\n{skills}",
        "zh": "将添加 {n} 项新技能：\n\n{skills}",
        "ja": "新しいスキルを {n} 件追加します：\n\n{skills}",
        "ko": "새 스킬 {n}개를 추가할게요:\n\n{skills}",
    },
    "import.nothing_new": {
        "vi": "Không có kỹ năng mới, chỉ bổ sung thông tin cho kỹ năng đã có.",
        "en": "No new skills, just extra details for the ones you already have.",
        "zh": "没有新技能，只补充已有技能的信息。",
        "ja": "新しいスキルはありません。今あるスキルの情報を補うだけです。",
        "ko": "새 스킬은 없고, 기존 스킬 정보만 보완해요.",
    },
    "import.confirm": {
        "vi": "{summary}\n\nHồ sơ hiện tại được giữ nguyên, chỉ gộp thêm. <b>Gộp chứ?</b>",
        "en": "{summary}\n\nYour current profile stays as it is; this only adds to it. <b>Merge?</b>",
        "zh": "{summary}\n\n现有档案保持不变，只做合并。<b>合并吗？</b>",
        "ja": "{summary}\n\n今のプロフィールはそのままで、追加で統合するだけです。<b>統合しますか？</b>",
        "ko": "{summary}\n\n현재 프로필은 그대로 두고 합치기만 해요. <b>합칠까요?</b>",
    },
    "import.done": {
        "vi": "✅ Đã gộp vào hồ sơ. Xem: /profile",
        "en": "✅ Merged into your profile. See: /profile",
        "zh": "✅ 已合并到档案。查看：/profile",
        "ja": "✅ プロフィールに統合しました。確認：/profile",
        "ko": "✅ 프로필에 합쳤어요. 보기: /profile",
    },

    # ---------------------------------------------------------------- /language
    "language.prompt": {
        "vi": "🌐 Chọn ngôn ngữ cho bot:", "en": "🌐 Choose the bot's language:",
        "zh": "🌐 选择机器人的语言：", "ja": "🌐 ボットの言語を選んでください：",
        "ko": "🌐 봇 언어를 선택해 주세요:"},
    "language.saved": {
        "vi": "✅ Đã chuyển sang Tiếng Việt.", "en": "✅ Switched to English.",
        "zh": "✅ 已切换为中文。", "ja": "✅ 日本語に切り替えました。", "ko": "✅ 한국어로 바꿨어요."},
}


def tr(key: str, lang: str | None = None, **params) -> str:
    """The text for `key` in `lang` (falls back to English), with `{params}` filled."""
    entry = TEXT.get(key)
    if entry is None:
        return key
    text = entry.get(i18n.lang_code(lang)) or entry[FALLBACK]
    try:
        return text.format(**params) if params else text
    except (KeyError, IndexError):
        return text
