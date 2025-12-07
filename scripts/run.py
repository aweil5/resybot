#!/usr/bin/env python3
"""Main entry point for headless bot execution."""

import signal
import sys
import threading
from datetime import datetime

from src.config import settings
from src.models import Task
from src.bot.executor import run_tasks, get_and_reset_stats
from src.bot.notifier import send_fatal_error, send_status_report

# Track start time for uptime calculation
_start_time: datetime | None = None
_shutdown_event = threading.Event()


def create_tasks() -> list[Task]:
    """Create tasks from environment configuration."""
    party_sizes = settings.get_party_sizes()

    tasks: list[Task] = []
    for party_size in party_sizes:
        task = Task(
            auth_token=settings.resy_auth_token,
            payment_id=settings.resy_payment_id,
            restaurant_id=settings.resy_restaurant_id,
            party_size=party_size,
            start_time=settings.resy_start_time,
            end_time=settings.resy_end_time,
            min_days_out=settings.resy_min_days_out,
            max_days_out=settings.resy_max_days_out,
            burst_start=settings.burst_start,
            burst_end=settings.burst_end,
            burst_delay=settings.burst_delay_ms,
            idle_delay=settings.idle_delay_ms,
            burst_timeout=settings.burst_timeout,
            idle_timeout=settings.idle_timeout,
            max_retries=settings.max_retries,
            base_backoff=settings.base_backoff,
            max_backoff=settings.max_backoff,
        )
        tasks.append(task)

    return tasks


def status_reporter() -> None:
    """Background thread that sends periodic status reports."""
    interval_seconds = settings.status_report_interval_hours * 3600

    while not _shutdown_event.is_set():
        # Wait for interval or shutdown
        _shutdown_event.wait(timeout=interval_seconds)

        if _shutdown_event.is_set():
            break

        # Calculate uptime
        if _start_time:
            uptime_hours = (datetime.now() - _start_time).total_seconds() / 3600
        else:
            uptime_hours = 0

        # Get and reset stats
        scan_count, availability_seen = get_and_reset_stats()

        # Send report
        print(f"[STATUS] Sending {settings.status_report_interval_hours}-hour status report...")
        send_status_report(scan_count, availability_seen, uptime_hours)


def signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals gracefully."""
    signal_name = signal.Signals(signum).name
    print(f"\n[SHUTDOWN] Received {signal_name}, stopping gracefully...")
    _shutdown_event.set()
    sys.exit(0)


def main() -> int:
    """Main entry point."""
    global _start_time

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    _start_time = datetime.now()

    print("=" * 60)
    print("    RESYBOT - HEADLESS MODE")
    print("=" * 60)
    print(f"Started at: {_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Create tasks from config
    print("[CONFIG] Creating tasks from environment...")
    tasks = create_tasks()

    if not tasks:
        print("[ERROR] No tasks created")
        return 1

    print(f"  Created {len(tasks)} task(s)")
    print(f"  Restaurant: {settings.resy_restaurant_id}")
    print(f"  Party sizes: {settings.resy_party_sizes}")
    print(f"  Time window: {settings.resy_start_time}:00 - {settings.resy_end_time}:00")
    print(f"  Date range: {settings.resy_min_days_out} to {settings.resy_max_days_out} days out")
    print(f"  Status reports: every {settings.status_report_interval_hours} hours")
    print()

    # Print task summary
    print("[TASKS]")
    for i, task in enumerate(tasks, 1):
        print(
            f"  {i}. Restaurant {task.restaurant_id} - "
            f"Party {task.party_size} - "
            f"{task.start_time}:00-{task.end_time}:00"
        )
    print()

    # Start status reporter thread
    reporter_thread = threading.Thread(target=status_reporter, daemon=True)
    reporter_thread.start()
    print(f"[STATUS] Status reporter started (reports every {settings.status_report_interval_hours} hours)")

    print("[RUNNING] Starting task execution...")
    print("-" * 60)

    try:
        run_tasks(tasks, settings.proxy_url)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Interrupted by user")
        _shutdown_event.set()
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        send_fatal_error(str(e))
        _shutdown_event.set()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
