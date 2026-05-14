FROM python:3.12-slim

WORKDIR /app

# System deps for PyMuPDF, Pillow, pydub (audio) y edge-tts
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    libmupdf-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure audio directory exists for local file storage
RUN mkdir -p app/static/audio

EXPOSE 8000

# railway.toml startCommand overrides this; fallback uses $PORT or 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4"]
