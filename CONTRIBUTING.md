# Contributing to StackScout

Thanks for helping! Issues, ideas and pull requests are all welcome. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Questions, bugs and ideas

- **A question** or an idea you want to talk through: [Discussions](https://github.com/huynguyenvietwork/StackScout/discussions).
- **A bug**: open an issue with the *Bug report* form. Include the server log lines, with API keys,
  tokens, webhook URLs and anything personal removed.
- **A feature request**: the *Feature request* form. Say what you are trying to do, not only the fix you have in mind.
- **A security problem**: report it privately, see [SECURITY.md](SECURITY.md).

## How a change gets into `main`

`main` is protected: nobody pushes to it directly, the maintainer included.

1. Fork the repository and create a branch from `main` (`fix/…`, `feat/…`, `docs/…`).
2. Make the change, with a test when it changes behaviour, and run `uv run pytest -q`.
3. Open a pull request against `main` and fill in the template: what changes and why, and how you tested it.
4. CI runs two checks, `test` (the test suite) and `docker` (the image builds). For a first-time
   contributor, a maintainer approves the run first; this is a GitHub safeguard, not a judgement on your PR.
5. Both checks must be green and the branch up to date with `main` (use **Update branch** on the PR if asked).
6. A maintainer reviews and **squash-merges** the PR: it lands as one commit titled after the PR,
   so a clear PR title matters. The branch is deleted after the merge.

## Run it locally

```bash
git clone <your fork> && cd StackScout
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
- **Secrets stay on the user's server.** They are sent only to the self-hosted StackScout server,
  stored in `.env` or owner-only files under `data/`, never written to logs and never returned to the
  browser after saving: the API only says whether a secret is set.
- User-facing text goes in all five languages.
- Keep changes small and focused; explain the "why" in the PR.

## Reporting a security problem

See [SECURITY.md](SECURITY.md). Please do not open a public issue for it.
