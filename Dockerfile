# --- Builder Stage ---
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy all project files for workspace resolution
COPY pyproject.toml uv.lock ./
COPY bot ./bot
COPY shared ./shared
COPY webapp ./webapp

# Configure uv to install to system location
ENV UV_PROJECT_ENVIRONMENT="/usr/local"
ENV UV_COMPILE_BYTECODE=1

# Install dependencies for bot package
RUN uv sync --frozen --no-dev --package mmwb-bot

# --- Final Stage ---
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
# libgl1 and libglib2.0-0 are for opencv
# libzbar0 is for pyzbar
# libfbclient2 is for firebird
# fonts-dejavu-core is for PIL ImageFont
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    libzbar0 \
    libfbclient2 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create directories for volumes
RUN mkdir -p logs data db

# Set working directory to bot
WORKDIR /app/bot

# Run the application directly with python
CMD ["python", "start.py"]
