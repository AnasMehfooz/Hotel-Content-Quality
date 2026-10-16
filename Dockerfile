# Pipeline image: Dagster (UI + daemon) by default; the dashboard service reuses it.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HCQ_PROJECT_ROOT=/app \
    DAGSTER_HOME=/app/data/dagster_home \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev && mkdir -p data/dagster_home

EXPOSE 3000 8501
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-m", "hcq.orchestration.definitions"]
