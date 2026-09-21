"""
Tests for app/observability/. Pure unit tests for the formatter/filter/
handler; a couple of FastAPI TestClient tests for the middleware +
exception handler against a minimal app (not the full app.main, so they
need no real Elasticsearch/AWS credentials at import time).
"""
import logging
import sys

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.observability.context import RequestContextFilter, claim_context, set_request_id
from app.observability.es_handler import ElasticsearchLogHandler
from app.observability.formatting import record_to_dict
from app.observability.middleware import RequestLoggingMiddleware, unhandled_exception_handler


def _make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def test_record_to_dict_includes_message_and_extras():
    doc = record_to_dict(_make_record(request_id="req-1", claim_id="CLM-1", status_code=200))
    assert doc["message"] == "hello world"
    assert doc["level"] == "INFO"
    assert doc["logger"] == "app.test"
    assert doc["request_id"] == "req-1"
    assert doc["claim_id"] == "CLM-1"
    assert doc["status_code"] == 200
    assert "@timestamp" in doc


def test_record_to_dict_captures_exception_info():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="app.test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    doc = record_to_dict(record)
    assert doc["error_type"] == "ValueError"
    assert doc["error_message"] == "boom"
    assert "ValueError: boom" in doc["traceback"]


def test_request_context_filter_injects_current_values():
    set_request_id("req-xyz")
    with claim_context("CLM-99"):
        record = _make_record()
        assert RequestContextFilter().filter(record) is True
        assert record.request_id == "req-xyz"
        assert record.claim_id == "CLM-99"
    set_request_id(None)


def test_request_context_filter_defaults_to_none():
    set_request_id(None)
    record = _make_record()
    RequestContextFilter().filter(record)
    assert record.request_id is None
    assert record.claim_id is None


def test_es_log_handler_swallows_failures(capsys):
    def broken_factory():
        raise RuntimeError("no cluster configured")

    ElasticsearchLogHandler(broken_factory).emit(_make_record())  # must not raise

    assert "failed to ship a log record" in capsys.readouterr().err


def test_es_log_handler_indexes_via_factory():
    indexed = []

    class FakeES:
        def index(self, index, document):
            indexed.append((index, document))

    ElasticsearchLogHandler(lambda: FakeES()).emit(_make_record(request_id="req-1"))

    assert len(indexed) == 1
    index_name, doc = indexed[0]
    assert index_name == "app-logs"
    assert doc["request_id"] == "req-1"


# ── middleware / exception handler, via a minimal app ────────────────────

def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/ok")
    def ok():
        return {"hello": "world"}

    @app.get("/boom")
    def boom():
        raise ValueError("something broke")

    @app.get("/missing")
    def missing():
        raise HTTPException(status_code=404, detail="not found")

    return app


def test_request_gets_a_request_id_header():
    resp = TestClient(_build_test_app()).get("/ok")
    assert resp.status_code == 200
    assert len(resp.headers.get("X-Request-ID", "")) > 0


def test_incoming_request_id_is_echoed_back():
    resp = TestClient(_build_test_app()).get("/ok", headers={"X-Request-ID": "my-custom-id"})
    assert resp.headers["X-Request-ID"] == "my-custom-id"


def test_unhandled_exception_returns_clean_500_not_a_traceback():
    resp = TestClient(_build_test_app(), raise_server_exceptions=False).get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal server error"
    assert "request_id" in body
    assert "ValueError" not in resp.text  # no raw traceback leaked to the client


def test_http_exception_handling_is_unaffected_by_the_new_handler():
    resp = TestClient(_build_test_app()).get("/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not found"
