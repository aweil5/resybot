#!/usr/bin/env python3
"""Quick config validation script - does NOT attempt bookings."""

import sys
from datetime import datetime, timedelta

def main() -> int:
    print("=" * 60)
    print("  RESYBOT - Configuration Test")
    print("=" * 60)
    print()

    # Test 1: Import config
    print("[TEST] Loading configuration...")
    try:
        from src.config import settings
        print(f"  [OK] Config loaded")
        print(f"       Restaurant: {settings.resy_restaurant_id}")
        print(f"       Party sizes: {settings.resy_party_sizes}")
        print(f"       Time window: {settings.resy_start_time}:00 - {settings.resy_end_time}:00")
        print(f"       Date range: {settings.resy_min_days_out} - {settings.resy_max_days_out} days")
        print(f"       Burst: {settings.burst_start} - {settings.burst_end} ET")
        print(f"       Burst delay: {settings.burst_delay_ms}ms, timeout: {settings.burst_timeout}s")
        print(f"       Idle delay: {settings.idle_delay_ms}ms, timeout: {settings.idle_timeout}s")
    except Exception as e:
        print(f"  [FAIL] Config error: {e}")
        return 1
    print()

    # Test 2: Validate JWT
    print("[TEST] Validating JWT token...")
    try:
        from src.utils.jwt import check_token_expiry, get_token_expiry_hours
        is_valid, msg = check_token_expiry(settings.resy_auth_token)
        if is_valid:
            hours = get_token_expiry_hours(settings.resy_auth_token)
            print(f"  [OK] {msg}")
            if hours and hours < 24:
                print(f"  [WARN] Token expires in {hours:.1f} hours - refresh soon!")
        else:
            print(f"  [FAIL] {msg}")
            return 1
    except Exception as e:
        print(f"  [FAIL] JWT validation error: {e}")
        return 1
    print()

    # Test 3: Validate proxy format
    print("[TEST] Validating proxy configuration...")
    try:
        from src.utils.proxy import format_proxy
        if settings.proxy_url:
            proxy = format_proxy(settings.proxy_url)
            if proxy:
                print(f"  [OK] Proxy configured")
                print(f"       URL: {proxy['http'][:50]}...")
            else:
                print(f"  [FAIL] Invalid proxy format (expected ip:port:user:pass)")
                return 1
        else:
            print(f"  [WARN] No proxy configured - may hit rate limits")
    except Exception as e:
        print(f"  [FAIL] Proxy error: {e}")
        return 1
    print()

    # Test 4: Telegram config
    print("[TEST] Validating Telegram configuration...")
    try:
        if settings.telegram_bot_token and settings.telegram_chat_id:
            print(f"  [OK] Telegram configured")
            print(f"       Bot token: {settings.telegram_bot_token[:10]}...")
            print(f"       Chat ID: {settings.telegram_chat_id}")
        else:
            print(f"  [FAIL] Missing Telegram credentials")
            return 1
    except Exception as e:
        print(f"  [FAIL] Telegram config error: {e}")
        return 1
    print()

    # Test 5: Calculate target dates
    print("[TEST] Target date calculation...")
    today = datetime.now()
    min_date = (today + timedelta(days=settings.resy_min_days_out)).strftime('%Y-%m-%d')
    max_date = (today + timedelta(days=settings.resy_max_days_out)).strftime('%Y-%m-%d')
    print(f"  [OK] Will search dates from {min_date} to {max_date}")
    print(f"       Burst mode will target: {max_date} (day {settings.resy_max_days_out})")
    print()

    # Test 6: Import all modules
    print("[TEST] Importing all modules...")
    try:
        from src.models import Task
        from src.bot.executor import run_tasks, create_session
        from src.bot.headers import get_headers
        from src.bot.notifier import send_booking_success
        print(f"  [OK] All modules imported successfully")
    except Exception as e:
        print(f"  [FAIL] Import error: {e}")
        return 1
    print()

    print("=" * 60)
    print("  All configuration tests passed!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Run verify:    uv run python scripts/verify.py")
    print("  2. Run bot:       uv run python scripts/run.py")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
