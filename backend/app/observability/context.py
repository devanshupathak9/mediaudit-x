"""
Per-request context (request_id, claim_id) propagated onto every log
record, without threading it through every function signature.

Uses contextvars rather than thread-locals because request handling here
is async (FastAPI/Starlette) -- a thread-local would leak across
concurrently-handled requests sharing the same event loop thread;
contextvars correctly scope to each request's own async context.
"""
import contextlib
import logging
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_claim_id: ContextVar[str | None] = ContextVar("claim_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def set_claim_id(value: str | None) -> None:
    """Call this from a route/service once a claim_id is known, so every
    subsequent log line in the same request -- including ones logged deep
    inside a service that doesn't otherwise know it's inside a request --
    is filterable by claim_id in Kibana."""
    _claim_id.set(value)


@contextlib.contextmanager
def claim_context(claim_id: str | None):
    """For code paths outside a request (CLI scripts, background jobs)
    that still want claim_id on their log lines."""
    token = _claim_id.set(claim_id)
    try:
        yield
    finally:
        _claim_id.reset(token)


class RequestContextFilter(logging.Filter):
    """Attached to the app's logger so every LogRecord picks up the
    current request_id/claim_id (or None) as attributes, which the
    formatters/handlers below read."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        record.claim_id = _claim_id.get()
        return True
