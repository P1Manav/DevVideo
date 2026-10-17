FROM python:3.11-slim

# System deps: ffmpeg, espeak-ng, fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    fonts-dejavu-core \
    fonts-liberation \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash devvideo
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (chromium only)
RUN pip install playwright && playwright install chromium --with-deps

# Copy source
COPY . .

# Switch to non-root
USER devvideo

ENTRYPOINT ["python", "-m", "src.cli"]
