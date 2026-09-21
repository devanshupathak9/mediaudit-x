"""
Claim processing pipeline — one package per stage (see ARCHITECTURE.md).

  ingestion/  hospital uploads documents → validated, stored, registered,
              claim created in DRAFT

Later stages (ocr, drafting, review, evidence, ...) are added as sibling
packages. Each stage exposes a small service API and owns its own
Elasticsearch reads/writes; routers stay thin.
"""
