FROM python:3.11-slim

# System deps: ffmpeg, espeak-ng, fonts, git
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    fonts-dejavu-core \
    fonts-liberation \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set shared location for Playwright browsers before installation
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Create non-root user devvideo and application directories
RUN useradd -m -s /bin/bash devvideo && \
    mkdir -p /ms-playwright /app/out /app/tmp && \
    chown -R devvideo:devvideo /app

WORKDIR /app

# Install Python dependencies from requirements.txt only
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright chromium browser and system dependencies, making it readable to all users
RUN playwright install chromium --with-deps && \
    chmod -R a+rX /ms-playwright

# Copy repository source with devvideo ownership
COPY --chown=devvideo:devvideo . .

# Environment variables
ENV TMPDIR=/app/tmp

# Switch to non-root user
USER devvideo

ENTRYPOINT ["python", "-m", "src.cli"]
