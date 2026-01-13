# syntax=docker/dockerfile:1
#
# Uses pre-built base image with ML dependencies for faster CI builds.
# Base image: ghcr.io/dewey/birdhomie-base (see Dockerfile.base)
#

FROM ghcr.io/dewey/birdhomie-base:latest

WORKDIR /app

# Copy source code and project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY README.md ./

# Sync any updated dependencies and install the project
# Base image has most deps cached, so this is fast
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# Create data directory
RUN mkdir -p /app/data

EXPOSE 5000

# Environment variables with defaults (can be overridden at runtime)
ENV PORT=5000
ENV GUNICORN_WORKERS=2

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD uv run python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"5000\")}/')" || exit 1

# Use gunicorn for production with config file that handles scheduler
CMD ["uv", "run", "gunicorn", "--config", "src/birdhomie/gunicorn.conf.py", "birdhomie.app:app"]
