# SALVAGE backend — single image runs either the API or the worker.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate + seed synthetic data at build time so a fresh deploy has demo data.
# (On Postgres, seeding also runs lazily on first request via _db().)
RUN python scripts/generate_data.py || true

EXPOSE 8000
# Default: the API. Override the command for the worker (see render.yaml).
CMD ["sh", "-c", "uvicorn salvage.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
