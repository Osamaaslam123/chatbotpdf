# Smarted backend — FastAPI + LangChain + Chroma + Whisper

Voice-first RAG backend for the **Smarted** Flutter app. Built for blind
students learning Maths, Chemistry, and Urdu from their own PDF notes.

## What's inside

| Layer            | Tech                                                        | Cost    |
| ---------------- | ----------------------------------------------------------- | ------- |
| Web framework    | FastAPI + Uvicorn                                           | $0      |
| Speech-to-text   | Groq Whisper-large-v3 → faster-whisper local fallback       | $0      |
| Embeddings       | `paraphrase-multilingual-MiniLM-L12-v2` (HuggingFace, local) | $0      |
| Vector DB        | ChromaDB (embedded, persisted to `./data/chroma`)           | $0      |
| LLM              | Groq Llama 3 70B → Gemini 1.5 Flash → OpenAI (last resort)  | $0 / $0 / paid |
| OCR              | Tesseract (`eng+urd`) via pytesseract / pdf2image           | $0      |

> Out-of-the-box you can run the entire stack on **$0** by setting just
> `GROQ_API_KEY` (free at https://console.groq.com).  The $10 budget you
> mentioned is plenty of headroom — typical dev usage stays at $0.

---

## Endpoints

| Method | Path             | Body                                   | Returns                                          |
| ------ | ---------------- | -------------------------------------- | ------------------------------------------------ |
| GET    | `/health`        | —                                      | `{ ok, llm: {…}, stt, embed_model }`             |
| POST   | `/transcribe`    | multipart `file` + optional `language` | `{ text, language, duration }`                   |
| POST   | `/chat`          | `{ query, language, model }`           | `{ answer, sources[] }`                          |
| POST   | `/chat/stream`   | same                                   | SSE stream of `{ delta }` then `{ sources }`     |
| POST   | `/upload`        | multipart `file` (PDF)                 | `{ ok, filename, queued }` (ingests in BG)       |
| POST   | `/ingest_all`    | —                                      | Re-ingest every PDF in `data/pdfs/`              |
| GET    | `/documents`     | —                                      | PDF files on disk                                |
| GET    | `/list_indexed`  | —                                      | What's in the vector store + chunk counts        |

---

## Three ways to feed PDFs to the tutor

Pick whichever fits your workflow.

### A. Drop into the folder (simplest, no app interaction)
```powershell
# Put any PDFs you want the tutor to know about here:
C:\Users\Khadi\chatbotwith claudeai\backend\data\pdfs\
```
Restart uvicorn. The startup hook auto-ingests anything new on first boot
(when the vector store is empty). For incremental updates use option C.

### B. Upload from the Flutter app
Open Smarted on your phone, tap the **upload** icon in the top-right, pick
PDFs from your phone storage. The app posts them to `/upload` and the
backend ingests in the background.

### C. Re-ingest after dropping new files
```powershell
# Run after dropping more PDFs into data/pdfs/:
Invoke-RestMethod -Method POST http://127.0.0.1:8000/ingest_all
# Returns per-file summary with chunk counts
```

### Verify what the tutor knows about
```powershell
Invoke-RestMethod http://127.0.0.1:8000/list_indexed
# Shows total_chunks + each indexed source filename
```

---

## End-to-end self-test

After installing requirements and starting uvicorn:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python test_e2e.py
```

Generates a sample chemistry/maths PDF, uploads it, queries the RAG
pipeline about water (`H2O`) and the Pythagorean theorem, and verifies
streaming works. Five green checks = the backend is healthy.

---

---

## Setup (one-time)

### 1. System packages (Windows)
```powershell
# Tesseract OCR (with English + Urdu trained data)
# Download: https://github.com/UB-Mannheim/tesseract/wiki
# After install, set in .env:  TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
# Then download urd.traineddata into the tessdata folder.

# Poppler (for pdf2image)
# Download: https://github.com/oschwartz10612/poppler-windows/releases
# Add bin/ to PATH.
```

### 2. Python env
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Free API keys
```powershell
copy .env.example .env
# Edit .env and paste at minimum:
#   GROQ_API_KEY=gsk_...   (https://console.groq.com/keys — free, instant)
# Optional extras:
#   GOOGLE_API_KEY=...     (https://aistudio.google.com/apikey — free)
#   OPENAI_API_KEY=sk-...  (paid)
```

### 4. Run
```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit http://localhost:8000/docs for the OpenAPI / Swagger UI.

---

## Cost-management knobs

The defaults already hold the line at **$0** when using Groq. If you ever
want to dial it tighter:

- `max_tokens=600` on every LLM call (caps reply length, also speeds spoken
  delivery for blind users).
- `k=4` chunks retrieved — small enough to stay well under the 8K context
  window of cheap models.
- Local sentence-transformer embeddings — zero per-token cost; first run
  downloads ~120 MB to `~/.cache/huggingface`.
- ChromaDB embedded mode — no network, no service.
- Whisper via Groq is **free** and ~10× real-time, so transcription is also $0.
- If you exceed Groq's free RPM, the router auto-falls back to Gemini, then
  OpenAI (only if `OPENAI_API_KEY` is set).

---

## How the RAG pipeline runs

1. **Upload** — PDFs land in `./data/pdfs/`, `/upload` queues an
   ingestion task in the background.
2. **Extract** — `pypdf` reads native text first.  If a page is empty or
   sparse, falls back to **Tesseract OCR** with `eng+urd` language data.
3. **Chunk** — `RecursiveCharacterTextSplitter` (900 chars, 120 overlap).
4. **Embed** — multilingual MiniLM produces a single 384-dim embedding
   per chunk that handles Urdu, English, and code-switched text.
5. **Index** — chunks + metadata persisted to ChromaDB.
6. **Query** — `/chat` retrieves top-4 chunks, formats them into the
   blind-friendly system prompt (Maths/Chemistry/Urdu rules), calls the
   selected LLM, and returns answer + sources.

---

## Why these choices for blind students

- **Whisper** for STT — far more accurate than browser STT in noisy
  classrooms and handles Urdu out of the box.
- **System prompt** explicitly bans markdown, ASCII art, raw LaTeX, and
  visual symbols — every answer is written for the ear, not the eye.
- **`max_tokens=600`** keeps spoken answers short by default.
- **Sources field** is plain filenames (no clickable links) so the
  frontend can read them aloud as "according to your physics notes".
- **Chemistry formulas** stay in their natural form ("H2O") — the
  Flutter side has a `SpeechNormalizer` that turns those into "H two O"
  before TTS speaks them.

---

## Troubleshooting

| Symptom                                  | Fix                                                              |
| ---------------------------------------- | ---------------------------------------------------------------- |
| `/chat` → 503 "No LLM available"         | Set `GROQ_API_KEY` in `.env`, restart server.                    |
| `/transcribe` slow & no Groq key         | Local faster-whisper is being used.  Set `GROQ_API_KEY` for 10× speed. |
| OCR returns empty for scanned PDF        | Tesseract or poppler not installed (see Setup §1).               |
| Urdu OCR wrong                           | Make sure `urd.traineddata` is present in tessdata folder.       |
| First Chroma query is slow               | Embedding model loading (~120 MB).  Subsequent queries are fast. |
