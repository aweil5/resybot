"""Core booking logic and task execution."""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import settings
from src.models import Task
from src.bot.headers import get_headers
from src.bot.notifier import send_booking_success, send_jwt_expiry_warning
from src.utils.jwt import check_token_expiry, get_token_expiry_hours
from src.utils.proxy import format_proxy

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Eastern timezone for burst timing
ET = ZoneInfo("America/New_York")

# Thread-safe stats tracking
_stats_lock = threading.Lock()
_stats = {
    "scan_count": 0,
    "availability_seen": {},  # date -> count
}

# Global backoff coordination - all threads pause together on rate limits
_global_backoff_lock = threading.Lock()
_global_backoff_until = 0.0  # Unix timestamp when backoff ends


def set_global_backoff(seconds: float) -> None:
    """Set global backoff time (thread-safe). All threads will pause."""
    global _global_backoff_until
    with _global_backoff_lock:
        new_until = time.time() + seconds
        if new_until > _global_backoff_until:
            _global_backoff_until = new_until


def wait_for_global_backoff() -> None:
    """Wait if in global backoff period (thread-safe)."""
    global _global_backoff_until
    with _global_backoff_lock:
        wait_time = _global_backoff_until - time.time()
    if wait_time > 0:
        log_status(f"Global backoff active, waiting {wait_time:.1f}s...", "warning")
        time.sleep(wait_time)


def increment_scan_count() -> None:
    """Increment the global scan counter (thread-safe)."""
    with _stats_lock:
        _stats["scan_count"] += 1


def record_availability(date: str) -> None:
    """Record that availability was seen for a date (thread-safe)."""
    with _stats_lock:
        if date not in _stats["availability_seen"]:
            _stats["availability_seen"][date] = 0
        _stats["availability_seen"][date] += 1


def get_and_reset_stats() -> tuple[int, dict[str, int]]:
    """Get current stats and reset counters (thread-safe)."""
    with _stats_lock:
        scan_count = _stats["scan_count"]
        availability_seen = dict(_stats["availability_seen"])
        _stats["scan_count"] = 0
        _stats["availability_seen"] = {}
        return scan_count, availability_seen


def create_session(proxy: dict[str, str] | None = None) -> requests.Session:
    """Create a requests session with connection pooling and retry logic."""
    session = requests.Session()

    # Connection pooling - reuse connections
    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=10,
        max_retries=Retry(total=0),  # We handle retries manually
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if proxy:
        session.proxies.update(proxy)

    return session


def log_status(message: str, level: str = "info") -> None:
    """Log message with appropriate level."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = {
        "success": "[OK]",
        "error": "[FAIL]",
        "warning": "[WARN]",
        "info": "[INFO]",
        "burst": "[BURST]",
    }.get(level, "[INFO]")

    formatted = f"[{timestamp}] {prefix} {message}"
    print(formatted)

    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)


def is_burst_time(burst_start: str, burst_end: str) -> bool:
    """Check if current time (in ET) is within burst window."""
    now_et = datetime.now(ET)
    current_time = now_et.time()

    start_parts = burst_start.split(":")
    end_parts = burst_end.split(":")

    start = dt_time(
        int(start_parts[0]),
        int(start_parts[1]),
        int(start_parts[2]) if len(start_parts) > 2 else 0,
    )
    end = dt_time(
        int(end_parts[0]),
        int(end_parts[1]),
        int(end_parts[2]) if len(end_parts) > 2 else 0,
    )

    return start <= current_time <= end


def get_current_delay(task: Task, in_burst_mode: bool) -> int:
    """Get appropriate delay based on time of day."""
    if in_burst_mode:
        return task.burst_delay
    return task.idle_delay


def get_details(
    day: str,
    party_size: int,
    config_token: str,
    restaurant_id: str,
    session: requests.Session,
    timeout: float = 30.0,
) -> str | None:
    """Get book token directly from Resy API.

    Args:
        day: Date in YYYY-MM-DD format
        party_size: Number of guests
        config_token: The config token from slot search
        restaurant_id: Resy venue ID
        session: Requests session with auth headers already set
        timeout: Request timeout in seconds

    Returns:
        Book token string if successful, None otherwise
    """
    auth_token = session.headers.get("X-Resy-Auth-Token", "")
    url = (
        f"https://api.resy.com/3/details?"
        f"day={day}&"
        f"party_size={party_size}&"
        f"x-resy-auth-token={auth_token}&"
        f"venue_id={restaurant_id}&"
        f"config_id={config_token}"
    )

    try:
        response = session.get(url, timeout=timeout)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            log_status(f"Rate limited getting details. Waiting {retry_after}s", "warning")
            set_global_backoff(retry_after)
            time.sleep(retry_after)
            return None

        if response.status_code != 200:
            log_status(f"Get details failed: HTTP {response.status_code}", "error")
            return None

        data = response.json()
        return data.get("book_token", {}).get("value")
    except Exception as e:
        log_status(f"Get details error: {e}", "error")
        return None


def book_reservation(
    book_token: str,
    payment_id: int,
    session: requests.Session,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Book reservation directly via Resy API.

    Args:
        book_token: The book token from get_details
        payment_id: Payment method ID
        session: Requests session with auth headers already set
        timeout: Request timeout in seconds

    Returns:
        Response dict with reservation_id if successful, or error info
    """
    url = "https://api.resy.com/3/book"
    payload = {
        "book_token": book_token,
        "struct_payment_method": json.dumps({"id": payment_id}),
        "source_id": "resy.com-venue-details",
    }

    # Booking requires additional headers beyond what's in the session
    auth_token = session.headers.get("X-Resy-Auth-Token", "")
    booking_headers = {
        "X-Origin": "https://widgets.resy.com",
        "X-Resy-Universal-Auth": auth_token,
        "Referer": "https://widgets.resy.com/",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache",
        "Sec-Fetch-Dest": "empty",
    }

    try:
        response = session.post(url, data=payload, headers=booking_headers, timeout=timeout)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            log_status(f"Rate limited during booking. Waiting {retry_after}s", "warning")
            set_global_backoff(retry_after)
            time.sleep(retry_after)
            return {"error": "rate_limited"}

        return response.json()
    except Exception as e:
        log_status(f"Book reservation error: {e}", "error")
        return {"error": str(e)}


