"""
One shared logging setup, used by both the FastAPI app (main.py) and the
standalone CLI tools (claim_draft_tool.py, ingestion scripts) so log output
looks the same and shows up either way -- without this, module-level
`logging.getLogger(__name__).info(...)` calls are silently dropped by
Python's default "no handler configured" behavior.
"""
import logging
import os

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Elasticsearch's own client logs every request at INFO, which drowns
    # out the app's own logs -- keep it at WARNING unless someone sets
    # LOG_LEVEL=DEBUG to specifically dig into ES request/response bodies.
    if level != "DEBUG":
        logging.getLogger("elastic_transport").setLevel(logging.WARNING)
    _CONFIGURED = True
