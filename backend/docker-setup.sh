#!/bin/sh
# One-shot setup run by docker compose before the backend starts, against
# the Elasticsearch configured in backend/.env:
#   1. check the connection
#   2. create missing indices (existing ones get new fields added)
#   3. load sample data only if insurance-claims is empty, unless
#      SEED_SAMPLE_DATA=false (the loaders index without ids, so
#      re-running them duplicates data)
set -e

python -c "
from app.es_client import get_es_client
info = get_es_client().info()
print(f\"[setup] connected to Elasticsearch {info['version']['number']} ({info['cluster_name']})\")
" || { echo "[setup] ERROR: can't reach Elasticsearch. Check ELASTIC_URL / ELASTIC_CLOUD_ID / ELASTIC_API_KEY in backend/.env"; exit 1; }

python -m app.indices.create_indices

if [ "${SEED_SAMPLE_DATA:-true}" = "false" ]; then
  echo "[setup] SEED_SAMPLE_DATA=false, skipping sample data"
  exit 0
fi

CLAIMS=$(python -c "from app.es_client import get_es_client; print(get_es_client().count(index='insurance-claims')['count'])")
if [ "$CLAIMS" = "0" ]; then
  echo "[setup] insurance-claims is empty, loading sample data"
  for loader in load_sample_data load_real_cms_policies ingest_synthea_samples; do
    python -m "app.ingestion.$loader" || echo "[setup] WARNING: $loader failed, continuing"
  done
else
  echo "[setup] $CLAIMS claims already in insurance-claims, skipping sample data"
fi
