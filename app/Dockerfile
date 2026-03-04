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

# Install Poetry
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VENV_IN_PROJECT=1
ENV POETRY_NO_INTERACTION=1
ENV POETRY_CACHE_DIR=/opt/poetry/.cache
RUN pip install poetry==1.8.5

WORKDIR /app

# Copy dependency files and install (cached layer)
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root && \
    poetry cache clear --all pypi

# App code is bind-mounted via docker-compose volumes
# No COPY of application code here

ARG APP_PORT=8000
EXPOSE $APP_PORT

CMD ["poetry", "run", "python", "main.py"]
