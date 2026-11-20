# AGENTS.md

Instructions for AI coding assistants (Claude Code, Cursor, Codex, Copilot, Gemini CLI…) working in this repository. People: see [README.md](README.md).

StackScout is a self-hosted weekly tech radar: a FastAPI web UI on `127.0.0.1:8000`, a scheduler that sends digests, and an optional Telegram bot. Python 3.11+, managed with [uv](https://docs.astral.sh/uv/).

## Installing it for a user

Goal: `main.py doctor` shows no ❌, then the web UI is open at http://127.0.0.1:8000.

1. **Pick the path** from what the machine has (check, don't ask):
   - `uv` available, or installable → **uv path** (simplest, and the only one that can use the `claude` CLI instead of an API key).
   - Docker running and the user has an Anthropic API key → **Docker path**.
   - Neither: install uv (`curl -LsSf https://astral.sh/uv/install.sh | sh` on macOS/Linux, `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` on Windows), after telling the user what you are installing.
2. **Get the code**: `git clone https://github.com/huynguyenvietwork/StackScout && cd StackScout`.
3. **uv path**
   ```bash
   uv sync
   uv run main.py doctor
   ```
   - If the AI backend line is ❌: ask the user to run `uv run main.py setup` **in their own terminal** (it asks for the key with hidden input). In Claude Code they can type `! uv run main.py setup`. If `claude` is installed and logged in, no key is needed at all.
   - Then `uv run main.py web` (keep it running in the background) and open http://127.0.0.1:8000.
4. **Docker path**
   ```bash
   cp .env.example .env      # then the USER adds ANTHROPIC_API_KEY=... to .env themselves
   docker compose up -d --build --wait
   docker compose exec web uv run --no-sync main.py doctor
   ```
   Or without cloning: `docker run -d --name stackscout -p 127.0.0.1:8000:8000 -e ANTHROPIC_API_KEY -v stackscout_data:/app/data -v stackscout_reports:/app/reports ghcr.io/huynguyenvietwork/stackscout` (the key comes from the user's shell environment).
5. **Finish**: run `main.py doctor --online` once to prove the key or CLI works (free with an API key), open the web UI, and tell the user the next step: create the profile in the browser (about 2 minutes), then **Run this week's radar**.

### Rules while installing

- **Never ask for an API key, bot token, SMTP password or webhook URL in the chat**, and never type one into a command line or a file yourself. The user enters secrets with `main.py setup`, in `.env` with their own editor, or in the web UI's Notifications tab. Chat transcripts are sent to the AI provider.
- **Never commit `.env`**, `data/` or `reports/` (they are git-ignored; keep it that way).
- **Keep it on 127.0.0.1.** The web UI has no login. Do not use `--host 0.0.0.0`, change the compose port binding, or open a tunnel unless the user asks and understands that.
- **Running the radar costs the user money** (AI calls with web search). Don't start radars, comparisons or `main.py digest` repeatedly to "test"; `doctor --online` is the free check.
- Don't change notification settings, schedules or the profile for the user without asking.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `doctor`: no ANTHROPIC_API_KEY and no `claude` CLI | user runs `uv run main.py setup`, or installs Claude Code and logs in |
| `doctor --online`: key rejected / model not found | user copies the key again; or sets `STACKSCOUT_MODEL` to a model their key can use |
| Port 8000 in use | StackScout may already be running: open it; or `uv run main.py web --port 8001` |
| Docker: the `claude` CLI is not in the image | the Docker path needs `ANTHROPIC_API_KEY` in `.env` |
| Docker: cannot write `/app/data` | use the named volumes from `docker-compose.yml`, not a bind-mounted `./data` |

## Working on the code

- Tests: `uv run pytest -q`. They are offline and never call an AI; keep it that way (mock `stackscout.ai`).
- Layout: see "Project layout" in README.md. Prompts live in `prompts/*.md`, not in code. Every server message has all 5 languages (`stackscout/i18n.py`, `bot_text.py`, `render.py`, and the `I18N` object in `stackscout/static/index.html`).
- Rules that must stay true:
  - comparison claims without a valid source link are dropped in code (`compare.finalize`, `compare.finalize_market`);
  - the profile stores only technology names, categories, ecosystems and levels (`profile.clean`, `profile.scrub`);
  - secrets are never returned to the browser (`notify.public_settings`).
- `main` is protected: work on a branch, open a PR, CI (`test`, `docker`) must pass, squash merge. Update `CHANGELOG.md` under *Unreleased*.
