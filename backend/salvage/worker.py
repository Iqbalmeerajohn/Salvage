"""Continuous outbox worker.

In the cloud this is what makes SALVAGE "always on": it polls the outbox and
performs pending money actions exactly once, forever, independent of any UI.

Two ways to run it:
  * As its own process:      python -m salvage.worker
  * In-process with the API: set RUN_WORKER=true (a daemon thread is started).

Either way the exactly-once guarantees in outbox.py hold — running both at once
is safe (the UNIQUE idempotency key collapses any duplicate).
"""
from __future__ import annotations

import os
import threading
import time

from . import outbox
from .db import connect, init_db
from .payments.factory import get_gateway

POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "3"))


def run_forever(stop: threading.Event | None = None) -> None:
    init_db()
    gateway = get_gateway()
    while stop is None or not stop.is_set():
        conn = connect()
        try:
            n = outbox.run_once(conn, gateway)
            if n:
                print(f"[worker] executed {n} pending recover action(s)", flush=True)
        except Exception as exc:  # never let the loop die
            print(f"[worker] error: {type(exc).__name__}: {exc}", flush=True)
        finally:
            conn.close()
        time.sleep(POLL_SECONDS)


def start_background() -> threading.Thread:
    """Start the worker as a daemon thread (used when RUN_WORKER=true)."""
    t = threading.Thread(target=run_forever, name="salvage-worker", daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    print(f"[worker] starting, poll every {POLL_SECONDS}s", flush=True)
    run_forever()
