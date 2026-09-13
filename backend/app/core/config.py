"""Central configuration for data-master-ai (数据问数 / AI Agent Platform).

Provider-agnostic by design: models can be served by AWS Bedrock (Anthropic
native Messages API + Cohere embed/rerank, SigV4 or bearer auth) OR by any
OpenAI-compatible endpoint (DashScope / vLLM / the Bedrock OpenAI gateway).

The platform itself is generic — data-master问数 is just one *agent* configured
in the DB (see app/platform). Nothing here hardcodes data-master; the default
MCP registry seed merely points the flagship agent at data-master's /api/mcp.
"""

from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "AgentWorks"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8700
    CORS_ORIGINS: str = "*"  # comma-separated, "*" = all (frontend is a separate origin)

    # ── LLM provider selection ───────────────────────────────────────────────
    # "bedrock" -> Bedrock (Anthropic native for claude-*, Cohere for embed/rerank)
    # "openai"  -> any OpenAI-compatible /v1 endpoint
    LLM_PROVIDER: str = "bedrock"
    LLM_ENABLED: bool = True          # False -> deterministic mock replies (offline dev)
    LLM_TOOL_CHOICE: str = ""         # "" | "auto" | "none" (OpenAI path only)

    # ── Bedrock ──────────────────────────────────────────────────────────────
    BEDROCK_REGION: str = "ap-southeast-1"
    BEDROCK_BASE_URL: str = ""        # override bedrock-mantle gateway URL; blank = auto
    BEDROCK_CHAT_MODEL: str = "global.anthropic.claude-sonnet-5"
    BEDROCK_QUERY_REWRITER_MODEL: str = ""  # blank -> reuse BEDROCK_CHAT_MODEL
    BEDROCK_ANTHROPIC_MAX_TOKENS: int = 16000
    # "bearer" (QA/prod, needs bedrock:CallWithBearerToken) | "sigv4" (local SSO role)
    BEDROCK_ANTHROPIC_AUTH_MODE: str = "sigv4"

    # Bedrock embeddings (Cohere embed-v4 / Titan)
    EMBEDDING_BEDROCK_ENABLED: bool = True
    BEDROCK_EMBEDDING_MODEL: str = "global.cohere.embed-v4:0"
    BEDROCK_EMBEDDING_REGION: str = "ap-southeast-1"
    BEDROCK_EMBEDDING_DIMENSION: int = 1024

    # Bedrock reranker (Cohere rerank v3.5)
    RERANKER_BEDROCK_ENABLED: bool = True
    BEDROCK_RERANKER_MODEL: str = "cohere.rerank-v3-5:0"
    BEDROCK_RERANKER_REGION: str = "ap-northeast-1"

    # ── OpenAI-compatible provider (used when LLM_PROVIDER=openai, or as fallback) ─
    OPENAI_BASE_URL: str = ""         # e.g. http://host:8080/v1  or  https://api.openai.com/v1
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_QUERY_REWRITER_MODEL: str = ""

    # OpenAI-compatible embeddings (used when EMBEDDING_BEDROCK_ENABLED=false)
    EMBEDDING_API_ENABLED: bool = False
    EMBEDDING_API_URL: str = ""       # e.g. http://host:8081  (-> /v1/embeddings)
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_API_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024   # dimension when using the API path

    # OpenAI-compatible reranker (used when RERANKER_BEDROCK_ENABLED=false)
    RERANKER_API_ENABLED: bool = False
    RERANKER_API_URL: str = ""        # e.g. http://host:8082  (-> /rerank)

    # ── Vector store (Milvus; milvus-lite runs with zero infra) ──────────────
    # VECTOR_DB_URI: a "*.db" file path -> milvus-lite (embedded), else a server URI
    VECTOR_DB_URI: str = "./data/milvus_lite.db"
    VECTOR_DB_TOKEN: str = ""
    VECTOR_DB_NAME: str = "default"
    VECTOR_COLLECTION_PREFIX: str = "aw_rag"  # per-agent collection = {prefix}_{agent_id}

    # ── RAG ──────────────────────────────────────────────────────────────────
    RAG_TOP_K: int = 6
    RAG_CANDIDATE_K: int = 24         # fetched from vector store before rerank
    RAG_SCORE_THRESHOLD: float = 0.30
    RAG_RERANK_ENABLED: bool = True
    QUERY_REWRITE_ENABLED: bool = True
    QUERY_REWRITE_MAX_QUERIES: int = 3

    # ── Memory / checkpointer ────────────────────────────────────────────────
    # "memory" (in-process) | "sqlite" (file) | "postgres"
    CHECKPOINTER: str = "memory"
    CHECKPOINTER_SQLITE_PATH: str = "./data/checkpoints.sqlite"

    # ── Metadata / platform config / trace store ─────────────────────────────
    # SQLAlchemy URL. Default = self-contained SQLite; point at Postgres for prod.
    DATABASE_URL: str = "sqlite:///./data/platform.sqlite"

    # ── Agent loop safety ────────────────────────────────────────────────────
    AGENT_MAX_TOOL_TURNS: int = 8
    AGENT_TOOL_TIMEOUT_SECONDS: float = 30.0

    # ── Identity ─────────────────────────────────────────────────────────────
    # Platform-issued JWT is validated (HS256 local dev), then passed through to
    # every MCP server the agent federates. The AI project makes no authz decision.
    PLATFORM_JWT_SECRET: str = "dev-only-change-me"
    PLATFORM_JWT_ALG: str = "HS256"
    PLATFORM_JWT_AUDIENCE: str = "data-master-ai"
    # When true, unauthenticated requests get a dev principal (local only).
    ALLOW_ANONYMOUS: bool = True
    DEV_PRINCIPAL_SUB: str = "dev|local"


settings = Settings()
