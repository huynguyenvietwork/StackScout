# StackScout (Tiếng Việt)

**Công nghệ mới, đối chiếu với stack của bạn.** · [English](README.md) · [Xem demo](https://huynguyenvietwork.github.io/StackScout/)

StackScout là radar công nghệ hằng tuần: đọc các nguồn chính chủ và uy tín, chọn ra tin liên quan tới **đúng những công cụ bạn đang dùng**, rồi tự so sánh từng công nghệ mới với chúng, mọi nhận định đều có link nguồn.

- **Model & công cụ AI mới** từ kênh chính chủ (Anthropic, OpenAI, Google DeepMind, Gemini…), mỗi cái được so với **3–5 đối thủ mạnh nhất**: hơn, kém, nên chọn khi nào.
- **So với stack**: công nghệ mới cùng loại với công cụ bạn dùng được **tự động so sánh**: nên chuyển, thử nghiệm, theo dõi hay bỏ qua. Ưu tiên benchmark độc lập.
- **Gửi bản tin hằng tuần** qua web, Telegram, email, Slack, Discord hoặc webhook.
- **5 ngôn ngữ**: Tiếng Việt, English, 中文, 日本語, 한국어.
- **Bảo mật**: hồ sơ chỉ lưu tên công nghệ và mức độ, không lưu tên dự án hay thông tin công ty.

## Chạy thử

```bash
git clone https://github.com/huynguyenvietwork/StackScout && cd StackScout
cp .env.example .env     # điền ANTHROPIC_API_KEY (hoặc để trống nếu đã đăng nhập Claude Code CLI)
docker compose up -d     # mở http://127.0.0.1:8000
```

Không dùng Docker: `uv sync && uv run main.py web`. Hướng dẫn đầy đủ (kênh thông báo, bot Telegram, lịch gửi) ở [README.md](README.md).

Muốn dùng **bản online không cần cài đặt**? [Đăng ký ở đây](../../issues/new?template=hosted_waitlist.yml), số người đăng ký sẽ quyết định có làm hay không. Góp ý, thêm nguồn tin, thêm ngôn ngữ: xem [CONTRIBUTING.md](CONTRIBUTING.md).
