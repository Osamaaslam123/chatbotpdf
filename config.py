"""Centralised settings loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM providers
    groq_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Model names
    groq_llm_model: str = "llama-3.3-70b-versatile"
    groq_whisper_model: str = "whisper-large-v3"
    gemini_model: str = "gemini-1.5-flash"
    openai_model: str = "gpt-4o-mini"
    default_model: str = "auto"

    # Embeddings
    embed_model: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    # Vector store
    chroma_dir: Path = Path("./data/chroma")
    collection_name: str = "smarted"

    # OCR
    pdf_dir: Path = Path("./data/pdfs")
    tesseract_langs: str = "eng+urd"
    tesseract_cmd: Optional[str] = None

    # Local Whisper fallback
    local_whisper_model: str = "base"
    local_whisper_device: str = "cpu"
    local_whisper_compute: str = "int8"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    allow_origins: str = "*"

    def has_any_llm(self) -> bool:
        return bool(self.groq_api_key or self.google_api_key or self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.chroma_dir.mkdir(parents=True, exist_ok=True)
    s.pdf_dir.mkdir(parents=True, exist_ok=True)
    return s
