"""
OCR stage -- see service.py for the flow. Use get_ocr_service() rather
than wiring the parts by hand, matching app.pipeline.ingestion's pattern.
"""
from app.pipeline.ocr.repository import OCRRepository
from app.pipeline.ocr.service import OCRService


def get_ocr_service() -> OCRService:
    return OCRService(repository=OCRRepository())
