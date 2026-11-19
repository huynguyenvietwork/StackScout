# Contributing to StackScout

Thanks for helping! Issues, ideas and pull requests are all welcome.

## Run it locally

```bash
git clone <your fork> && cd stackscout
uv sync                      # Python 3.11+, https://docs.astral.sh/uv/
cp .env.example .env         # set ANTHROPIC_API_KEY, or log in to the `claude` CLI
uv run main.py web           # http://127.0.0.1:8000
uv run pytest -q             # the whole suite runs offline, no AI calls
```

Tests never call a real AI, feed or messaging service: they replace `ai.complete`,
`httpx` transports and SMTP with fakes. Please keep it that way.

## Good first contributions

- **A source** for a technology people use: add it to `config/industries.yaml`
  (`tier: stack` with `match` rules, or `tier: extra`). Prefer official blogs and release feeds.
- **A notification channel**: one formatter in `stackscout/render.py` and one sender in
  `stackscout/notify.py`, plus a test with a fake transport.
- **A language**: add it to `config.LANGUAGES`, then to the dictionaries in
  `static/index.html` (`I18N`), `stackscout/i18n.py`, `stackscout/render.py` and `stackscout/bot_text.py`.
  A test fails if a key is missing.

## Rules the project keeps

- **Every claim needs a link.** Comparison rules are enforced in code (`compare.finalize`), not trusted to the AI.
- **Privacy:** a profile stores technology names and levels only. Never add fields that hold
  project names, what someone works on, or anything about their employer.
- **Secrets stay in `.env`.** Nothing secret goes through the web page or into logs.
- User-facing text goes in all five languages.
- Keep changes small and focused; explain the "why" in the PR.

## Reporting a security problem

See [SECURITY.md](SECURITY.md). Please do not open a public issue for it.
