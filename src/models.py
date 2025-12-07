"""Pydantic models for request/response validation."""

from pydantic import BaseModel


class Task(BaseModel):
    """Reservation booking task configuration."""

    auth_token: str
    payment_id: int
    restaurant_id: str
    party_size: int
    start_time: int
    end_time: int
    min_days_out: int
    max_days_out: int
    burst_start: str
    burst_end: str
    burst_delay: int
    idle_delay: int
    burst_timeout: float = 5.0
    idle_timeout: float = 15.0
    max_retries: int = 5
    base_backoff: int = 2
    max_backoff: int = 30


class DetailsRequest(BaseModel):
    """Request model for getting reservation details."""

    day: str
    party_size: int
    config_token: str
    restaurant_id: str
    headers: dict[str, str]
    select_proxy: dict[str, str] | None = None


class ReservationRequest(BaseModel):
    """Request model for booking a reservation."""

    book_token: str
    payment_id: int
    headers: dict[str, str]
    select_proxy: dict[str, str] | None = None


class VerificationResult(BaseModel):
    """Result of a verification check."""

    name: str
    passed: bool
    message: str = ""
    details: dict[str, str] = {}
