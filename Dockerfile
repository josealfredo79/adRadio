# ── Stage 1: Build React frontend ─────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json ./
COPY frontend/package-lock.json* ./
RUN npm install --ignore-scripts

COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python API (serves frontend too) ─────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    libmupdf-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

COPY --from=frontend-builder /frontend/dist ./app/static/dist

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

CMD ["/docker-entrypoint.sh"]