# Development Dockerfile
# =====================
# Lightweight image for local Docker development.
# App code is bind-mounted at runtime (not COPY'd) for live reloading.
#
# For production, use Dockerfile.production (multi-stage, non-root user).

FROM python:3.12-slim

# Install build tools needed by some Python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency files and install (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-root

# App code is bind-mounted via docker-compose volumes
# No COPY of application code here

ARG APP_PORT=8000
EXPOSE $APP_PORT

CMD ["uv", "run", "python", "main.py"]
