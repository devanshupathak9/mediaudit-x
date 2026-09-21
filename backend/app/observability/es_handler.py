"""
Ships log records to the `app-logs` index.

Deliberately not named "alerts" -- ARCHITECTURE.md already reserves that
name for a planned business-domain alerts index (drug interactions,
broken ledger, Stage 10), which is a different concept from infra/app
logging and would be confusing to conflate.

This handler is only ever driven from the background thread started by
QueueListener (see logging_config.py) -- never called inline from a
request-handling coroutine -- so a slow or unreachable Elasticsearch
cluster adds latency to the log-processing thread, never to the response
the caller is waiting on.

If the write itself fails, it's swallowed with a one-line stderr notice
rather than raised: a log line that fails to log itself must never take
the application down, and must never re-enter the logging system (that
would recurse straight back into this same handler).
"""
import logging
import sys

from app.indices.names import APP_LOGS
from app.observability.formatting import record_to_dict


class ElasticsearchLogHandler(logging.Handler):
    def __init__(self, es_client_factory):
        super().__init__()
        self._es_client_factory = es_client_factory

    def emit(self, record: logging.LogRecord) -> None:
        try:
            es = self._es_client_factory()
            es.index(index=APP_LOGS, document=record_to_dict(record))
        except Exception as exc:  # noqa: BLE001 -- logging must never crash the app
            print(f"[ElasticsearchLogHandler] failed to ship a log record: {exc}", file=sys.stderr)
