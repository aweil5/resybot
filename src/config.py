"""Centralized configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Resy authentication
    resy_auth_token: str
    resy_payment_id: int

    # Restaurant configuration
    resy_restaurant_id: str = "834"
    resy_party_sizes: str = "2,3,4"
    resy_start_time: int = 16
    resy_end_time: int = 23
    resy_min_days_out: int = 2
    resy_max_days_out: int = 21  # 4 Charles releases 21 days out

    # Proxy configuration (format: ip:port:user:pass)
    proxy_url: str | None = None

    # Telegram notifications
    telegram_bot_token: str
    telegram_chat_id: str
    status_report_interval_hours: int = 6  # Hours between status reports

    # Timing configuration
    burst_start: str = "08:59:50"
    burst_end: str = "09:01:00"
    burst_delay_ms: int = 100  # Aggressive polling during burst
    idle_delay_ms: int = 1500
    burst_timeout: float = 5.0  # Fast timeout during burst
    idle_timeout: float = 15.0  # Normal timeout outside burst

    # Stagger configuration - offsets per thread to prevent simultaneous API calls
    stagger_burst_ms: int = 30  # Light stagger during burst (keep fast)
    stagger_idle_ms: int = 500  # Heavier stagger during idle (spread load)

    # Retry configuration
    max_retries: int = 5
    base_backoff: int = 2
    max_backoff: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_party_sizes(self) -> list[int]:
        """Parse party sizes from comma-separated string."""
        return [int(s.strip()) for s in self.resy_party_sizes.split(",")]


settings = Settings()
