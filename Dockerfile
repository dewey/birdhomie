# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (all packages have pre-built wheels, no build-essential needed)
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

# Copy source code and install project
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev


FROM python:3.13-slim-bookworm AS runtime

# Install runtime dependencies for OpenCV and video processing
RUN --mount=type=cache,target=/var/cache/apt,id=apt-runtime,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        ffmpeg \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtual environment and app from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/migrations /app/migrations

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

CMD ["python", "-m", "birdhomie.app"]
