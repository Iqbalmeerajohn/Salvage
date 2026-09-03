"""Vercel backend-framework entrypoint.

Vercel's Python runtime looks for a FastAPI instance named `app` in a supported
entrypoint file at the project root (root directory here is `backend/`). It then
serves the ASGI app directly and forwards the ORIGINAL request path, so every
route defined in salvage/app.py is reachable without any rewrite.

This module intentionally contains no logic — it only re-exports the single
FastAPI application. Running locally is unchanged:
    uvicorn salvage.app:app     (or)     uvicorn main:app
"""
from salvage.app import app  # noqa: F401
