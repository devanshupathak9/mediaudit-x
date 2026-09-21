"""
FastAPI application entrypoint.

Run with: uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.logging_config import configure_logging as configure_basic_logging
configure_basic_logging()

from app.config import settings
from app.indices.create_indices import ensure_indices
from app.observability.logging_config import configure_logging as configure_app_logging, get_app_logger, stop_logging
from app.observability.middleware import RequestLoggingMiddleware, unhandled_exception_handler
from app.pipeline.ingestion.storage import upload_root
from app.routers import chat, claims, adjudication, intake, ocr, patients, audit

# Two layers, not a conflict: configure_basic_logging() (app/logging_config.py)
# sets up the root logger's baseline -- shared with the standalone CLI
# scripts (claim_draft_tool.py, load_sample_evidence.py) so they behave
# the same whether run alone or imported here. configure_app_logging()
# then layers the enhanced JSON-stdout + Elasticsearch-shipping handlers
# onto the "app.*" logger namespace specifically (propagate=False), which
# is why it has to run second -- see app/observability/logging_config.py.
configure_app_logging(settings.log_level, settings.log_to_elasticsearch)
logger = get_app_logger(__name__)

UPLOAD_DIR = upload_root()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MediAudit-X API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(intake.router)
app.include_router(claims.router)
app.include_router(ocr.router)
app.include_router(chat.router)
app.include_router(adjudication.router)
app.include_router(patients.router)
app.include_router(audit.router)

# Serves files stored by the ingestion stage. Local disk, not an object
# store -- see app/pipeline/ingestion/storage.py for the swap-to-S3 note.
app.mount("/files", StaticFiles(directory=UPLOAD_DIR), name="files")


@app.on_event("startup")
def create_missing_indices():
    # Don't block startup if Elasticsearch is unreachable; requests will
    # surface the connection error instead.
    try:
        created = ensure_indices()
        if created:
            logger.info("Created indices", extra={"indices": created})
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not check/create indices", exc_info=e)


@app.on_event("shutdown")
def flush_logs():
    stop_logging()


@app.get("/health")
def health():
    """Pure liveness check -- unconditional, no Elasticsearch dependency,
    so Docker's HEALTHCHECK (which hits this) doesn't flap just because
    Elasticsearch is briefly slow or unreachable. See /health/es for a
    real connectivity check."""
    return {"status": "ok"}


@app.get("/health/es")
def health_es():
    from app.es_client import get_es_client

    try:
        info = get_es_client().info()
        return {"status": "ok", "cluster_name": info.get("cluster_name"), "version": info["version"]["number"]}
    except Exception as e:  # noqa: BLE001 -- reporting the failure IS the point of this endpoint
        logger.warning("Elasticsearch health check failed", exc_info=e)
        return {"status": "unreachable", "error": str(e)}
