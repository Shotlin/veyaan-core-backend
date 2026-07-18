import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_list(value: str) -> list[str]:
    """Parse comma-separated string or JSON array to list."""
    if isinstance(value, list):
        return value
    if value.startswith("["):
        return json.loads(value)
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # Application
    ENVIRONMENT: str = "development"
    SERVICE_VERSION: str = "0.1.0"
    API_BASE_URL: str = "http://localhost:8000"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Supabase
    SUPABASE_URL: str
    SUPABASE_JWKS_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # NATS
    NATS_URL: str = "nats://localhost:4222"
    NATS_STREAM_COMMANDS: str = "VEYAAN_COMMANDS"
    NATS_STREAM_DEVICE_EVENTS: str = "VEYAAN_DEVICE_EVENTS"
    NATS_STREAM_APPROVALS: str = "VEYAAN_APPROVALS"
    NATS_STREAM_SECURITY: str = "VEYAAN_SECURITY"
    NATS_CONSUMER_API: str = "api_consumer"
    NATS_CONSUMER_GATEWAY: str = "gateway_consumer"

    # Valkey
    VALKEY_URL: str = "redis://localhost:6379"
    VALKEY_KEY_PREFIX: str = "veyaan:dev:"
    VALKEY_DEFAULT_TTL: int = 300

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_HEARTBEAT_TIMEOUT: int = 90
    WS_MAX_MESSAGE_SIZE: int = 1048576
    WS_SUPPORTED_PROTOCOLS: list[str] = ["v1"]

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = "veyaan-dev"
    R2_BUCKET_NAME: str = "veyaan-dev"  # alias used by r2_client.py
    R2_ENDPOINT_URL: str = ""  # e.g. https://<account_id>.r2.cloudflarestorage.com
    R2_PUBLIC_URL: str = ""

    # Security
    DEVICE_CREDENTIAL_TTL_DAYS: int = 365
    PAIRING_CODE_TTL_MINUTES: int = 10
    APPROVAL_TTL_MINUTES: int = 30
    IDEMPOTENCY_TTL_HOURS: int = 24
    EMERGENCY_STOP_CACHE_TTL: int = 60

    # Trusted reverse proxies — only these IPs may set X-Forwarded-For
    # In production this is the Caddy container's network IP (e.g. 172.x.x.x)
    # Leave empty to disable proxy header trust (fall back to direct client IP)
    TRUSTED_PROXY_IPS: list[str] = []

    # Rate Limits
    RATE_LIMIT_AUTH_FAILURES: int = 5
    RATE_LIMIT_PAIRING: int = 3
    RATE_LIMIT_COMMANDS: int = 30
    RATE_LIMIT_APPROVALS: int = 10
    RATE_LIMIT_WS_CONNECTIONS: int = 5
    RATE_LIMIT_HEALTH_DETAIL: int = 30

    # Monitoring
    LOG_LEVEL: str = "DEBUG"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    SENTRY_DSN: str = ""

    @field_validator(
        "ALLOWED_ORIGINS", "WS_SUPPORTED_PROTOCOLS", "TRUSTED_PROXY_IPS", mode="before"
    )
    @classmethod
    def parse_list_fields(cls, v):
        return parse_list(v)


settings = Settings()
