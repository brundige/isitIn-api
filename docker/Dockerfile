# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# Stage 1 — build the PWA bundle
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /build

# Install deps with cache, then build. Keeping these in two layers means
# changes to src/ don't invalidate the npm-install layer.
COPY Frontend/package.json Frontend/package-lock.json ./
RUN npm ci

COPY Frontend/ ./
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — Python runtime
# ------------------------
---------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# libgomp1: OpenMP runtime needed by LightGBM
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Backend ./Backend
COPY ML ./ML

# Bring in the built PWA from stage 1
COPY --from=frontend /build/dist ./Frontend/dist

# cache/ is mounted as a volume at runtime, but ensure the dir exists
RUN mkdir -p cache

EXPOSE 8000

CMD ["uvicorn", "Backend.API.main:app", "--host", "0.0.0.0", "--port", "8000"]
