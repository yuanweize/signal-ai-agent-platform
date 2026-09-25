"""Application process configuration (Docker compose env + safe defaults)."""

import ipaddress
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central process configuration loaded from process environment/defaults."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Environment ----
    environment: str = "development"

    # ---- Signal API Gateway ----
    signal_api_url: str = ""
    signal_api_token: str = ""
    signal_phone_number: str = ""

    # ---- Feature Toggles (each module is independent) ----
    feature_ai_enabled: bool = False
    feature_market_enabled: bool = True

    # ---- AI Provider (OpenAI-compatible) ----
    # Only used when feature_ai_enabled=True AND ai_api_key is set
    # Works with: OpenAI, Azure, Tailscale AI Gateway, OpenRouter,
    #             Ollama, vLLM, LocalAI, LiteLLM, etc.
    ai_api_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_temperature: float = 0.7
    ai_max_tokens: int = 1000
    ai_context_messages: int = 20  # Max messages in AI context window

    # ---- Database ----
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # ---- Admin Dashboard Security ----
    admin_username: str = ""
    admin_password: str = ""
    admin_totp_secret: str = ""  # Empty = 2FA disabled
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    # ---- Login Protection ----
    login_rate_limit_window_seconds: int = 300
    login_rate_limit_max_attempts_per_ip: int = 20
    login_rate_limit_max_attempts_per_user: int = 8
    login_lock_seconds: int = 900

    # ---- Config Encryption ----
    config_encryption_key: str = ""

    # ---- Data Retention ----
    data_retention_days: int = 30

    # ---- Monitoring Thresholds ----
    alert_signal_pull_fail_rate: float = 0.2
    alert_api_5xx_rate: float = 0.05

    # ---- Bot Behavior ----
    bot_default_language: str = "cs"
    bot_name: str = "Signal AI Agent"
    bot_system_prompt: str = (
        "You are a helpful sales assistant. Reply naturally and professionally."
    )

    # ---- Logging ----
    log_level: str = "INFO"

    # ---- Derived Properties ----

    @property
    def signal_ws_url(self) -> str:
        """WebSocket URL for receiving Signal messages."""
        if not self.signal_api_url or not self.signal_phone_number:
            return ""
        base = self.signal_api_url.replace("http://", "ws://").replace("https://", "wss://")
        number = self.signal_phone_number
        return f"{base}/v1/receive/{number}"

    @property
    def signal_send_url(self) -> str:
        """HTTP URL for sending Signal messages."""
        if not self.signal_api_url:
            return ""
        return f"{self.signal_api_url}/v2/send"

    @property
    def signal_receive_url(self) -> str:
        """HTTP URL for polling Signal messages (fallback)."""
        if not self.signal_api_url or not self.signal_phone_number:
            return ""
        number = self.signal_phone_number
        return f"{self.signal_api_url}/v1/receive/{number}"

    @property
    def is_2fa_enabled(self) -> bool:
        """Check if TOTP 2FA is configured."""
        return bool(self.admin_totp_secret)

    @property
    def is_ai_available(self) -> bool:
        """True if AI module is enabled and auth requirements are satisfied."""
        if not self.feature_ai_enabled:
            return False
        if self.ai_api_key:
            return True

        try:
            host = (urlparse(self.ai_api_base_url).hostname or "").lower()
        except Exception:
            host = ""

        if "gateway.ai" in host or "tailscale" in host or host in {"localhost", "127.0.0.1"}:
            return True

        try:
            return ipaddress.ip_address(host) in ipaddress.ip_network("100.64.0.0/10")
        except ValueError:
            return False

    @property
    def is_market_available(self) -> bool:
        """True if market/sales module is enabled."""
        return self.feature_market_enabled

    @property
    def features_summary(self) -> dict:
        """Summary of module states for dashboard / health check."""
        return {
            "signal": bool(self.signal_phone_number),
            "ai": self.is_ai_available,
            "market": self.is_market_available,
            "admin_2fa": self.is_2fa_enabled,
        }


# Singleton instance
settings = Settings()
