"""
Central configuration, loaded from environment variables (.env).
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # FIXED (18 Sept): pydantic-settings reads a blank .env line (e.g.
    # "AWS_SESSION_TOKEN=" with nothing after the =) as the empty string
    # "", not None. That empty string then gets passed to boto3/
    # AnthropicBedrock as an actual (invalid) credential value instead of
    # "not provided", which is what caused a real
    # "security token included in the request is invalid" 403 even
    # though only access-key auth (no session token) was intended. This
    # validator normalizes "" -> None for every optional string setting
    # below so a blank .env line always means "not set."
    @field_validator(
        "elastic_cloud_id", "elastic_api_key", "elastic_url", "elastic_username",
        "elastic_password", "aws_access_key_id", "aws_secret_access_key",
        "aws_session_token", "aws_bearer_token_bedrock", "anthropic_api_key",
        "kibana_url",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    # Elastic Cloud Serverless
    elastic_cloud_id: str | None = None
    elastic_api_key: str | None = None

    # Or self-managed / local cluster
    elastic_url: str | None = None
    elastic_username: str | None = None
    elastic_password: str | None = None

    # Elastic Agent Builder (app/agent_builder_client.py, app/agent/
    # chat_agent_builder.py) -- the Kibana URL for this project (distinct
    # from ELASTIC_URL, which is the Elasticsearch endpoint). Reuses
    # ELASTIC_API_KEY for auth; Kibana accepts the same Elasticsearch API
    # key. If unset, the claim chat endpoint falls back to the direct
    # Bedrock/Anthropic tool-loop in app/agent/chat.py.
    kibana_url: str | None = None
    chat_provider: str = "agent_builder"  # "agent_builder" | "bedrock"

    # LLM provider: "bedrock" (default -- AWS is a hackathon sponsor, use
    # their platform) or "anthropic" (direct Anthropic API, e.g. for local
    # dev if you don't have Bedrock model access set up yet).
    llm_provider: str = "bedrock"

    # AWS Bedrock. Credentials are optional here: if left unset, boto3's
    # normal credential chain is used instead (AWS_ACCESS_KEY_ID/
    # AWS_SECRET_ACCESS_KEY env vars, ~/.aws/credentials, an IAM role, SSO,
    # etc.) -- set these explicitly only if you want the .env file itself
    # to carry the credentials.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_region: str = "us-east-1"

    # ADDED (18 Sept): AWS's newer Bedrock API key -- a single self-
    # contained bearer-token credential (ABSK-prefixed, ~132 chars),
    # distinct from a classic IAM access-key-id/secret-access-key SigV4
    # pair. If this is set, _make_llm_client() (agent/orchestrator.py)
    # uses bearer-token auth instead of SigV4 and ignores
    # aws_access_key_id/aws_secret_access_key/aws_session_token entirely
    # -- don't set both auth styles at once, the bearer token takes
    # priority. Get one from AWS Console -> Bedrock -> API keys, or
    # generate one long-term via IAM's CreateServiceSpecificCredential
    # for bedrock.amazonaws.com.
    aws_bearer_token_bedrock: str | None = None

    # Bedrock model ID (or cross-region inference profile ID, e.g. prefixed
    # "us."). VERIFY THIS against your own AWS account: Bedrock requires
    # explicit per-model access approval (AWS Console -> Bedrock -> Model
    # access) and exact ID strings can differ by region/account. Check
    # Console -> Bedrock -> Model catalog for the exact string before the
    # event if this default doesn't match what's enabled for you.
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Direct Anthropic API (used only if llm_provider="anthropic")
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    # OCR (Stage 2 of Architecture Plan.txt). "tesseract" runs local
    # Tesseract OCR for scanned pages/images (needs the tesseract binary
    # installed separately -- see backend/README); "none" skips OCR
    # entirely and scanned pages come back ocr_status=FAILED; "textract"
    # is spec'd but not yet implemented here (unverified AWS Bedrock-style
    # per-account setup, same caveat as BEDROCK_MODEL_ID above).
    ocr_provider: str = "tesseract"

    # Explicit path to tesseract.exe if it isn't on PATH (common on
    # Windows, e.g. "C:\\Program Files\\Tesseract-OCR\\tesseract.exe").
    tesseract_cmd: str | None = None

    app_env: str = "development"

    # Browser origins allowed to call the API (CORS), comma-separated,
    # e.g. "https://app.example.com,http://187.77.130.9:3000". "*" allows any.
    cors_origins: str = "http://localhost:3000"

    # Logging/monitoring (app/observability/). Every module logs via
    # logging.getLogger(__name__) under the "app.*" namespace; log_level
    # sets that namespace's threshold (uvicorn/elasticsearch-py/boto3's
    # own loggers are untouched). log_to_elasticsearch ships the same
    # records to the app-logs index for Kibana -- turn off for local dev
    # if you don't want per-request docs landing on a shared cluster.
    log_level: str = "INFO"
    log_to_elasticsearch: bool = True

    # Document ingestion (app/pipeline/ingestion). Limits are enforced by
    # the checks in app/pipeline/ingestion/checks.py.
    upload_dir: str | None = None  # default: backend/uploads
    max_upload_mb: int = 20
    max_files_per_upload: int = 20
    max_pdf_pages: int = 200
    min_image_side_px: int = 300


settings = Settings()
