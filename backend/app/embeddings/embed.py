"""
768-dim embedding client for clinical notes and policy text.

BUILT LIVE (18 Sept): implements a deterministic, dependency-light
embedding using feature hashing + TF weighting + L2 normalization. This
was chosen over a downloaded transformer model (e.g. sentence-transformers
all-mpnet-base-v2, which is also 768-dim) for two reasons specific to a
48-hour hackathon:

  1. No model download / no torch install required at event time — the
     venue wifi is not guaranteed, and a ~1-2GB dependency download is a
     real risk on stage.
  2. Deterministic and instant (no first-call model load latency), which
     matters for the live demo's p95 latency numbers.

It is NOT a semantic embedding in the neural sense — it captures shared
vocabulary (tokens, bigrams, medical codes) via random hashed projection,
which is still meaningfully better than the zero-vector stub because
near-duplicate phrasing and shared code tokens land close in vector space.
The RRF fusion in policy_matcher_tool.py compensates for its weaker
semantic recall by leaning on BM25 for exact term matches (which is what
actually matters for CPT/ICD/RxNorm precision per the spec's own thesis).

Swap-in path for a real transformer model, if venue wifi allows:
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    def embed_text(text): return _model.encode(text).tolist()
That's a one-function change — nothing else in the pipeline needs to know
which embedding strategy is in use, since the contract (str -> list[float]
of length EMBED_DIM) doesn't change.
"""
import hashlib
import math
import re

EMBED_DIM = 768

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    words = _TOKEN_RE.findall(text.lower())
    unigrams = words
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return unigrams + bigrams


def _hash_to_index_and_sign(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % dim
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return index, sign


def embed_text(text: str, dim: int = EMBED_DIM) -> list[float]:
    """
    Deterministic hashed bag-of-words/bigrams embedding, L2-normalized.
    Same input always produces the same vector (needed for reproducible
    eval numbers).

    FIXED (18 Sept, found while loading real Synthea Observation records
    that have no code_display/clinician_notes text): empty/whitespace
    input used to return an all-zero vector. That's fine for a plain
    dense_vector field, but notes_vector/policy_vector use `dot_product`
    similarity per the mapping spec, and dot_product strictly requires
    unit-length vectors -- ES rejects an all-zero row at index time with
    a document_parsing_exception ("The [dot_product] similarity can only
    be used with unit-length vectors"), which is a hard failure, not a
    warning. Empty input now hashes a fixed sentinel token instead, so it
    still gets a deterministic, valid unit vector, distinguishable from
    (and never colliding with) any real content's embedding for
    similarity search purposes.
    """
    vector = [0.0] * dim
    tokens = _tokens(text or "") or ["__empty_embedding_input__"]

    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1

    for token, count in counts.items():
        index, sign = _hash_to_index_and_sign(token, dim)
        # log-dampened term frequency so one repeated word doesn't dominate
        weight = sign * (1.0 + math.log(count))
        vector[index] += weight

    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector
