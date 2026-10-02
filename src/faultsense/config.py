"""Runtime settings, read from environment variables and the project's .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = ""
    db_schema: str = "public"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-5-5"
    llm_api_key: str = ""
    llm_effort: str = "high"
    ollama_url: str = "http://localhost:11434"  # LLM_PROVIDER=ollama runs a local open-weight model
    ollama_num_ctx: int = 16384  # prompts carry 8+ manual passages; Ollama's default context is shorter
    ollama_think: bool = False
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "cuda"
    evidence_threshold: float = 0.14  # tuned from eval runs; see README "Tuning"
    cause_match_threshold: float = 0.65  # tuned from eval cause pairs; see README "Tuning"
    query_rewrite: bool = True  # LLM rewrite of code-less queries into manual vocabulary (retrieval only)
    rewrite_effort: str = "low"
    # The rewrite can run on a different model from the diagnosis, e.g. Claude for this short call and a
    # local Ollama model for the diagnosis. Empty means the same provider/model as the diagnosis.
    rewrite_provider: str = ""
    rewrite_model: str = ""

    @property
    def effective_rewrite_provider(self) -> str:
        return self.rewrite_provider or self.llm_provider

    @property
    def effective_rewrite_model(self) -> str:
        return self.rewrite_model or self.llm_model
    data_dir: Path = PROJECT_ROOT / "data"
    eval_runs_dir: Path = PROJECT_ROOT / "eval_runs"

    @property
    def manuals_dir(self) -> Path:
        return self.data_dir / "manuals"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"


def get_settings() -> Settings:
    return Settings()
