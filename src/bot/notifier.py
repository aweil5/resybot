"""Telegram notification module."""

import logging
from datetime import datetime

import requests

from src.config import settings

logger = logging.getLogger(__name__)


def send_message(message: str, parse_mode: str = "HTML") -> bool:
    """
    Send a message to the configured Telegram channel.

    Args:
        message: Message text to send
        parse_mode: Message format (HTML or Markdown)

    Returns:
        True if successful, False otherwise
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug(f"[TELEGRAM DISABLED] {message}")
        return False

    try:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        data = {
            "chat_id": settings.telegram_chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def send_booking_success(
    restaurant_id: str,
    date: str,
    time_str: str,
    party_size: int,
    reservation_id: str,
) -> bool:
    """Send notification for successful booking."""
    message = (
        f"<b>RESERVATION BOOKED</b>\n\n"
        f"Restaurant: {restaurant_id}\n"
        f"Date: {date}\n"
        f"Time: {time_str}\n"
        f"Party Size: {party_size}\n"
        f"Reservation ID: {reservation_id}\n\n"
        f"Booked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_message(message)


def send_jwt_expiry_warning(account_name: str, hours_remaining: float) -> bool:
    """Send notification when JWT is expiring soon."""
    message = (
        f"<b>TOKEN EXPIRING SOON</b>\n\n"
        f"Account: {account_name}\n"
        f"Expires in: {hours_remaining:.1f} hours\n\n"
        f"Please refresh the auth token soon."
    )
    return send_message(message)


def send_fatal_error(error: str) -> bool:
    """Send notification for fatal errors that crash the bot."""
    message = (
        f"<b>FATAL ERROR</b>\n\n"
        f"Error: {error[:500]}\n\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_message(message)


def send_status_report(
    scans_completed: int,
    availability_seen: dict[str, int],
    uptime_hours: float,
) -> bool:
    """
    Send periodic status report.

    Args:
        scans_completed: Number of scans since last report
        availability_seen: Dict of date -> times availability was seen
        uptime_hours: Total uptime in hours
    """
    lines = [
        "<b>RESYBOT STATUS REPORT</b>",
        "",
        f"Uptime: {uptime_hours:.1f} hours",
        f"Scans completed: {scans_completed:,}",
    ]

    if availability_seen:
        lines.append("Availability seen:")
        for date, count in sorted(availability_seen.items()):
            times_word = "time" if count == 1 else "times"
            lines.append(f"  {date}: {count} {times_word}")
    else:
        lines.append("Availability seen: None")

    lines.append("")

    return send_message("\n".join(lines))
