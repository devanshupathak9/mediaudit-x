"""
Combines local (deterministic) candidates with the LLM's own pick for a
field into a ranked list, and the top rank decides the final code -- "both
the browser/global knowledge and the local dictionary content, add the
ranker, get the rank and add the code based on ranking."

Score components:
  - local candidate base score, summed across every supporting span on the
    same page as the LLM's citation (regex 1.0 / dictionary 0.7 per
    ARCHITECTURE.md Stage 3a; more corroborating mentions = stronger).
    Negated mentions are dropped entirely; historical mentions halved.
  - +LLM_SELECTED_BONUS if the LLM itself picked this code.
  - +WEB_SEARCH_BONUS if the LLM verified it via the web_search tool.
  - learned-correction adjustment: past coder corrections for text that
    resembles this candidate's cited span push its score up if it's the
    code the coder confirmed, down if it's the code the coder rejected --
    see feedback.py, this is the loop that lets rejections retrain ranking.
"""
import logging

logger = logging.getLogger(__name__)

LLM_SELECTED_BONUS = 0.5
WEB_SEARCH_BONUS = 0.4
LEARNED_CORRECTION_BOOST = 0.6
LEARNED_CORRECTION_PENALTY = 0.6
OVERLAP_THRESHOLD = 0.3


def _local_score(spans: list[dict]) -> float:
    total = 0.0
    for span in spans:
        if span.get("context") == "negated":
            continue
        base = span["score"]
        if span.get("context") == "historical":
            base *= 0.5
        total += base
    return total


def _text_overlap(a: str, b: str) -> float:
    """Cheap token-overlap similarity -- good enough to decide whether a
    past correction's context resembles this candidate's, not a real NLP
    similarity metric."""
    tokens_a, tokens_b = set(a.lower().split()), set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _learned_adjustment(code: str, cited_text: str, learned_corrections: list[dict]) -> float:
    adjustment = 0.0
    for correction in learned_corrections:
        overlap = _text_overlap(cited_text, correction.get("cited_text", ""))
        if overlap < OVERLAP_THRESHOLD:
            continue
        if correction.get("corrected_code") == code:
            adjustment += LEARNED_CORRECTION_BOOST * overlap
        elif correction.get("rejected_code") == code:
            adjustment -= LEARNED_CORRECTION_PENALTY * overlap
    return adjustment


def rank_field(llm_item: dict, code_system: str, local_candidates: list[dict],
                learned_corrections: list[dict]) -> dict:
    """
    local_candidates should already be narrowed to the same page as the
    LLM's citation (doc_id + page_number) -- ranking is "which code best
    explains this particular mention," not a document-wide popularity
    contest.

    Returns {code, description, cited_text, doc_id, page_number, score,
    sources, alternatives: [{code, description, score}]}. The returned
    code/description is the TOP-ranked one, which may differ from what the
    LLM said if local evidence (or a learned correction) outranks it.
    """
    by_code: dict[str, dict] = {}
    for cand in local_candidates:
        if cand["code_system"] != code_system:
            continue
        entry = by_code.setdefault(cand["code"], {
            "code": cand["code"], "description": cand["display"], "spans": [], "sources": set(),
        })
        entry["spans"].append(cand)
        entry["sources"].add("local_dictionary")

    llm_code = llm_item.get("code")
    if llm_code:
        entry = by_code.setdefault(llm_code, {
            "code": llm_code, "description": llm_item.get("description", ""), "spans": [], "sources": set(),
        })
        entry["sources"].add("web_search_verified" if llm_item.get("source") == "web_search" else "llm_selected")

    cited_text = llm_item.get("cited_text", "")
    ranked = []
    for code, entry in by_code.items():
        score = _local_score(entry["spans"])
        if "llm_selected" in entry["sources"]:
            score += LLM_SELECTED_BONUS
        if "web_search_verified" in entry["sources"]:
            score += WEB_SEARCH_BONUS
        span_text = entry["spans"][0]["text"] if entry["spans"] else cited_text
        score += _learned_adjustment(code, span_text, learned_corrections)
        ranked.append({
            "code": code,
            "description": entry["description"] or llm_item.get("description", ""),
            "score": round(score, 3),
            "sources": sorted(entry["sources"]),
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)

    top = ranked[0] if ranked else {
        "code": llm_code, "description": llm_item.get("description", ""), "score": 0.0, "sources": ["llm_selected"],
    }
    alternatives = ranked[1:4] if len(ranked) > 1 else []

    logger.info("Ranked %s field: top=%s(%.2f) alternatives=%s",
                code_system, top["code"], top["score"], [(a["code"], a["score"]) for a in alternatives])

    return {
        "code": top["code"],
        "description": top["description"],
        "cited_text": cited_text,
        "doc_id": llm_item.get("doc_id"),
        "page_number": llm_item.get("page_number"),
        "score": top["score"],
        "sources": top["sources"],
        "alternatives": [{"code": a["code"], "description": a["description"], "score": a["score"]} for a in alternatives],
    }
