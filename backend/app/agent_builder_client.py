"""
Thin client for Elastic Agent Builder's Kibana REST API (tools, agents,
converse). Distinct from app/llm_client.py (which talks to Claude
directly via Bedrock/Anthropic) -- this talks to Kibana instead, which
internally picks its own LLM connector (see setup_agent_builder.py's
docstring for which one this project uses).

Docs verified against the live API on this project's Kibana instance,
not assumed from memory:
  https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/kibana-api
  https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/agent-builder-api-tutorial
"""
import requests

from app.config import settings

_TIMEOUT = 60


class AgentBuilderError(Exception):
    """Wraps a non-2xx response from the Agent Builder API with the
    actual response body, so callers can log/handle it without needing
    to know requests' exception shapes."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"Agent Builder API returned {status_code}: {body[:500]}")
        self.status_code = status_code
        self.body = body


def _headers() -> dict:
    return {
        "Authorization": f"ApiKey {settings.elastic_api_key}",
        "kbn-xsrf": "true",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    if not settings.kibana_url:
        raise AgentBuilderError(0, "KIBANA_URL is not configured")
    return settings.kibana_url.rstrip("/") + "/api/agent_builder"


def _request(method: str, path: str, json_body: dict | None = None) -> dict:
    resp = requests.request(method, f"{_base_url()}{path}", headers=_headers(), json=json_body, timeout=_TIMEOUT)
    if resp.status_code >= 300:
        raise AgentBuilderError(resp.status_code, resp.text)
    return resp.json() if resp.text else {}


def _already_exists(e: "AgentBuilderError") -> bool:
    """The API returns plain 400 Bad Request (not 409 Conflict) for a
    duplicate id -- verified against the real API, not assumed -- so
    upsert has to check the message text instead of the status code."""
    return e.status_code == 400 and "already exists" in e.body


def is_configured() -> bool:
    return bool(settings.kibana_url and settings.elastic_api_key)


def list_tools() -> list[dict]:
    return _request("GET", "/tools").get("results", [])


def upsert_esql_tool(tool_id: str, description: str, query: str, params: dict) -> dict:
    """Creates the tool, or updates it in place if it already exists --
    same idempotent create-or-update shape as create_indices.py uses for
    index mappings, so re-running setup is always safe."""
    body = {
        "id": tool_id,
        "type": "esql",
        "description": description,
        "configuration": {"query": query, "params": params},
    }
    try:
        return _request("POST", "/tools", body)
    except AgentBuilderError as e:
        if not _already_exists(e):
            raise
        return _request("PUT", f"/tools/{tool_id}", {
            "description": description,
            "configuration": {"query": query, "params": params},
        })


def upsert_agent(agent_id: str, name: str, description: str, instructions: str, tool_ids: list[str]) -> dict:
    body = {
        "id": agent_id,
        "name": name,
        "description": description,
        "configuration": {"instructions": instructions, "tools": [{"tool_ids": tool_ids}]},
    }
    try:
        return _request("POST", "/agents", body)
    except AgentBuilderError as e:
        if not _already_exists(e):
            raise
        return _request("PUT", f"/agents/{agent_id}", {
            "name": name, "description": description,
            "configuration": {"instructions": instructions, "tools": [{"tool_ids": tool_ids}]},
        })


def converse(agent_id: str, input_text: str, conversation_id: str | None = None) -> dict:
    body = {"agent_id": agent_id, "input": input_text}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return _request("POST", "/converse", body)
