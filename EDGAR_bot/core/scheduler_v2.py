"""
APScheduler entry-point for edgar_scheduler_2 with dynamic intervals based on earnings periods.

Earnings periods (10-second intervals):
- 6:00 AM - 9:30 AM EST
- 4:00 PM - 5:30 PM EST

Cooldown periods (30-minute intervals):
- All other times

During earnings periods, uses Watchlist tickers if available, otherwise full CSV.
During cooldown periods, always uses full CSV list.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from EDGAR_bot.core import config
from EDGAR_bot.core import jobs_v2

LOGGER = logging.getLogger("scheduler_v2")

# Time zone for EST/EDT
EST = pytz.timezone('US/Eastern')

# Earnings period configuration (in EST)
EARNINGS_PERIODS = [
    (datetime.time(6, 0), datetime.time(9, 30)),  # 6:00 AM - 9:30 AM EST
    (datetime.time(12, 30), datetime.time(13, 10)),  # 4:00 PM - 5:30 PM EST
    (datetime.time(16, 0), datetime.time(17, 30)),  # 4:00 PM - 5:30 PM EST
]

# Interval configuration
EARNINGS_INTERVAL_SECONDS = 10
COOLDOWN_INTERVAL_MINUTES = 30


def is_earnings_period(dt: Optional[datetime.datetime] = None) -> bool:
    """
    Check if the given datetime (or current time) is within an earnings period.

    Args:
        dt: Datetime to check. If None, uses current time.

    Returns:
        True if within earnings period, False otherwise.
    """
    if dt is None:
        dt = datetime.datetime.now(EST)
    elif dt.tzinfo is None:
        dt = EST.localize(dt)
    else:
        dt = dt.astimezone(EST)

    current_time = dt.time()

    for start_time, end_time in EARNINGS_PERIODS:
        if start_time <= current_time <= end_time:
            return True

    return False


def get_next_transition_time() -> datetime.datetime:
    """
    Calculate when the next transition between earnings/cooldown periods occurs.

    Returns:
        Datetime of the next transition point.
    """
    now = datetime.datetime.now(EST)
    today = now.date()
    current_time = now.time()

    # Check all transition points for today
    transition_times = []
    for start_time, end_time in EARNINGS_PERIODS:
        transition_times.append(datetime.datetime.combine(today, start_time, tzinfo=EST))
        transition_times.append(datetime.datetime.combine(today, end_time, tzinfo=EST))

    # Find next transition after current time
    future_transitions = [t for t in transition_times if t > now]

    if future_transitions:
        return min(future_transitions)

    # If no transitions left today, return first transition tomorrow
    tomorrow = today + datetime.timedelta(days=1)
    return datetime.datetime.combine(tomorrow, EARNINGS_PERIODS[0][0], tzinfo=EST)


class DynamicScheduler:
    """
    Manages dynamic scheduling based on earnings/cooldown periods.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.scheduler = AsyncIOScheduler(event_loop=loop)
        self.current_job = None
        self.is_earnings_mode = None

    def start(self):
        """Start the scheduler with initial configuration."""
        self.scheduler.start()
        self._update_schedule()

        # Schedule periodic checks for period transitions
        self.scheduler.add_job(
            self._check_and_update_schedule,
            trigger="interval",
            minutes=1,  # Check every minute for period transitions
            id="period_checker",
            coalesce=True,
            max_instances=1,
        )

        LOGGER.info("Dynamic EDGAR bot scheduler started")

    def _update_schedule(self):
        """Update the job schedule based on current period."""
        is_earnings = is_earnings_period()

        # Only update if period has changed
        if self.is_earnings_mode == is_earnings:
            return

        self.is_earnings_mode = is_earnings

        # Remove existing job if any
        if self.current_job:
            try:
                self.scheduler.remove_job(self.current_job)
            except Exception:
                pass  # Job might not exist

        # Add new job with appropriate interval
        if is_earnings:
            interval_seconds = EARNINGS_INTERVAL_SECONDS
            job_id = "edgar_job_earnings"
            LOGGER.info(
                "Entering EARNINGS period - switching to %d second intervals",
                interval_seconds
            )
        else:
            interval_seconds = COOLDOWN_INTERVAL_MINUTES * 60
            job_id = "edgar_job_cooldown"
            LOGGER.info(
                "Entering COOLDOWN period - switching to %d minute intervals",
                COOLDOWN_INTERVAL_MINUTES
            )

        # Schedule the job with the appropriate run_once variant
        self.scheduler.add_job(
            jobs_v2.run_once,
            trigger="interval",
            seconds=interval_seconds,
            id=job_id,
            args=[is_earnings],  # Pass period type to jobs
            next_run_time=datetime.datetime.now(datetime.UTC),
            coalesce=True,
            max_instances=1,
        )

        self.current_job = job_id

        # Log next transition time
        next_transition = get_next_transition_time()
        LOGGER.info("Next period transition at: %s", next_transition.strftime("%Y-%m-%d %H:%M:%S %Z"))

    def _check_and_update_schedule(self):
        """Periodically check if we need to update the schedule."""
        self._update_schedule()

    def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown(wait=False)


async def _runner() -> None:
    """
    Main async runner that manages the dynamic scheduler.

    * Spin up the dynamic scheduler
    * Register signal handlers for clean shutdown
    * Park on an Event to keep the loop alive
    """
    loop = asyncio.get_running_loop()
    scheduler = DynamicScheduler(loop)
    scheduler.start()

    # Event that we set() when a termination signal arrives
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, AttributeError):
            pass  # Windows doesn't support add_signal_handler

    await stop_event.wait()  # Blocks here until set()

    LOGGER.info("Shutdown signal received - stopping scheduler...")
    scheduler.shutdown()


def main() -> None:
    """
    Synchronous entry point for the edgar_scheduler_2 command.
    Wraps the async runner in asyncio.run() to ensure an event loop exists.
    """
    try:
        asyncio.run(_runner())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Exiting.")


if __name__ == "__main__":
    main()