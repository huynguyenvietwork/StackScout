# Changelog

All notable changes to StackScout are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Comparisons open on their own full page (browser Back returns to the same place in the list), with sources and the week's original news beside them; a model's page starts with a table of its rivals.
- More detailed comparisons: up to 5 pros and 5 cons, key numbers side by side, how hard it is to switch, longer "what's new" and "for you" notes. Older comparisons show a **Compare again** button.

## [0.1.1] - 2026-11-19

### Changed

- `LICENSE` now names the copyright holder: "huynguyenvietwork and StackScout contributors". The license is still MIT, with unchanged terms.

## [0.1.0] - 2026-11-19

First public release. StackScout is designed for personal self-hosting: one local profile, no login.

### Added

- **Profile in your own words**: AI normalises technologies to canonical names and levels, you confirm before saving. Import from code or a CV with the included prompt.
- **Curated sources** (~60 live feeds): first-party AI channels always on, official blogs and release feeds of your technologies on automatically, community sources optional; add any blog, RSS feed or GitHub repo.
- **Weekly radar**: overview of the week by type, new AI models and tools, your tools' updates, other ecosystems, new areas and a roundup.
- **Vs. my stack**: new tools of the same kind as yours are compared automatically (adopt, trial, watch, skip), grouped by your skills; compare with any other tool from the menu.
- **New AI models vs. rivals**: each new model is compared with its 3–5 strongest competitors.
- **Source rules enforced in code**: every pro and con cites a source; fewer than 2 sources means "not enough data"; no independent source caps confidence.
- **Notifications tab**: daily, weekly or monthly digests on Telegram, email (SMTP), Slack, Discord or a JSON webhook, with step-by-step setup, test messages and a delivery log. The web server sends on schedule; no cron needed.
- **5 languages** (English, Tiếng Việt, 中文, 日本語, 한국어) for the interface, AI-written content, digests and the Telegram bot; light and dark themes.
- **AI backends**: Anthropic API key, or a logged-in Claude Code CLI (any stdin/stdout CLI through `STACKSCOUT_AI_CMD`).
- **Docker** setup (`docker compose up -d`), a read-only demo, CI running tests and the Docker build.

### Privacy and security

- Profiles store technology names and levels only; project names, `used_in` and `evidence` are dropped on save and import.
- Secrets are sent only to your self-hosted server, stored with owner-only permissions and never returned to the browser.
- Custom source URLs must resolve to public addresses (SSRF guard); the Telegram bot answers only allowed user ids.

### Upgrading from a pre-release checkout

- Profiles lose their `projects`, `used_in` and `evidence` fields the next time they are saved.
- Notification channels can now be set in the Notifications tab; `.env` values still fill empty fields.
- `STACKSCOUT_DIGEST_DAY` and `STACKSCOUT_DIGEST_TIME` are replaced by the schedule in the Notifications tab, and the separate `scheduler` service is gone from `docker-compose.yml` (the web service sends on schedule).

[0.1.1]: https://github.com/huynguyenvietwork/StackScout/releases/tag/v0.1.1
[0.1.0]: https://github.com/huynguyenvietwork/StackScout/releases/tag/v0.1.0
