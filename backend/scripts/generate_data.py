"""CLI: regenerate the synthetic dataset into ../data/.

    python scripts/generate_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from salvage.synth import generate, write  # noqa: E402

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[2] / "data"
    counts = write(generate(), out)
    print(f"Wrote synthetic dataset to {out}")
    for k, v in counts.items():
        print(f"  {k}: {v}")
