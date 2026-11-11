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
ENV HOME=/home/devvideo
ENV DEVVIDEO_CONTAINER=1

# Create non-root user devvideo with UID 10001 and application directories
RUN useradd -u 10001 -m -s /bin/bash devvideo && \
    mkdir -p /ms-playwright /app /app/out /app/tmp && \
    chown -R devvideo:devvideo /app /ms-playwright /home/devvideo

WORKDIR /app

# Install Python dependencies from requirements.txt
COPY requirements.txt .
RUN for attempt in 1 2 3; do \
        if pip install --no-cache-dir --timeout=120 --retries=10 --upgrade pip && \
           pip install --no-cache-dir --timeout=120 --retries=10 --prefer-binary -r requirements.txt; then \
            break; \
        fi; \
        if [ "$attempt" -eq 3 ]; then \
            echo "pip install failed after 3 attempts" >&2; \
            exit 1; \
        fi; \
        echo "pip install attempt $attempt failed; retrying in 5s..." >&2; \
        sleep 5; \
    done

# Install Playwright chromium browser and system dependencies, making it readable to all users
RUN playwright install chromium --with-deps && \
    chmod -R a+rX /ms-playwright

# Copy repository source with devvideo ownership
COPY --chown=devvideo:devvideo . .

# Environment variables
ENV TMPDIR=/app/tmp
ENV PORT=10000
ENV HOST=0.0.0.0

EXPOSE 10000

# Switch to non-root user UID 10001
USER devvideo

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["serve"]

