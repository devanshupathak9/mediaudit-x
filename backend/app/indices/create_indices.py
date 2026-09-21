"""
Idempotent index creation.

Reads every *.json mapping file in this directory and creates the matching
index name (filename with underscores -> hyphens) in Elasticsearch.

Run with:  python -m app.indices.create_indices
"""
import json
from pathlib import Path

from app.es_client import get_es_client

MAPPINGS_DIR = Path(__file__).parent / "mappings"


def index_name_from_filename(filename: str) -> str:
    return filename.replace(".json", "").replace("_", "-")


def create_all_indices() -> None:
    es = get_es_client()

    for mapping_file in sorted(MAPPINGS_DIR.glob("*.json")):
        index_name = index_name_from_filename(mapping_file.name)
        body = json.loads(mapping_file.read_text())

        if es.indices.exists(index=index_name):
            # Push any newly added fields onto the existing index. Adding
            # fields is always allowed; changing an existing field's type
            # is not, and will raise here rather than silently diverge.
            es.indices.put_mapping(index=index_name, body=body["mappings"])
            print(f"[update] {index_name} already exists, mapping synced")
            continue

        es.indices.create(index=index_name, body=body)
        print(f"[create] {index_name}")

    print("\nDone. Indices in cluster:")
    for name in sorted(es.indices.get_alias(index="*").keys()):
        if not name.startswith("."):
            print(f"  - {name}")


def ensure_indices() -> list[str]:
    """
    Creates any index from mappings/ that doesn't exist yet, and adds new
    fields from the mapping files to indices that do (adding fields is
    always allowed). Called on API startup so schema changes apply without
    running this script. Returns the names created.
    """
    es = get_es_client()
    created = []
    for mapping_file in sorted(MAPPINGS_DIR.glob("*.json")):
        index_name = index_name_from_filename(mapping_file.name)
        body = json.loads(mapping_file.read_text())
        if not es.indices.exists(index=index_name):
            es.indices.create(index=index_name, body=body)
            created.append(index_name)
            continue
        try:
            es.indices.put_mapping(index=index_name, body=body["mappings"])
        except Exception as e:  # noqa: BLE001 - a conflicting field shouldn't block the others
            print(f"[ensure_indices] could not sync mapping for {index_name}: {e}")
    return created


if __name__ == "__main__":
    create_all_indices()
