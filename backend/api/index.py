"""Vercel serverless entrypoint.

Vercel's Python runtime detects the ASGI `app` object and serves it. All routes
are rewritten here by vercel.json, so the whole FastAPI surface is available.
"""
import sys
from pathlib import Path

# Make the `salvage` package importable when Vercel executes this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from salvage.app import app  # noqa: E402,F401
