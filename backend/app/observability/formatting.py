"""
Shared shape for a log record, whether it ends up on stdout (one JSON
object per line) or as an Elasticsearch document -- same fields either
way, so `docker compose logs` and Kibana show the same story.
"""
import json
import logging
import traceback
from datetime import datetime, timezone

# Attributes every LogRecord already has -- anything else on the record
# (passed via `logger.info(..., extra={...})`) is application-specific
# and gets folded into the output too.
_STANDARD_ATTRS = set(logging.LogRecord(
    "", 0, "", 0, "", (), None,
).__dict__.keys()) | {"message", "asctime", "request_id", "claim_id"}


def record_to_dict(record: logging.LogRecord) -> dict:
    doc = {
        "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
        "request_id": getattr(record, "request_id", None),
        "claim_id": getattr(record, "claim_id", None),
    }
    if record.exc_info:
        exc_type, exc_value, _ = record.exc_info
        doc["error_type"] = exc_type.__name__ if exc_type else None
        doc["error_message"] = str(exc_value) if exc_value else None
        doc["traceback"] = "".join(traceback.format_exception(*record.exc_info))

    extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
    doc.update(extras)
    return doc


class JsonFormatter(logging.Formatter):
    """One JSON object per line on stdout -- readable with `docker compose
    logs` / `jq`, and the exact same shape indexed into Elasticsearch, so
    there's one schema to remember, not two."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_to_dict(record), default=str)
