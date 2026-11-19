# Security policy

## Reporting a vulnerability

Please report it privately through GitHub: **Security → Report a vulnerability** on this
repository. Do not open a public issue. You will get an answer within a week.

## What StackScout protects, and how

- **Your profile** holds technology names and levels only; project names, employers and
  what you work on are dropped on save and on import (`profile.clean`).
- **Secrets** (API keys, bot token, SMTP password, webhook URLs) are sent only to your
  self-hosted StackScout server, stored locally with owner-only permissions (`.env`, or
  `data/users/<id>/notify.yaml` when entered in the Notifications tab), and never returned
  to the browser after saving: the page only learns whether a secret is set.
- **Custom sources**: links you add are fetched only if they resolve to public addresses,
  checked again on every request (`sources.check_public_host`), to prevent SSRF.
- **AI steps** run without tools, except comparisons, which get web search and fetch only.
  With the `claude` CLI they run in an empty temporary directory.
- **The web UI has no login.** It listens on 127.0.0.1 (Docker publishes it on 127.0.0.1 too).
  Do not expose it to a network without putting authentication in front of it.
- **The Telegram bot** answers only the user ids in `STACKSCOUT_ALLOWED_USERS`.

## Supported versions

Only the latest release gets security fixes.
