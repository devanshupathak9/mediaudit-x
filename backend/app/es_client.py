"""
Elasticsearch client singleton.

Supports three connection shapes:
  1. Classic Elastic Cloud (hosted deployments): cloud_id + api_key.
  2. Elastic Cloud Serverless: url (the project's https://...es....elastic.cloud
     endpoint) + api_key. Serverless projects don't expose a classic
     base64 Cloud ID and don't support basic auth — API key over the
     endpoint URL is the only supported auth method.
  3. Self-managed / local Docker cluster: url + basic auth
     (username/password), or url with no auth at all for a local dev
     cluster running with security disabled.

BUILT LIVE (18 Sept) — fixed after discovering during local setup that a
Serverless project's "connection details" panel gives you a URL endpoint,
not a Cloud ID, and the original url-only branch only supported basic
auth, which Serverless rejects. Put the project's endpoint URL in
ELASTIC_URL and its API key in ELASTIC_API_KEY (leave ELASTIC_CLOUD_ID
blank) to connect to Serverless with this client.
"""
import logging

from elasticsearch import Elasticsearch
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)


def _clean(value: str | None) -> str | None:
    """Strips whitespace and wrapping quotes that Docker env_file keeps."""
    if value is None:
        return None
    value = value.strip().strip('"').strip("'").strip()
    return value or None


@lru_cache
def get_es_client() -> Elasticsearch:
    cloud_id = _clean(settings.elastic_cloud_id)
    api_key = _clean(settings.elastic_api_key)
    url = _clean(settings.elastic_url)

    # A common mix-up: pasting the endpoint URL into ELASTIC_CLOUD_ID.
    # A real Cloud ID is "name:base64..."; a URL means URL-based auth.
    if cloud_id and cloud_id.startswith(("http://", "https://")):
        url = url or cloud_id
        cloud_id = None

    if cloud_id and api_key:
        logger.info("Connecting to Elasticsearch via cloud_id + api_key")
        client = Elasticsearch(cloud_id=cloud_id, api_key=api_key)
        logger.info("Elasticsearch client ready: %s", client.info().get("cluster_name"))
        return client

    if url and api_key:
        # Elastic Cloud Serverless (or any URL-based cluster using API
        # key auth instead of basic auth).
        logger.info("Connecting to Elasticsearch at %s via api_key", url)
        client = Elasticsearch(url, api_key=api_key)
        logger.info("Elasticsearch client ready: %s", client.info().get("cluster_name"))
        return client

    if url:
        auth = None
        username, password = _clean(settings.elastic_username), _clean(settings.elastic_password)
        if username and password:
            auth = (username, password)
        logger.info(
            "Connecting to Elasticsearch at %s via %s",
            url, "basic_auth" if auth else "no auth",
        )
        client = Elasticsearch(url, basic_auth=auth)
        logger.info("Elasticsearch client ready: %s", client.info().get("cluster_name"))
        return client

    logger.error("No Elasticsearch connection configured -- see .env.example")
    raise RuntimeError(
        "No Elasticsearch connection configured. Set either "
        "ELASTIC_CLOUD_ID + ELASTIC_API_KEY (classic Elastic Cloud), or "
        "ELASTIC_URL + ELASTIC_API_KEY (Elastic Cloud Serverless / API-key "
        "auth), or ELASTIC_URL (+ ELASTIC_USERNAME/ELASTIC_PASSWORD for "
        "basic auth) for a self-managed cluster, in your .env file."
    )
