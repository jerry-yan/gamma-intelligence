"""
APScheduler entry‑point that runs `jobs.run_once()` every N minutes
(as configured in config.SCHEDULE_MINUTES).

Usage (local):
    python scheduler.py

On Heroku the Procfile should contain:
    worker: python scheduler.py
"""
from __future__ import annotations

import asyncio
import logging
import signal
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from EDGAR_bot.core import config
from EDGAR_bot.core import jobs

LOGGER = logging.getLogger("scheduler")


# ───────────────────────────────────────── scheduler setup ────────────────
def _setup_scheduler(loop: asyncio.AbstractEventLoop) -> AsyncIOScheduler:
    """
    Create and configure the AsyncIO scheduler, explicitly binding it to
    the *running* event‑loop that `asyncio.run()` gives us.
    """
    sched = AsyncIOScheduler(event_loop=loop)
    sched.add_job(
        jobs.run_once,
        trigger="interval",
        minutes=config.SCHEDULE_MINUTES,
        next_run_time=datetime.datetime.now(datetime.UTC),
        coalesce=True,          # skip overlapping runs
        max_instances=1,
    )
    return sched


# ──────────────────────────────────────── main async runner ───────────────
async def _runner() -> None:
    """
    *   Spin‑up the scheduler.
    *   Register signal handlers for clean shutdown.
    *   Then park forever on an Event so the loop stays alive.
    """
    loop = asyncio.get_running_loop()
    scheduler = _setup_scheduler(loop)
    scheduler.start()

    LOGGER.info(
        "EDGAR bot scheduler started – interval: %d min (Ctrl‑C to quit)",
        config.SCHEDULE_MINUTES,
    )

    # an Event that we set() when a termination signal arrives
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows raises if SIGTERM is missing – ignore gracefully
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, AttributeError):
            pass

    await stop_event.wait()     # ← blocks here until set()

    LOGGER.info("Shutdown signal received – stopping scheduler …")
    scheduler.shutdown(wait=False)


# ───────────────────────────────────────── script entry‑point ─────────────
def main() -> None:
    """
    Synchronous entry‑point used by `python scheduler.py` **and** the Heroku
    Procfile.  Wraps the async runner in `asyncio.run()` so an event‑loop is
    guaranteed to exist before APScheduler is started.
    """
    try:
        asyncio.run(_runner())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Exiting.")


if __name__ == "__main__":
    main()
