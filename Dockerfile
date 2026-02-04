# --- Builder Stage ---
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Configure uv to install to system location
ENV UV_PROJECT_ENVIRONMENT="/usr/local"
ENV UV_COMPILE_BYTECODE=1

# Step 1: Copy only dependency files (cached layer)
COPY pyproject.toml uv.lock ./
COPY bot/pyproject.toml ./bot/
COPY shared/pyproject.toml ./shared/
COPY webapp/pyproject.toml ./webapp/

# Create minimal package structure for uv workspace resolution
RUN mkdir -p bot/other shared/src/shared webapp && \
    touch bot/__init__.py bot/other/__init__.py && \
    touch shared/src/shared/__init__.py && \
    touch webapp/__init__.py

# Step 2: Install dependencies (cached unless pyproject.toml/uv.lock change)
RUN uv sync --frozen --no-dev --package mmwb-bot

# Step 3: Copy actual source code (invalidates only on code changes)
COPY bot ./bot
COPY shared ./shared
COPY webapp ./webapp

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
