"""FastAPI backend.

Local:   uvicorn src.api:app --reload        -> http://127.0.0.1:8000  (UI + API)
Render:  uvicorn src.api:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import ROOT, env
from src.rag.answer import answer_question, meta

app = FastAPI(title="HDFC Fund Facts Assistant API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

origins = [o.strip() for o in env("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"])

# --- tiny in-memory rate limit (protects the free LLM key); nothing is persisted ---
_WINDOW, _MAX = 60, 30
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= _MAX:
        return True
    q.append(now)
    return False


class AskRequest(BaseModel):
    question: str = Field(..., max_length=2000)
    scheme_hint: str | None = Field(None, max_length=40)


@app.get("/api/health")
def health():
    from src.rag.retriever import get_collection

    try:
        count = get_collection().count()
        return {"status": "ok", "chunks": count}
    except Exception as e:  # noqa: BLE001
        return {"status": "degraded", "error": type(e).__name__}


@app.get("/api/meta")
def get_meta():
    return meta()


@app.post("/api/ask")
def ask(req: AskRequest, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0]
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many questions — please wait a minute.")
    return answer_question(req.question, req.scheme_hint)


# --- serve the static UI locally (on Vercel the same folder is served by Vercel) ---
FRONTEND = ROOT / "frontend"
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/{name}", include_in_schema=False)
    def frontend_file(name: str):
        f = FRONTEND / name
        if f.is_file() and f.suffix in {".js", ".css", ".png", ".svg", ".ico", ".html"}:
            return FileResponse(f)
        raise HTTPException(status_code=404)
