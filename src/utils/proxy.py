"""Proxy formatting utilities."""


def format_proxy(proxy_str: str) -> dict[str, str] | None:
    """
    Format proxy string to requests-compatible dict.

    Args:
        proxy_str: Proxy string in format ip:port:user:password

    Returns:
        Dict with http/https proxy URLs or None if invalid format
    """
    if not proxy_str:
        return None

    try:
        parts = proxy_str.split(":")
        if len(parts) != 4:
            return None

        ip, port, user, password = parts
        proxy_url = f"http://{user}:{password}@{ip}:{port}"

        return {
            "http": proxy_url,
            "https": proxy_url,
        }
    except Exception:
        return None


def format_proxy_for_httpx(proxy_str: str) -> dict[str, str] | None:
    """
    Format proxy string for httpx AsyncClient.

    Args:
        proxy_str: Proxy string in format ip:port:user:password

    Returns:
        Dict with http:// and https:// scheme keys or None if invalid
    """
    if not proxy_str:
        return None

    try:
        parts = proxy_str.split(":")
        if len(parts) != 4:
            return None

        ip, port, user, password = parts
        proxy_url = f"http://{user}:{password}@{ip}:{port}"

        return {
            "http://": proxy_url,
            "https://": proxy_url,
        }
    except Exception:
        return None
