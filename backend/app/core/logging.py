"""Application logging. Do not log passwords, API keys, or tokens."""

import logging
import sys

_SECRET_KEYS = {"password", "secret", "token", "api_key", "access_token", "refresh_token"}


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = str(record.getMessage()).lower()
        if any(key in message for key in _SECRET_KEYS):
            record.msg = "[redacted log record]"
            record.args = ()
        return True


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[handler],
        force=True,
    )
