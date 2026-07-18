import logging

import structlog

from app.config import settings


def setup_logging():
    # Configure standard library logging first
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL.upper()),
    )

    # Redact sensitive fields
    class RedactingProcessor:
        SENSITIVE_FIELDS = {
            "authorization", "token", "password", "secret", "credential",
            "access_token", "refresh_token", "api_key", "private_key",
            "supabase_service_role_key", "database_url", "valkey_url",
            "nats_url", "r2_secret_access_key"
        }

        def __call__(self, logger, name, event_dict):
            for key in list(event_dict.keys()):
                if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                    event_dict[key] = "[REDACTED]"
            return event_dict

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            RedactingProcessor(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


setup_logging()
logger = structlog.get_logger()
