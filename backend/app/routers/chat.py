"""
Claim Q&A chat endpoint -- thin HTTP layer over app.agent.chat and
app.agent.chat_agent_builder (all the actual LLM/tool logic lives there,
same split as intake.py/ocr.py over their own pipeline packages).

Provider selection: settings.chat_provider ("agent_builder" by default,
"bedrock" as the other option) picks which one to try first; if Agent
Builder is selected but errors (unreachable Kibana, tool/agent not
provisioned, etc.), this falls back to the Bedrock/Anthropic tool loop
automatically -- same "always have a deterministic/working fallback"
rule this codebase applies everywhere else an external LLM is involved
(app/llm_client.py, app/pipeline/ocr/extract.py's Tesseract fallback).
"""
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.chat import answer_claim_question
from app.agent.chat_agent_builder import answer_claim_question_via_agent_builder
from app.agent_builder_client import AgentBuilderError, is_configured as agent_builder_configured
from app.config import settings
from app.es_client import get_es_client
from app.indices.names import ALL_CLAIMS

# Not app.observability.get_app_logger: that package lives on a separate,
# not-yet-merged branch (usr/lomindil/logging) -- plain logging.getLogger
# here keeps this feature mergeable independently. Swap to get_app_logger
# once that branch lands; the call shape is identical.
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Used by the Bedrock path only (app.agent.chat re-sends full claim
    # context every turn rather than relying on the model to remember it).
    history: list[ChatMessage] = Field(default_factory=list)
    # Used by the Agent Builder path only -- its conversation state is
    # server-side; pass back the conversation_id a prior response
    # returned to continue that same conversation instead of resending
    # full context every turn.
    conversation_id: str | None = None


class Citation(BaseModel):
    id: str
    type: str
    description: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    conversation_id: str | None = None
    provider: str


def _find_claim(es, claim_id: str) -> dict:
    result = es.search(index=ALL_CLAIMS, query={"term": {"claim_id": claim_id}}, size=1, ignore_unavailable=True)
    hits = result["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=404, detail="Claim not found")
    return hits[0]["_source"]


def _latest_adjudication(es, claim_id: str) -> dict | None:
    result = es.search(
        index="adjudication-results", query={"term": {"claim_id": claim_id}},
        sort=[{"decided_at": "desc"}], size=1,
    )
    hits = result["hits"]["hits"]
    return hits[0]["_source"] if hits else None


@router.post("/{claim_id}/chat", response_model=ChatResponse)
def chat_about_claim(claim_id: str, body: ChatRequest):
    es = get_es_client()
    claim = _find_claim(es, claim_id)
    adjudication = _latest_adjudication(es, claim_id)

    # Deliberately not logging body.question/answer text: a reviewer's
    # free-text question could embed clinical details, and the standing
    # rule (MONITORING.md) is that clinical free-text never reaches a log
    # line. claim_id + shape metadata is enough to debug/monitor this.
    logger.info("claim chat question received", extra={
        "claim_id": claim_id, "question_length": len(body.question), "history_length": len(body.history),
    })

    provider = "bedrock"
    conversation_id = None

    if settings.chat_provider == "agent_builder" and agent_builder_configured():
        try:
            answer, citations, conversation_id = answer_claim_question_via_agent_builder(
                claim=claim, adjudication=adjudication,
                question=body.question, conversation_id=body.conversation_id,
            )
            provider = "agent_builder"
        except AgentBuilderError as e:
            logger.warning("Agent Builder chat failed, falling back to Bedrock", extra={
                "claim_id": claim_id, "error": str(e),
            })
            answer, citations, _ = answer_claim_question(
                claim=claim, adjudication=adjudication,
                question=body.question, history=[h.model_dump() for h in body.history],
            )
    else:
        answer, citations, _ = answer_claim_question(
            claim=claim, adjudication=adjudication,
            question=body.question, history=[h.model_dump() for h in body.history],
        )

    logger.info("claim chat answered", extra={
        "claim_id": claim_id, "provider": provider, "citation_count": len(citations),
    })

    return ChatResponse(
        answer=answer, citations=[Citation(**c) for c in citations],
        conversation_id=conversation_id, provider=provider,
    )
