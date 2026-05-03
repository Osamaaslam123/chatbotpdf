"""End-to-end smoke test for the Smarted backend.

Run while uvicorn is up on :8000.

    python test_e2e.py

What it checks (in order):
  1. /health responds OK and shows which LLM is wired up
  2. A sample PDF gets uploaded
  3. /list_indexed shows the new doc inside the vector DB
  4. /chat returns an answer that mentions the seeded fact
  5. /chat/stream produces a non-empty SSE stream

Designed to be readable: each step prints a green check or a red x.
"""
from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path

import requests
from pypdf import PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

BASE = "http://127.0.0.1:8000"
SAMPLE_PDF = Path(__file__).parent / "data" / "pdfs" / "smarted_selftest.pdf"


# --------------------------- helpers ----------------------------------- #


def _ok(label: str, detail: str = "") -> None:
    print(f"  [OK] {label}{(' - ' + detail) if detail else ''}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  [FAIL] {label}{(' - ' + detail) if detail else ''}")
    sys.exit(1)


def _section(title: str) -> None:
    print()
    print(f"\033[1m{title}\033[0m")
    print("-" * len(title))


# --------------------------- create test PDF --------------------------- #


def _make_sample_pdf(path: Path) -> None:
    """Generate a tiny chemistry / maths cheat-sheet PDF so we have something
    deterministic to query against."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    text = c.beginText(72, 720)
    text.setFont("Helvetica", 12)
    for line in textwrap.dedent(
        """
        Smarted Self-Test Notes

        Chemistry: The chemical formula for water is H2O. Water is composed
        of two hydrogen atoms bonded to one oxygen atom. Carbon dioxide is
        CO2. The pH of pure water at 25 degrees Celsius is 7.

        Maths: The Pythagorean theorem states that a squared plus b squared
        equals c squared, where c is the length of the hypotenuse of a
        right triangle. The square root of 144 is 12.

        Urdu: یہ ایک اردو جملہ ہے برائے امتحان۔
        """
    ).strip().splitlines():
        text.textLine(line)
    c.drawText(text)
    c.save()


# --------------------------- steps ------------------------------------- #


def step_health() -> dict:
    _section("1. /health")
    try:
        r = requests.get(f"{BASE}/health", timeout=10)
        r.raise_for_status()
    except Exception as e:
        _fail("/health unreachable", str(e))
    data = r.json()
    if not data.get("ok"):
        _fail("/health returned ok=false", json.dumps(data))
    llm = data.get("llm", {})
    backends = [k for k, v in llm.items() if v]
    if not backends:
        _fail("no LLM key configured", "set GROQ_API_KEY in backend/.env and restart")
    _ok("backend up", f"LLM={','.join(backends)}, STT={data.get('stt')}")
    return data


def step_upload() -> None:
    _section("2. /upload sample PDF")
    if not SAMPLE_PDF.exists():
        try:
            _make_sample_pdf(SAMPLE_PDF)
            _ok("created sample PDF", str(SAMPLE_PDF))
        except ImportError:
            _fail(
                "reportlab missing",
                "pip install reportlab  (only needed by this test script)",
            )
    with SAMPLE_PDF.open("rb") as f:
        r = requests.post(
            f"{BASE}/upload",
            files={"file": (SAMPLE_PDF.name, f, "application/pdf")},
            timeout=30,
        )
    if r.status_code != 200:
        _fail("/upload failed", f"{r.status_code} {r.text}")
    _ok("upload accepted", r.json().get("filename", ""))

    # Background ingest takes a few seconds (embedding model load + chunking).
    print("  ...waiting 12s for background ingestion...")
    time.sleep(12)


def step_list_indexed(expected_source: str) -> None:
    _section("3. /list_indexed")
    r = requests.get(f"{BASE}/list_indexed", timeout=15)
    if r.status_code != 200:
        _fail("/list_indexed failed", f"{r.status_code} {r.text}")
    data = r.json()
    sources = {d["source"] for d in data.get("documents", [])}
    if expected_source not in sources:
        _fail(
            f"PDF '{expected_source}' not indexed yet",
            f"current sources={sources}",
        )
    _ok(
        "vector store contains the upload",
        f"total_chunks={data.get('total_chunks')}",
    )


def step_chat() -> None:
    _section("4. /chat (one-shot)")
    payload = {
        "query": "What is the chemical formula for water according to my notes?",
        "language": "english",
        "model": "auto",
    }
    r = requests.post(f"{BASE}/chat", json=payload, timeout=60)
    if r.status_code != 200:
        _fail("/chat failed", f"{r.status_code} {r.text}")
    data = r.json()
    answer = (data.get("answer") or "").lower()
    # The system prompt asks the model to SPEAK chemistry formulas as
    # "H two O" (blind-friendly), so we accept either the spoken form or
    # the literal H2O.
    matches_water = (
        "h2o" in answer
        or "h 2 o" in answer
        or "h two o" in answer
        or ("hydrogen" in answer and "oxygen" in answer)
    )
    if not matches_water:
        _fail(
            "answer doesn't reference water composition",
            data.get("answer", ""),
        )
    _ok("RAG retrieved water answer", data.get("answer", "")[:120].replace("\n", " "))


def step_chat_stream() -> None:
    _section("5. /chat/stream (SSE)")
    payload = {
        "query": "What does the Pythagorean theorem say?",
        "language": "english",
        "model": "auto",
    }
    chunks = []
    try:
        with requests.post(
            f"{BASE}/chat/stream",
            json=payload,
            stream=True,
            timeout=60,
        ) as r:
            if r.status_code != 200:
                _fail("/chat/stream failed", f"{r.status_code} {r.text}")
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if raw.startswith("data:"):
                    raw = raw[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    j = json.loads(raw)
                    if "delta" in j:
                        chunks.append(j["delta"])
                except Exception:
                    chunks.append(raw)
    except Exception as e:
        _fail("/chat/stream errored", str(e))
    full = "".join(chunks).lower()
    if not full:
        _fail("stream returned no content")
    # Accept any of the natural ways the model might say it.
    keywords = ["squared", "hypoten", "right triangle", "a square", "b square"]
    if not any(k in full for k in keywords):
        _fail("stream answer didn't reference Pythagorean theorem", full[:160])
    _ok("stream produced answer", full[:120].replace("\n", " "))


# --------------------------- main -------------------------------------- #


def main() -> None:
    print(f"\n\033[1mSmarted backend self-test\033[0m  ->  {BASE}\n")
    step_health()
    step_upload()
    step_list_indexed(SAMPLE_PDF.name)
    step_chat()
    step_chat_stream()
    print("\n\033[1;92mAll checks passed.\033[0m  RAG pipeline is healthy.\n")


if __name__ == "__main__":
    main()
