# The API and the worker of the rebuilt app (deploy/README.md): one image, two commands
# (deploy/compose.yaml). The dependencies are exactly uv.lock's, plus the `otel` extra so a
# deployed environment can send telemetry; whether it does is up to its environment variables.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# The dependencies in a layer of their own, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra otel --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev --extra otel --no-editable
ENV PATH="/app/.venv/bin:$PATH"

# Photos go to a volume mounted at /data/blobs; a new volume takes this directory's owner.
RUN useradd --create-home --uid 1000 app && mkdir -p /data/blobs && chown app /data/blobs
USER app
EXPOSE 8000

# opentelemetry-instrument loads the SDK and the FastAPI, psycopg and urllib instrumentation
# from OTEL_* variables; with OTEL_SDK_DISABLED=true everything stays a no-op. --proxy-headers:
# behind nginx, the client address and scheme come from X-Forwarded-*.
CMD ["opentelemetry-instrument", "uvicorn", "cojidaily.main:create_app", "--factory", "--host", "0.0.0.0", \
     "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
