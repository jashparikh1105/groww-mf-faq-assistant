# Architecture — HDFC Fund Facts Assistant

*Derived from `PRD.md`. This file plus `implementation.md` are the main source of truth.*

## 1. High-level view

```
                OFFLINE (run on your laptop)                                ONLINE (deployed)
┌──────────────────────────────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ config/config.yaml                                           │   │  Browser                              │
│     │                                                        │   │   │  (Vercel static UI: frontend/)    │
│ Phase 2  scrape   ─► data/raw/*.html + manifest.json         │   │   ▼  POST /api/ask {question}         │
│ Phase 3  load     ─► data/loaded/*.json  (facts+sections+FAQ)│   │  Vercel rewrite  /api/* ─────────┐    │
│ Phase 4  chunk    ─► data/chunks/chunks.json                 │   └──────────────────────────────────│───┘
│ Phase 5  embed    ─► data/embeddings/embeddings.json         │                                      ▼
│          (sentence-transformers/all-MiniLM-L6-v2, 384-dim)   │   ┌──────────────────────────────────────┐
│ Phase 6  store    ─► vector_db/  (ChromaDB, cosine)          │   │ Render: FastAPI  (src/api.py)        │
└───────────────────────────┬──────────────────────────────────┘   │  1 Guardrails (PII/advice/returns)   │
                            │ git push (vector_db/ is committed)    │  2 Scheme + fact detection           │
                            └──────────────────────────────────────►│  3 Embed query (same MiniLM, ONNX)   │
                                                                    │  4 ChromaDB query (+metadata filter) │
                                                                    │  5 LLM (Groq) answers from context   │
                                                                    │  6 Post-process: ≤3 sent, 1 link,    │
                                                                    │    "Last updated from sources"       │
                                                                    └──────────────────────────────────────┘
```

## 2. Components

| # | Component | File | Responsibility | Output stored |
|---|---|---|---|---|
| 0 | Config | `config/config.yaml`, `.env`, `src/config.py` | Single place for URLs, models, sizes, thresholds, keys | — |
| 1 | Directory setup | `scripts/setup_dirs.py` | Create `data/*`, `vector_db/` | folders |
| 2 | Scraper | `src/phase2_scrape.py` | GET the 5 URLs only (no crawling), save raw HTML | `data/raw/<slug>.html`, `manifest.json` |
| 3 | Loader | `src/phase3_load.py` | Parse HTML → clean document: structured facts (from `__NEXT_DATA__` JSON + regex on text), sections, FAQs | `data/loaded/<slug>.json` |
| 4 | Chunker | `src/phase4_chunk.py` | Data-aware chunking (see §4) | `data/chunks/chunks.json`, `chunk_stats.json` |
| 5 | Embedder | `src/phase5_embed.py`, `src/embeddings.py` | Encode chunks with all-MiniLM-L6-v2 (normalized) | `data/embeddings/embeddings.json` |
| 6 | Vector store | `src/phase6_store.py` | Upsert into ChromaDB collection `hdfc_mf_faq` (cosine) and verify count | `vector_db/`, `data/vectordb_report.json` |
| 7 | Retrieval/RAG | `src/rag/guardrails.py`, `retriever.py`, `llm.py`, `answer.py` | Guardrails → retrieve → generate → format | — (no query logging) |
| 8 | API | `src/api.py` | FastAPI: `GET /api/health`, `GET /api/meta`, `POST /api/ask`; also serves the UI locally | — |
| 9 | UI | `frontend/index.html`, `styles.css`, `app.js` | Groww-coloured chat UI, examples, disclaimer | — |

## 3. Data model

**Loaded document** (`data/loaded/<slug>.json`)
```json
{
  "doc_id": "hdfc-mid-cap", "url": "...", "page_type": "scheme|amc",
  "scheme_name": "HDFC Mid Cap Fund Direct Growth", "category": "Mid Cap",
  "scraped_at": "2026-11-08", "title": "...",
  "facts": {"expense_ratio": "0.74%", "exit_load": "...", "min_sip": "₹100", ...},
  "sections": [{"heading": "Exit load, stamp duty and tax", "text": "..."}],
  "faqs": [{"q": "...", "a": "..."}]
}
```

**Chunk** (`data/chunks/chunks.json`)
```json
{"id": "hdfc-mid-cap::fact::expense_ratio", "text": "HDFC Mid Cap Fund Direct Growth — Expense ratio: 0.74% ...",
 "metadata": {"doc_id": "hdfc-mid-cap", "scheme": "hdfc-mid-cap", "chunk_type": "fact|section|faq",
              "fact_type": "expense_ratio", "section": "...", "source_url": "...", "scraped_at": "2026-11-08"}}
```

## 4. Chunking strategy (decided from the data)
Groww scheme pages are mostly **short label → value facts** plus a few prose sections and an
FAQ block. One fixed-size splitter would mix many facts in one chunk and blur retrieval, so
three chunk types are used:

1. **Fact cards** — one chunk per extracted field, written as a full sentence that repeats the
   scheme name ("HDFC Mid Cap Fund Direct Growth — Exit load: 1% if redeemed within 1 year.").
   Tagged with `fact_type` so retrieval can filter exactly.
