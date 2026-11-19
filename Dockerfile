# StackScout: web UI, weekly scheduler and Telegram bot from one image.
# AI runs through the Anthropic API here (set ANTHROPIC_API_KEY in .env):
# the `claude` CLI is not installed in the container.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    STACKSCOUT_AI_BACKEND=api

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .

RUN useradd --create-home --uid 10001 stackscout && mkdir -p data reports && chown -R stackscout data reports
USER stackscout

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "main.py", "web", "--host", "0.0.0.0", "--port", "8000"]
