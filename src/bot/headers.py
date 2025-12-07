"""Resy API header definitions."""

RESY_API_KEY = 'ResyAPI api_key="VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"'


def get_headers(auth_token: str) -> dict[str, str]:
    """
    Get headers for authenticated Resy API requests.

    Args:
        auth_token: JWT authentication token

    Returns:
        Headers dict for requests
    """
    return {
        "Authorization": RESY_API_KEY,
        "X-Resy-Auth-Token": auth_token,
        "X-Resy-Universal-Auth": auth_token,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://resy.com",
        "Referer": "https://resy.com/",
        "Sec-Ch-Ua": '"Chromium";v="142", "Google Chrome";v="142", "Not:A-Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        ),
    }


def get_headers_no_auth() -> dict[str, str]:
    """
    Get headers for unauthenticated Resy API requests.

    Returns:
        Headers dict without auth tokens
    """
    return {
        "Authorization": RESY_API_KEY,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://resy.com",
        "Referer": "https://resy.com/",
        "Sec-Ch-Ua": '"Chromium";v="142", "Google Chrome";v="142", "Not:A-Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        ),
    }
