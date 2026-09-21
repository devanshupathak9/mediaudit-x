"""
Request-level logging + the catch-all for exceptions that fall through
every router/service's own error handling (this session's own survey of
the codebase found routers converting most errors to HTTPException, but
nothing catching a genuinely unexpected one -- it would previously reach
the client as FastAPI's bare default 500 and be logged nowhere).

Registering `unhandled_exception_handler` for the base `Exception` class
via app.add_exception_handler wires it into Starlette's ExceptionMiddleware,
which picks the most specific handler by walking each exception's MRO --
so existing HTTPException/RequestValidationError handling (404s, 409s,
422s) is untouched, since those already have more specific handlers
registered by FastAPI itself. Only a truly unanticipated exception reaches
this one. Because ExceptionMiddleware sits *inside* the middleware stack
(closer to the route than RequestLoggingMiddleware below), by the time
RequestLoggingMiddleware's call_next() returns, an exception handled this
way already looks like a normal 500 response, not a raised exception --
so the actual `logger.exception(...)` call has to live in the handler,
not in the middleware's own try/except (which stays only as a last-resort
net for whatever might still escape ExceptionMiddleware).
"""
import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.context import get_request_id, set_claim_id, set_request_id
from app.observability.logging_config import get_app_logger

logger = get_app_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def _claim_id_from_path(path: str) -> str | None:
    """Best-effort: most routes are /claims/{claim_id}/... -- pulling it
    out here means logs from anywhere in the request, including deep
    inside a service that has no idea it's inside an HTTP request, are
    filterable by claim_id in Kibana without every call site plumbing it
    through explicitly."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "claims":
        return parts[1]
    return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_request_id(request_id)
        set_claim_id(_claim_id_from_path(request.url.path))

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Last-resort net -- normally unhandled_exception_handler below
            # already converted this into a response before it gets here.
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.exception("unhandled exception escaped the exception handler", extra={
                "method": request.method, "path": request.url.path, "duration_ms": duration_ms,
            })
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        level = logging.INFO
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        logger.log(level, "request completed", extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        })

        response.headers[REQUEST_ID_HEADER] = request_id
        return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The actual `logger.exception` for an unanticipated error lives here
    -- see the module docstring for why the middleware's own try/except
    doesn't see these in the normal case."""
    logger.error("unhandled exception", exc_info=exc, extra={
        "method": request.method, "path": request.url.path,
    })
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": get_request_id()},
    )
