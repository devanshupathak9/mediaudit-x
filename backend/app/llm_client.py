"""
Shared Claude client factory — Bedrock by default, direct Anthropic API
as a fallback.

Extracted from app/agent/orchestrator.py's private _make_llm_client() so
app/tools/claim_draft_tool.py (OCR -> draft claim extraction) can use the
exact same provider logic instead of duplicating it. orchestrator.py now
imports make_llm_client() from here; behavior is unchanged from the
original (including the ADDED 18 Sept Bedrock API key / bearer-token
support and its anthropic>=0.88.0 requirement -- see below).
"""
import logging
import os

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)


def make_llm_client():
    """
    Returns (client, model_id) for whichever provider is configured.

    Default is AWS Bedrock (settings.llm_provider="bedrock") -- constructs
    anthropic.AnthropicBedrock, which authenticates one of two ways:

    1. Bedrock API key (bearer token) -- if settings.aws_bearer_token_bedrock
       is set (AWS's newer ABSK-prefixed long-lived key, from Console ->
       Bedrock -> API keys, or CreateServiceSpecificCredential). ADDED
       (18 Sept): requires anthropic>=0.88.0 (bumped in requirements.txt --
       0.34.2 predates this and only ever SigV4-signs, which rejects an
       ABSK key with a confusing "security token...invalid" 403 that has
       nothing to do with session tokens). The SDK reads this from the
       AWS_BEARER_TOKEN_BEDROCK env var, so it's set there explicitly
       (pydantic-settings loads .env into this process's Settings object,
       not into os.environ, so this has to be done by hand) and
       aws_access_key/aws_secret_key/aws_session_token are left unset --
       passing explicit (even blank) values for those forces the SigV4
       path instead and the bearer token is ignored.
    2. Classic SigV4 (aws_access_key_id/aws_secret_access_key pair) --
       used only if no bearer token is configured. If those are also
       unset, None is passed through and boto3's own default credential
       chain (env vars, ~/.aws/credentials, an IAM role, SSO) resolves
       them at call time.

    Falls back to the direct Anthropic API only if llm_provider is
    explicitly set to "anthropic" in .env (e.g. for local dev without
    Bedrock model access configured yet).
    """
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is unset -- no LLM client available")
            return None, None
        logger.info("Using direct Anthropic API, model=%s", settings.anthropic_model)
        return anthropic.Anthropic(api_key=settings.anthropic_api_key), settings.anthropic_model

    if settings.aws_bearer_token_bedrock:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = settings.aws_bearer_token_bedrock
        logger.info("Using AWS Bedrock via bearer-token API key, model=%s, region=%s", settings.bedrock_model_id, settings.aws_region)
        client = anthropic.AnthropicBedrock(aws_region=settings.aws_region)
        return client, settings.bedrock_model_id

    logger.info(
        "Using AWS Bedrock via %s, model=%s, region=%s",
        "explicit access/secret key" if settings.aws_access_key_id else "boto3's default credential chain",
        settings.bedrock_model_id, settings.aws_region,
    )
    client = anthropic.AnthropicBedrock(
        aws_access_key=settings.aws_access_key_id,
        aws_secret_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token,
        aws_region=settings.aws_region,
    )
    return client, settings.bedrock_model_id
