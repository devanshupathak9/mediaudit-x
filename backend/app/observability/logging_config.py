"""
Configures the "app" logger (the parent of every `logging.getLogger(__name__)`
call inside app/, since module names are all "app.foo.bar") with:

  - a JSON stdout handler (always on -- `docker compose logs` / plain
    `uvicorn` output stays useful with zero other setup)
  - an Elasticsearch handler shipping the same records to `app-logs`
    (optional, `settings.log_to_elasticsearch`)

Both run off a background thread via QueueHandler/QueueListener: the
calling code (a request handler, a pipeline service, anything that calls
`logger.info(...)`) only ever pushes onto an in-memory queue and returns
immediately. The listener thread drains the queue and does the actual
(potentially slow, e.g. an Elasticsearch round-trip) writing. This is the
standard library's own recommended pattern for a handler slow enough to
matter -- see `logging.handlers.QueueHandler`/`QueueListener` -- rather
than a bespoke async wrapper.

Deliberately scoped to the "app" logger, not the root logger: uvicorn,
elasticsearch-py, boto3 etc. configure their own loggers and are noisy at
INFO (every HTTP call, connection pool churn, ...) -- left alone here.

Call configure_logging() exactly once, at process startup (app/main.py).
"""
import logging
import logging.handlers
import queue
import sys

from app.observability.context import RequestContextFilter
from app.observability.es_handler import ElasticsearchLogHandler
from app.observability.formatting import JsonFormatter

APP_LOGGER_NAME = "app"

_listener: logging.handlers.QueueListener | None = None


def configure_logging(log_level: str, ship_to_elasticsearch: bool) -> None:
    global _listener

    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(log_level.upper())
    app_logger.propagate = False  # don't also hand records to the root logger

    # Idempotent: re-configuring (e.g. reload, tests) doesn't stack handlers.
    if _listener is not None:
        _listener.stop()
    app_logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JsonFormatter())
    handlers: list[logging.Handler] = [stdout_handler]

    if ship_to_elasticsearch:
        from app.es_client import get_es_client
        handlers.append(ElasticsearchLogHandler(get_es_client))

    log_queue: queue.Queue = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.addFilter(RequestContextFilter())
    app_logger.addHandler(queue_handler)

    _listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
    _listener.start()


def stop_logging() -> None:
    """Flushes and stops the background listener thread -- call on
    shutdown so buffered records aren't silently dropped mid-write."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def get_app_logger(name: str) -> logging.Logger:
    """`name` should be `__name__` of the calling module (e.g.
    "app.routers.claims") -- every such module is already a child of the
    "app" logger configured above by Python's dotted-name hierarchy, so
    this is just `logging.getLogger(name)` with a name that documents the
    expectation."""
    return logging.getLogger(name)
