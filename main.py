"""FastAPI entrypoint for Smarted backend.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routes import chat, health, transcribe, upload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="Smarted RAG backend",
    description="LangChain + Chroma + Whisper + Llama 3 / Gemini / OpenAI router.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allow_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["meta"])
app.include_router(chat.router, tags=["chat"])
app.include_router(transcribe.router, tags=["voice"])
app.include_router(upload.router, tags=["docs"])


@app.on_event("startup")
async def _startup():
    log = logging.getLogger("startup")
    if not settings.has_any_llm():
        log.warning(
            "No LLM API key set in .env — /chat will return 503. Set GROQ_API_KEY (free) at https://console.groq.com/keys"
        )
    else:
        log.info("Smarted backend ready. Vector store: %s", settings.chroma_dir)

    # Auto-ingest: if data/pdfs/ has files but the vector store is empty,
    # ingest them on startup so the user can just drop PDFs in and run.
    try:
        from routes.upload import _ingest_folder
        from services.retriever import get_vectorstore

        settings.pdf_dir.mkdir(parents=True, exist_ok=True)
        pdfs = list(settings.pdf_dir.glob("*.pdf"))
        if not pdfs:
            log.info("No PDFs in %s yet — drop some in and POST /ingest_all", settings.pdf_dir)
            return

        vdb = get_vectorstore(settings)
        existing = vdb._collection.count()  # noqa: SLF001
        if existing == 0:
            log.info("Found %d PDF(s) but vector store is empty — auto-ingesting…", len(pdfs))
            summary = _ingest_folder(settings)
            log.info("Auto-ingest complete: %s", summary)
        else:
            log.info("Vector store already has %d chunk(s); skipping auto-ingest", existing)
    except Exception as e:
        log.warning("Auto-ingest skipped: %s", e)