2. **FAQ chunks** — one chunk per Q&A pair (question + answer kept together).
3. **Section chunks** — remaining prose split on headings, then recursively to ≤ 800 chars
   with 120-char overlap; each chunk is prefixed with `"<scheme> | <section>:"` (contextual
   header) so it is self-describing.

Sizes and overlap live in `config.yaml → chunking`.

## 5. Query flow (Phase 7)
1. **Normalize** input (trim, max 500 chars).
2. **PII guard** (regex): PAN, Aadhaar, phone, email, OTP, account/folio numbers → refuse, nothing stored.
3. **Advice guard**: "should I", "buy/sell", "best", "recommend", "worth", "portfolio" … → polite refusal + AMFI/SEBI link.
4. **Performance guard**: "returns", "CAGR", "performance", "beat", "how much will I earn" → no numbers, link to scheme page.
5. **Scheme detection**: alias table (e.g. "elss", "tax saver" → `hdfc-elss`; "flexi", "equity fund" → `hdfc-flexi-cap`).
6. **Fact detection**: keyword table → `fact_type` (expense_ratio, exit_load, min_sip, lock_in, risk, benchmark …).
7. **Clarify**: if a scheme-specific fact is asked without a scheme → ask which scheme.
8. **Retrieve**: embed query → ChromaDB `query(top_k=5, where={scheme})`; if a fact card with the
   exact `fact_type` exists it is pinned to position 1 (hybrid: metadata + vector).
9. **Threshold**: if best cosine distance > `max_distance` → "not found in my sources" + AMC link.
10. **Generate**: Groq chat completion, temperature 0, system prompt enforcing facts-only,
    ≤3 sentences, answer only from numbered context, end with `SOURCE: [n]`.
11. **Post-process**: strip `<think>` blocks, cut to 3 sentences, attach the URL of chunk `[n]`
    (fallback: top chunk), append "Last updated from sources: <scraped_at>".
12. **Fallback**: no key / LLM error → extractive answer from the top chunk.

## 6. Embedding consistency (local vs cloud)
- Ingestion (laptop): `sentence-transformers` library, model `sentence-transformers/all-MiniLM-L6-v2`, normalized vectors.
- Query on Render: the same all-MiniLM-L6-v2 weights exported to ONNX (Chroma's built-in
  `ONNXMiniLM_L6_V2`: mean pooling + L2 normalization, same as sentence-transformers). This avoids
  installing PyTorch (~700 MB) on a 512 MB free server. `scripts/check_embedding_parity.py`
  proves both give the same vectors (cosine ≈ 1.0).
- Switch with `EMBEDDING_BACKEND=sentence-transformers|onnx` in `.env`.

## 7. LLM layer
`src/rag/llm.py` speaks the OpenAI-compatible Chat Completions format, so one client covers:
| Provider | Base URL | Env key |
|---|---|---|
| Groq (default) | `https://api.groq.com/openai/v1` | `GROQ_API_KEY`, `GROQ_MODEL` |
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` |
| Mistral | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` |
| Anthropic | native Messages API | `ANTHROPIC_API_KEY` |

Select with `LLM_PROVIDER` in `.env`. Groq default model `qwen/qwen3.8-27b` (preview) with
automatic fallback to `GROQ_FALLBACK_MODEL` (`openai/gpt-oss-20b`, production).

## 8. Deployment

| Piece | Host | Notes |
|---|---|---|
| UI (`frontend/`) | **Vercel** (Hobby, free) | Root directory `frontend`; `vercel.json` rewrites `/api/*` to the Render URL, so no CORS issues |
| API (`src/api.py`) | **Render** free web service | `render.yaml`; build installs `requirements.txt` and pre-downloads the ONNX model; vector DB comes from git |
| Code | GitHub | `.env` is git-ignored; `.env.example` is committed |

Free Render services sleep after 15 min idle; the first request takes ~1 min. The UI shows a
"waking up" note while it waits.

## 9. UI (Stitch-compatible)
Groww palette: primary green `#00D09C`, dark green `#00B386`, navy text `#44475B`,
heading `#121212`, background `#FFFFFF` / `#F8F8F8`, border `#E9E9EB`, error `#EB5B3C`.
Layout: header (logo mark + "HDFC Fund Facts Assistant"), disclaimer pill, welcome card,
3 example chips, chat thread (answer bubble with **Source** link + "Last updated" line),
input box with PII warning, footer listing the 5 sources. If a Stitch with Google export
(`stitch_hdfc_fund_facts_assistant.zip`) is used, its HTML/CSS replaces `frontend/index.html`
+ `styles.css` and must keep the element IDs used by `app.js` (`#chat`, `#question`,
`#send`, `.example`).

## 10. Security & privacy
- PII rejected before any processing; FastAPI does not log request bodies.
- No database of user queries; no cookies; no analytics.
- API keys only in environment variables (Render dashboard / local `.env`).
- CORS restricted with `ALLOWED_ORIGINS`.