def get_timeout(task: Task, in_burst: bool) -> float:
    """Get appropriate timeout based on mode."""
    return task.burst_timeout if in_burst else task.idle_timeout


def filter_slots_by_time(slots: list[dict[str, Any]], task: Task) -> list[tuple[str, str, dict[str, Any]]]:
    """Filter slots by time window and return (time_str, config_token, slot) tuples."""
    valid_slots: list[tuple[str, str, dict[str, Any]]] = []
    for slot in slots:
        config_token = slot.get("config", {}).get("token", "")
        parts = config_token.split("/")
        if len(parts) > 8:
            time_str = parts[8][:5]
            time_hour = int(parts[8].split(":")[0])
            if task.start_time <= time_hour <= task.end_time:
                valid_slots.append((time_str, config_token, slot))
    return valid_slots


def try_book_slots(
    valid_slots: list[tuple[str, str, dict[str, Any]]],
    date: str,
    task: Task,
    session: requests.Session,
    timeout: float,
) -> bool:
    """Try to book from a list of valid slots. Returns True if successful."""
    for time_str, config_token, slot in valid_slots:
        log_status(f"Getting book token for {time_str}...", "info")

        book_token = get_details(
            date,
            task.party_size,
            config_token,
            task.restaurant_id,
            session,
            timeout,
        )

        if not book_token:
            log_status(f"Failed to get book token for {time_str}", "error")
            continue

        log_status(f"Attempting to book {time_str}...", "info")

        result = book_reservation(
            book_token,
            task.payment_id,
            session,
            timeout,
        )

        if "reservation_id" in result or (
            "specs" in result
            and "reservation_id" in result.get("specs", {})
        ):
            res_id = result.get("reservation_id") or result.get(
                "specs", {}
            ).get("reservation_id")
            log_status(
                f"BOOKING SUCCESSFUL - Reservation ID: {res_id}",
                "success",
            )
            log_status(
                f"Date: {date} | Time: {time_str} | Party: {task.party_size}",
                "success",
            )
            send_booking_success(
                task.restaurant_id,
                date,
                time_str,
                task.party_size,
                str(res_id),
            )
            return True

        error_msg = result.get("message", str(result))
        log_status(f"Booking failed for {time_str}: {error_msg}", "error")
        # Removed: send_booking_failure - only log to console

    return False


