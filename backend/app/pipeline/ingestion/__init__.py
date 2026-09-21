"""
Ingestion stage — see service.py for the flow, checks.py for what gets
validated. Use get_ingestion_service() rather than wiring the parts by
hand, so the router, scripts and later stages share one configuration.
"""
from app.config import settings
from app.pipeline.ingestion.models import Limits
from app.pipeline.ingestion.repository import IngestionRepository
from app.pipeline.ingestion.service import IngestionService
from app.pipeline.ingestion.storage import LocalBlobStore


def get_ingestion_service() -> IngestionService:
    return IngestionService(
        repository=IngestionRepository(),
        blob_store=LocalBlobStore(),
        limits=Limits.from_settings(settings),
    )
