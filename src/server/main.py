"""FastAPI server for proxying Resy API requests."""

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.models import DetailsRequest, ReservationRequest

app = FastAPI(title="ResyBot Server", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2


def format_proxy_url(proxy_url: str) -> str:
    """Ensure proxy URL has a scheme."""
    if not urlparse(proxy_url).scheme:
        return f"http://{proxy_url}"
    return proxy_url


async def make_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    max_retries: int = MAX_RETRIES,
    timeout: float = REQUEST_TIMEOUT,
) -> httpx.Response:
    """
    Make HTTP request with retry logic for 5xx errors.

    Args:
        client: httpx AsyncClient
        method: HTTP method (GET or POST)
        url: Request URL
        headers: Request headers
        data: Form data for POST requests
        max_retries: Maximum retry attempts
        timeout: Request timeout in seconds

    Returns:
        Response object

    Raises:
        httpx.TimeoutException: If all retries timeout
        httpx.RequestError: If all retries fail
    """
    last_error: Exception | None = None
    response: httpx.Response | None = None

    for attempt in range(max_retries):
        try:
            if method == "GET":
                response = await client.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                response = await client.post(url, data=data, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Return immediately for non-5xx responses
            if response.status_code < 500:
                return response

            # Log 5xx error and retry
            logger.warning(
                f"Server error {response.status_code} on attempt {attempt + 1}/{max_retries}"
            )

            if attempt < max_retries - 1:
                backoff = RETRY_BACKOFF_BASE**attempt
                logger.info(f"Retrying in {backoff}s...")
                await asyncio.sleep(backoff)

        except httpx.TimeoutException as e:
            logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries}: {e}")
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BACKOFF_BASE**attempt)

        except httpx.RequestError as e:
            logger.warning(f"Request error on attempt {attempt + 1}/{max_retries}: {e}")
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BACKOFF_BASE**attempt)

    if last_error:
        raise last_error
    if response is None:
        raise httpx.RequestError("No response received")
    return response


@app.get("/")
async def index() -> dict[str, str]:
    """Health check endpoint."""
    logger.info("Health check accessed")
    return {"status": "ok", "message": "Server is running"}


@app.post("/api/get-details")
async def get_details(data: DetailsRequest) -> dict[str, Any]:
    """Get reservation details and book token from Resy API."""
    logger.info(f"Get details for restaurant {data.restaurant_id}")

    # Format proxy URLs
    formatted_proxies: dict[str, str] = {}
    if data.select_proxy:
        for scheme, proxy in data.select_proxy.items():
            formatted_proxies[f"{scheme}://"] = format_proxy_url(proxy)
        formatted_proxies["https://"] = formatted_proxies.get(
            "http://", formatted_proxies.get("https://", "")
        )

    url = (
        f"https://api.resy.com/3/details?"
        f"day={data.day}&"
        f"party_size={data.party_size}&"
        f"x-resy-auth-token={data.headers['X-Resy-Auth-Token']}&"
        f"venue_id={data.restaurant_id}&"
        f"config_id={data.config_token}"
    )

    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Authorization": data.headers["Authorization"],
        "Host": "api.resy.com",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(proxies=formatted_proxies, timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await make_request_with_retry(client, "GET", url, headers=headers)
            logger.info(f"Details response: {response.status_code}")
        except httpx.ProxyError as e:
            logger.error(f"Proxy error: {e}")
            raise HTTPException(status_code=500, detail="Proxy connection failed")
        except httpx.TimeoutException as e:
            logger.error(f"Request timeout: {e}")
            raise HTTPException(status_code=504, detail="Request timeout")
        except httpx.RequestError as e:
            logger.error(f"Request failed: {e}")
            raise HTTPException(status_code=500, detail="Request failed")

    # Handle rate limiting
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "60")
        logger.warning(f"Rate limited. Retry-After: {retry_after}")
        return JSONResponse(
            content={"error": "rate_limited", "retry_after": int(retry_after)},
            status_code=429,
            headers={"Retry-After": retry_after},
        )

    if response.status_code != 200:
        logger.warning(f"Failed to get details: {response.status_code}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to get details for restaurant {data.restaurant_id}",
        )

    response_data = response.json()
    logger.info("Details retrieved successfully")
    return {"response_value": response_data["book_token"]["value"]}


@app.post("/api/book-reservation")
async def book_reservation(data: ReservationRequest) -> JSONResponse:
    """Book a reservation through Resy API."""
    logger.info("Book reservation request")

    # Format proxy URLs
    formatted_proxies: dict[str, str] = {}
    if data.select_proxy:
        for scheme, proxy in data.select_proxy.items():
            formatted_proxies[f"{scheme}://"] = format_proxy_url(proxy)
        formatted_proxies["https://"] = formatted_proxies.get(
            "http://", formatted_proxies.get("https://", "")
        )

    url = "https://api.resy.com/3/book"
    payload = {
        "book_token": data.book_token,
        "struct_payment_method": json.dumps({"id": data.payment_id}),
        "source_id": "resy.com-venue-details",
    }

    headers = {
        "Host": "api.resy.com",
        "X-Origin": "https://widgets.resy.com",
        "X-Resy-Auth-Token": data.headers["X-Resy-Auth-Token"],
        "Authorization": data.headers["Authorization"],
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/"
        ),
        "X-Resy-Universal-Auth": data.headers["X-Resy-Auth-Token"],
        "Accept": "application/json, text/plain, */*",
        "Cache-Control": "no-cache",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://widgets.resy.com/",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with httpx.AsyncClient(proxies=formatted_proxies, timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await make_request_with_retry(
                client, "POST", url, headers=headers, data=payload
            )
        except httpx.ProxyError as e:
            logger.error(f"Proxy error during booking: {e}")
            raise HTTPException(status_code=500, detail="Proxy connection failed")
        except httpx.TimeoutException as e:
            logger.error(f"Booking request timeout: {e}")
            raise HTTPException(status_code=504, detail="Booking request timeout")
        except httpx.RequestError as e:
            logger.error(f"Booking request failed: {e}")
            raise HTTPException(status_code=500, detail="Booking request failed")

    logger.info(f"Booking response: {response.status_code}")

    # Handle rate limiting
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "60")
        logger.warning(f"Rate limited during booking. Retry-After: {retry_after}")
        return JSONResponse(
            content={"error": "rate_limited", "retry_after": int(retry_after)},
            status_code=429,
            headers={"Retry-After": retry_after},
        )

    return JSONResponse(content=response.json(), status_code=response.status_code)


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000)