def execute_task(task: Task, proxy_url: str | None, thread_index: int = 0) -> None:
    """Execute a single booking task.

    Args:
        task: The booking task configuration
        proxy_url: Optional proxy URL
        thread_index: Index of this thread (0-based), used for staggering API calls
    """
    log_status(
        f"Starting task: Restaurant {task.restaurant_id}, Party {task.party_size}",
        "info",
    )
    log_status(
        f"Time window: {task.start_time}:00-{task.end_time}:00, "
        f"Days out: {task.min_days_out}-{task.max_days_out}",
        "info",
    )

    # Check token expiry
    is_valid, token_msg = check_token_expiry(task.auth_token)
    if not is_valid:
        log_status(f"Token error: {token_msg}", "error")
        return

    log_status(token_msg, "success")

    # Check for expiry warning
    hours_remaining = get_token_expiry_hours(task.auth_token)
    if hours_remaining and hours_remaining < 24:
        send_jwt_expiry_warning("Account", hours_remaining)

    headers = get_headers(task.auth_token)
    select_proxy = format_proxy(proxy_url) if proxy_url else None

    # Create persistent session for connection pooling
    session = create_session(select_proxy)
    session.headers.update(headers)

    scan_count = 0
    consecutive_failures = 0
    current_backoff = task.base_backoff
    was_in_burst = False

    while True:
        scan_count += 1
        increment_scan_count()  # Track for status reports

        # Check burst mode
        in_burst = is_burst_time(task.burst_start, task.burst_end)
        timeout = get_timeout(task, in_burst)

        if in_burst and not was_in_burst:
            log_status(
                f"Entering BURST MODE (every {task.burst_delay}ms, {task.burst_timeout}s timeout, targeting day {task.max_days_out})",
                "burst",
            )
        elif not in_burst and was_in_burst:
            log_status(
                f"Exiting burst mode (every {task.idle_delay / 1000:.0f}s, {task.idle_timeout}s timeout)",
                "info",
            )
        was_in_burst = in_burst

        try:
            # BURST MODE OPTIMIZATION: Skip calendar, target day max_days_out directly
            # This is the new date that drops at 9 AM - no need to check calendar
            if in_burst:
                target_date = (datetime.now() + timedelta(days=task.max_days_out)).strftime('%Y-%m-%d')
                mode_indicator = "[BURST] "
                log_status(f"{mode_indicator}Scan #{scan_count} - Direct targeting {target_date}...", "info")

                # Go straight to slot search for day 21 (skip calendar)
                url2 = (
                    f"https://api.resy.com/4/find?"
                    f"lat=0&long=0&day={target_date}&"
                    f"party_size={task.party_size}&venue_id={task.restaurant_id}"
                )

                try:
                    response2 = session.get(url2, timeout=timeout)
                except requests.exceptions.Timeout:
                    log_status(f"{mode_indicator}Timeout targeting {target_date}, retrying...", "warning")
                    time.sleep(task.burst_delay / 1000)
                    continue
                except requests.exceptions.ConnectionError:
                    log_status(f"{mode_indicator}Connection error, retrying...", "warning")
                    time.sleep(task.burst_delay / 1000)
                    continue

                if response2.status_code == 429:
                    retry_after = int(response2.headers.get("Retry-After", 5))
                    log_status(f"{mode_indicator}Rate limited. Waiting {retry_after}s...", "warning")
                    set_global_backoff(retry_after)  # Pause all threads
                    time.sleep(retry_after)
                    continue

                if response2.status_code == 200:
                    data2 = response2.json()
                    venues = data2.get("results", {}).get("venues", [])

                    if venues:
                        slots = venues[0].get("slots", [])
                        valid_slots = filter_slots_by_time(slots, task)

                        if valid_slots:
                            record_availability(target_date)  # Track for status reports
                            log_status(
                                f"{mode_indicator}FOUND {len(valid_slots)} slot(s) on {target_date}: "
                                f"{', '.join([s[0] for s in valid_slots])}",
                                "success",
                            )

                            # Try to book immediately
                            if try_book_slots(valid_slots, target_date, task, session, timeout):
                                session.close()
                                return

                # Sleep burst delay with stagger offset and continue
                wait_for_global_backoff()  # Check if rate limited globally
                stagger = thread_index * settings.stagger_burst_ms
                time.sleep((task.burst_delay + stagger) / 1000)
                continue

            # IDLE MODE: Normal calendar scan for all dates
            start_date = datetime.now().strftime('%Y-%m-%d')
            end_date = (datetime.now() + timedelta(days=task.max_days_out)).strftime('%Y-%m-%d')
            url = (
                f"https://api.resy.com/4/venue/calendar?"
                f"venue_id={task.restaurant_id}&"
                f"num_seats={task.party_size}&"
                f"start_date={start_date}&"
                f"end_date={end_date}"
            )

            log_status(f"Scan #{scan_count} - Checking calendar...", "info")

            response = session.get(url, timeout=timeout)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                log_status(f"Rate limited (429). Waiting {retry_after}s...", "warning")
                set_global_backoff(retry_after)  # Pause all threads
                time.sleep(retry_after)
                continue

            if response.status_code != 200:
                consecutive_failures += 1

                if consecutive_failures >= task.max_retries:
                    log_status(
                        f"Max retries ({task.max_retries}) reached. Pausing {task.max_backoff}s...",
                        "error",
                    )
                    # Removed: send_max_retries_warning - only log to console
                    time.sleep(task.max_backoff)
                    consecutive_failures = 0
                    current_backoff = task.base_backoff
                    continue

                log_status(
                    f"HTTP {response.status_code}, retry {consecutive_failures}/{task.max_retries}",
                    "warning",
                )
                time.sleep(current_backoff)
                current_backoff = min(current_backoff * 2, task.max_backoff)
                continue

            # Success - reset failure tracking
            consecutive_failures = 0
            current_backoff = task.base_backoff

            data = response.json()
            if "scheduled" not in data:
                log_status("Unexpected response format", "warning")
                delay = get_current_delay(task, in_burst)
                time.sleep(delay / 1000)
                continue

            # Find available dates
            today = datetime.now().date()
            available_dates = []

            for entry in data["scheduled"]:
                if entry["inventory"]["reservation"] == "available":
                    entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                    days_until = (entry_date - today).days

                    if task.min_days_out <= days_until <= task.max_days_out:
                        available_dates.append(entry["date"])

            if available_dates:
                log_status(
                    f"Found {len(available_dates)} available date(s): "
                    f"{', '.join(available_dates[:5])}{'...' if len(available_dates) > 5 else ''}",
                    "success",
                )

            # Process each available date
            for entry in data["scheduled"]:
                if entry["inventory"]["reservation"] != "available":
                    continue

                entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
                days_until = (entry_date - today).days

                if not (task.min_days_out <= days_until <= task.max_days_out):
                    continue

                log_status(f"Searching slots for {entry['date']}...", "info")

                # Get available slots using session
                url2 = (
                    f"https://api.resy.com/4/find?"
                    f"lat=0&long=0&day={entry['date']}&"
                    f"party_size={task.party_size}&venue_id={task.restaurant_id}"
                )

                try:
                    response2 = session.get(url2, timeout=timeout)
                except requests.exceptions.Timeout:
                    log_status(f"Timeout on slot search for {entry['date']}", "warning")
                    continue
                except requests.exceptions.ConnectionError:
                    log_status(f"Connection error for {entry['date']}", "warning")
                    continue

                if response2.status_code != 200:
                    log_status(f"Slot search failed: HTTP {response2.status_code}", "warning")
                    continue

                data2 = response2.json()

                if "results" not in data2:
                    continue

                venues = data2.get("results", {}).get("venues", [])
                if not venues:
                    continue

                slots = venues[0].get("slots", [])
                valid_slots = filter_slots_by_time(slots, task)

                if valid_slots:
                    record_availability(entry["date"])  # Track for status reports
                    log_status(
                        f"Found {len(valid_slots)} slot(s): "
                        f"{', '.join([s[0] for s in valid_slots])}",
                        "success",
                    )

                    # Try to book using helper
                    if try_book_slots(valid_slots, entry["date"], task, session, timeout):
                        session.close()
                        return

            # Wait before next scan with stagger offset
            wait_for_global_backoff()  # Check if rate limited globally
            delay = get_current_delay(task, in_burst)
            stagger = thread_index * settings.stagger_idle_ms
            total_delay = delay + stagger
            log_status(f"Scan complete. Waiting {total_delay / 1000:.1f}s...", "info")
            time.sleep(total_delay / 1000)
            continue

        except requests.exceptions.Timeout:
            consecutive_failures += 1
            log_status(f"Request timeout, retry {consecutive_failures}/{task.max_retries}", "warning")

            if consecutive_failures >= task.max_retries:
                log_status(f"Max retries reached. Pausing {task.max_backoff}s...", "error")
                time.sleep(task.max_backoff)
                consecutive_failures = 0
                current_backoff = task.base_backoff
            else:
                time.sleep(current_backoff)
                current_backoff = min(current_backoff * 2, task.max_backoff)
            continue

        except requests.exceptions.ConnectionError:
            consecutive_failures += 1
            log_status(
                f"Connection error, retry {consecutive_failures}/{task.max_retries}",
                "warning",
            )

            if consecutive_failures >= task.max_retries:
                time.sleep(task.max_backoff)
                consecutive_failures = 0
                current_backoff = task.base_backoff
            else:
                time.sleep(current_backoff)
                current_backoff = min(current_backoff * 2, task.max_backoff)
            continue

        except Exception as e:
            consecutive_failures += 1
            log_status(f"Error: {e}, retry {consecutive_failures}/{task.max_retries}", "error")
            logger.exception("Task error")

            if consecutive_failures >= task.max_retries:
                time.sleep(task.max_backoff)
                consecutive_failures = 0
                current_backoff = task.base_backoff
            else:
                time.sleep(current_backoff)
                current_backoff = min(current_backoff * 2, task.max_backoff)
            continue


def run_tasks(tasks: list[Task], proxy_url: str | None) -> None:
    """Run multiple tasks concurrently with staggered timing."""
    log_status(f"Starting {len(tasks)} task(s) concurrently with staggered timing...", "info")
    print("=" * 60)

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = [
            executor.submit(execute_task, task, proxy_url, idx)
            for idx, task in enumerate(tasks)
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                log_status(f"Task failed: {e}", "error")
