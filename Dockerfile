# Use an official Python runtime as a parent image
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # UV environment variables
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

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

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set the working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application code
COPY . .

# Install the project itself (if needed, or just ensures env is ready)
RUN uv sync --frozen --no-dev

# Create directories for volumes
RUN mkdir -p logs data db

# Set the entrypoint
# Using 'uv run' ensures the environment is active and up-to-date
CMD ["uv", "run", "python", "start.py"]
