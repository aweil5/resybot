#!/usr/bin/env python3
"""Startup verification script with Telegram alerts."""

import sys
from datetime import datetime, timedelta

import requests

from src.config import settings
from src.bot.headers import get_headers
from src.utils.jwt import check_token_expiry, decode_jwt_payload
from src.utils.proxy import format_proxy


def log_check(name: str, passed: bool, message: str = "") -> None:
    """Log a check result."""
    status = "[OK]" if passed else "[FAIL]"
    print(f"  {status} {name}")
    if message:
        print(f"      {message}")


def verify_proxy() -> tuple[dict[str, object], dict[str, str] | None]:
    """Test proxy connectivity."""
    if not settings.proxy_url:
        return {
            "name": "Proxy",
            "passed": True,
            "message": "No proxy configured (direct connection)",
            "details": {},
        }, None

    formatted_proxy = format_proxy(settings.proxy_url)
    if not formatted_proxy:
        return {
            "name": "Proxy",
            "passed": False,
            "message": "Invalid proxy format",
            "details": {},
        }, None

    try:
        resp = requests.get(
            "http://httpbin.org/ip", proxies=formatted_proxy, timeout=15
        )
        if resp.status_code == 200:
            ip_data = resp.json()
            return {
                "name": "Proxy",
                "passed": True,
                "message": "Connected",
                "details": {"Exit IP": ip_data.get("origin", "Unknown")},
            }, formatted_proxy
        return {
            "name": "Proxy",
            "passed": False,
            "message": f"HTTP {resp.status_code}",
            "details": {},
        }, None
    except requests.exceptions.Timeout:
        return {
            "name": "Proxy",
            "passed": False,
            "message": "Connection timeout",
            "details": {},
        }, None
    except Exception as e:
        return {
            "name": "Proxy",
            "passed": False,
            "message": str(e)[:100],
            "details": {},
        }, None


def verify_auth_token(proxy: dict[str, str] | None) -> dict[str, object]:
    """Validate auth token against Resy API."""
    if not settings.resy_auth_token:
        return {
            "name": "Auth Token",
            "passed": False,
            "message": "No token configured",
            "details": {},
        }

    # Check JWT expiration
    is_valid, msg = check_token_expiry(settings.resy_auth_token)
    if not is_valid:
        return {
            "name": "Auth Token",
            "passed": False,
            "message": msg,
            "details": {},
        }

    # Test against Resy API
    headers = get_headers(settings.resy_auth_token)
    try:
        resp = requests.get(
            "https://api.resy.com/3/user/reservations",
            headers=headers,
            proxies=proxy,
            timeout=15,
        )
        if resp.status_code == 200:
            return {
                "name": "Auth Token",
                "passed": True,
                "message": "Valid",
                "details": {"Expiry": msg.split("until ")[-1] if "until" in msg else "Unknown"},
            }
        elif resp.status_code == 401:
            return {
                "name": "Auth Token",
                "passed": False,
                "message": "Invalid (401 Unauthorized)",
                "details": {},
            }
        elif resp.status_code == 403:
            return {
                "name": "Auth Token",
                "passed": False,
                "message": "Forbidden (403)",
                "details": {},
            }
        return {
            "name": "Auth Token",
            "passed": False,
            "message": f"HTTP {resp.status_code}",
            "details": {},
        }
    except Exception as e:
        return {
            "name": "Auth Token",
            "passed": False,
            "message": str(e)[:100],
            "details": {},
        }


def verify_restaurant(proxy: dict[str, str] | None) -> dict[str, object]:
    """Validate restaurant access."""
    if not settings.resy_restaurant_id:
        return {
            "name": "Restaurant",
            "passed": False,
            "message": "No restaurant ID configured",
            "details": {},
        }

    headers = get_headers(settings.resy_auth_token)
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    party_size = settings.get_party_sizes()[0]

    try:
        url = (
            f"https://api.resy.com/4/venue/calendar?"
            f"venue_id={settings.resy_restaurant_id}&"
            f"num_seats={party_size}&"
            f"start_date={today}&end_date={end_date}"
        )
        resp = requests.get(url, headers=headers, proxies=proxy, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            available_count = sum(
                1
                for entry in data.get("scheduled", [])
                if entry.get("inventory", {}).get("reservation") == "available"
            )
            return {
                "name": "Restaurant",
                "passed": True,
                "message": f"{available_count} available dates",
                "details": {
                    "Venue ID": settings.resy_restaurant_id,
                    "Party Size": str(party_size),
                },
            }
        elif resp.status_code == 404:
            return {
                "name": "Restaurant",
                "passed": False,
                "message": "Restaurant not found (404)",
                "details": {"Venue ID": settings.resy_restaurant_id},
            }
        return {
            "name": "Restaurant",
            "passed": False,
            "message": f"HTTP {resp.status_code}",
            "details": {"Venue ID": settings.resy_restaurant_id},
        }
    except Exception as e:
        return {
            "name": "Restaurant",
            "passed": False,
            "message": str(e)[:100],
            "details": {},
        }


def main() -> int:
    """Run verification checks."""
    print("=" * 50)
    print("    STARTUP VERIFICATION")
    print("=" * 50)
    print()

    checks: list[dict[str, object]] = []
    all_passed = True

    # Check 1: Proxy
    print("[1/3] Checking proxy...")
    proxy_result, proxy = verify_proxy()
    checks.append(proxy_result)
    log_check(
        proxy_result["name"],
        proxy_result["passed"],
        proxy_result.get("message", ""),
    )
    # Proxy failure is not critical
    if not proxy_result["passed"] and settings.proxy_url:
        print("      (Proxy failure is non-critical, continuing...)")

    # Check 2: Auth Token
    print("[2/3] Checking auth token...")
    auth_result = verify_auth_token(proxy)
    checks.append(auth_result)
    log_check(auth_result["name"], auth_result["passed"], auth_result.get("message", ""))
    if not auth_result["passed"]:
        all_passed = False

    # Check 3: Restaurant
    print("[3/3] Checking restaurant access...")
    if auth_result["passed"]:
        restaurant_result = verify_restaurant(proxy)
        checks.append(restaurant_result)
        log_check(
            restaurant_result["name"],
            restaurant_result["passed"],
            restaurant_result.get("message", ""),
        )
        if not restaurant_result["passed"]:
            all_passed = False
    else:
        checks.append({
            "name": "Restaurant",
            "passed": False,
            "message": "Skipped (auth failed)",
            "details": {},
        })
        log_check("Restaurant", False, "Skipped (auth failed)")
        all_passed = False

    # Removed: Telegram verification report - console output only

    # Summary
    print()
    print("=" * 50)
    print("    SUMMARY")
    print("=" * 50)

    passed_count = sum(1 for c in checks if c.get("passed"))
    print(f"\n  {passed_count}/{len(checks)} checks passed\n")

    if all_passed:
        print("  [OK] Ready to start bot")
        return 0
    else:
        print("  [FAIL] Fix issues above before running")
        return 1


if __name__ == "__main__":
    sys.exit(main())
