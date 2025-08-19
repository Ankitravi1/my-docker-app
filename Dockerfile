# Production image for Flask app with MoviePy
FROM python:3.10-slim

# Install system deps: ffmpeg for audio/video, ImageMagick for TextClip, fonts for rendering, curl for healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        imagemagick \
        fonts-dejavu-core \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Optional: relax ImageMagick policy if needed for text rendering (usually not required for TextClip)
# RUN sed -i 's/\(<policy domain=\"path\" rights=\"none\" pattern=\"@\"\)/<!-- \1 -->/g' /etc/ImageMagick-6/policy.xml || true
# RUN sed -i 's/\(<policy domain=\"coder\" rights=\"none\" pattern=\"PDF\"\/>\)/<!-- \1 -->/g' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

# Install Python deps first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

# Ensure required directories exist
RUN mkdir -p uploads outputs

EXPOSE 8080

# Use gunicorn in production
CMD ["gunicorn", "-w", "2", "-k", "gthread", "-b", "0.0.0.0:8080", "--timeout", "600", "main:app"]
