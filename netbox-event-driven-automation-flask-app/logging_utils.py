import logging
from dataclasses import asdict, is_dataclass
from typing import Any


SENSITIVE_KEYS = {
    "api_token",
    "api_token_secret",
    "password",
    "secret",
    "token",
    "token_value",
}


def redact_payload(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {
            key: "***REDACTED***"
            if str(key).lower() in SENSITIVE_KEYS
            else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_payload(item) for item in value]
    return value


def log_payload(logger: logging.Logger, enabled: bool, message: str, payload: Any) -> None:
    if enabled:
        logger.debug("%s: %r", message, redact_payload(payload))
