import pytest

# Settings from the developer's shell must not change which code path a test takes.
ISOLATED_ENV = (
    "ANTHROPIC_API_KEY", "STACKSCOUT_AI_BACKEND", "STACKSCOUT_MODEL", "STACKSCOUT_EFFORT",
    "TELEGRAM_BOT_TOKEN", "STACKSCOUT_TELEGRAM_CHAT_ID", "SMTP_HOST", "STACKSCOUT_EMAIL_TO",
    "STACKSCOUT_SLACK_WEBHOOK_URL", "STACKSCOUT_DISCORD_WEBHOOK_URL", "STACKSCOUT_WEBHOOK_URL",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    for name in ISOLATED_ENV:
        monkeypatch.delenv(name, raising=False)
