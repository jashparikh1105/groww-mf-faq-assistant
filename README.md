# HDFC Fund Facts Assistant — Mutual Fund FAQ (Facts-Only Q&A)

A small **RAG (Retrieval-Augmented Generation)** assistant that answers factual questions about HDFC Mutual Fund
schemes using **only 5 public Groww pages**. Every answer has **one source link** and a
**"Last updated from sources"** date. It refuses investment advice, does not compute returns, and blocks personal data.

> **Facts-only. No investment advice.**

- **Live demo:** `https://<your-project>.vercel.app` *(replace after deploying)*
- **API:** `https://<your-service>.onrender.com/api/health`
- **Product:** Groww · **AMC:** HDFC Mutual Fund

---

## 1. Scope

| # | Page | Category |
|---|------|----------|
| 1 | [HDFC Mutual Fund — AMC overview](https://groww.in/mutual-funds/amc/hdfc-mutual-funds) | AMC |
| 2 | [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) | Large Cap |
| 3 | [HDFC Flexi Cap Direct Plan Growth](https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth) | Flexi Cap |
| 4 | [HDFC ELSS Tax Saver Fund Direct Plan Growth](https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth) | ELSS |
| 5 | [HDFC Mid Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) | Mid Cap |

**Answers:** expense ratio, exit load, minimum SIP / lumpsum, lock-in (ELSS), riskometer, benchmark, fund size,
NAV date, fund manager, launch date, objective, stamp duty, tax notes, AMC details, page FAQs.
**Refuses:** buy/sell/which-is-best questions, return calculations/comparisons, anything with PAN, Aadhaar,
account/folio numbers, OTPs, phone numbers or emails.

---

## 2. How it works

```
OFFLINE (laptop)                                         ONLINE
config.yaml ─► 2 Scrape ─► 3 Load ─► 4 Chunk ─► 5 Embed ─► 6 ChromaDB ──git──► Render (FastAPI RAG API)
             data/raw   data/loaded data/chunks data/embeddings vector_db/            ▲  /api/*
                                                                            Vercel (static UI)
Query: guardrails ─► scheme+fact detection ─► MiniLM query embedding ─► ChromaDB (metadata filter + vector)
       ─► Groq LLM (answer only from context) ─► ≤3 sentences + 1 link + "Last updated from sources"
```

| Stage | Tool | Output kept on disk |
|---|---|---|
| Scraping | `requests` (+ optional Playwright) — only the 5 URLs | `data/raw/*.html`, `manifest.json` |
| Loading | BeautifulSoup; facts from embedded page JSON + regex fallback | `data/loaded/*.json`, `load_report.json` |
| Chunking | Fact cards + FAQ pairs + heading-aware recursive split (800 chars / 120 overlap) | `data/chunks/chunks.json`, `chunk_stats.json` |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` (384-dim, normalized) | `data/embeddings/embeddings.json` |
| Vector DB | ChromaDB (persistent, cosine) | `vector_db/`, `data/vectordb_report.json` |
| LLM | Groq — model from `.env` (`qwen/qwen3.8-27b`, fallback `openai/gpt-oss-20b`) | — |
| UI | HTML/CSS/JS (Groww colours) | `frontend/` |

Full design: [`docs/PRD.md`](docs/PRD.md) · [`docs/architecture.md`](docs/architecture.md) · [`docs/implementation.md`](docs/implementation.md)

**Why this chunking?** Groww pages are mostly short label→value facts. One chunk per fact (with the scheme
name repeated) makes "exit load of HDFC Mid Cap" retrieve exactly that fact instead of a mixed block.

---

## 3. Setup (Windows)

Requirements: **Python 3.11**, Git, a free **Groq API key** (https://console.groq.com/keys).

```powershell
git clone https://github.com/<your-username>/groww-mf-faq-assistant.git
cd groww-mf-faq-assistant
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-ingest.txt
copy .env.example .env      # then open .env and paste your GROQ_API_KEY
```

macOS / Linux: `python3.11 -m venv .venv && source .venv/bin/activate`, `cp .env.example .env`.

## 4. Build the knowledge base (phase by phase)

```powershell
python scripts/setup_dirs.py          # Phase 1  directories
python -m src.phase2_scrape           # Phase 2  scrape the 5 pages
python -m src.phase3_load             # Phase 3  load + extract facts
python -m src.phase4_chunk            # Phase 4  chunk
python -m src.phase5_embed            # Phase 5  embed (MiniLM)
python -m src.phase6_store            # Phase 6  store in ChromaDB
python scripts/verify_vector_db.py    #          are all chunks in the DB?
# or all at once:
python run_pipeline.py
```

## 5. Run

```powershell
python scripts/ask_cli.py "What is the exit load of HDFC Mid Cap Fund?"   # terminal test
uvicorn src.api:app --reload                                             # UI at http://127.0.0.1:8000
python scripts/generate_sample_qa.py                                     # refresh sample Q&A below
pytest -q                                                                # 68 automated tests
```

## 6. Configuration

- `config/config.yaml` — source URLs, chunk size/overlap, embedding model, collection name, `top_k`,
  similarity threshold, max sentences, education links.
- `.env` — `LLM_PROVIDER` (groq | openai | gemini | mistral | anthropic), API keys, `GROQ_MODEL`,
  `GROQ_FALLBACK_MODEL`, `EMBEDDING_BACKEND` (sentence-transformers locally, onnx on the server), `ALLOWED_ORIGINS`.

## 7. Deployment

| Part | Platform | Settings |
|---|---|---|
| API | **Render** (free) | New → Blueprint → this repo (`render.yaml`). Add secret `GROQ_API_KEY`. |
| UI | **Vercel** (Hobby) | Add New → Project → this repo → **Root Directory: `frontend`** → Framework: Other → Deploy. |
| Link them | — | In `frontend/vercel.json` replace `YOUR-RENDER-SERVICE` with your Render service name, commit, push. |

Pushing to `main` redeploys both automatically. The server uses the same MiniLM weights in ONNX form
(`EMBEDDING_BACKEND=onnx`), so it doesn't need PyTorch. `scripts/check_embedding_parity.py` shows both
backends produce the same vectors.

## 8. Guardrails

| Check | Example | Result |
|---|---|---|
| PII (regex, browser + server) | "My PAN is ABCDE1234F" | Blocked, nothing stored or logged |
| Advice | "Should I buy HDFC Mid Cap?" | Polite refusal + SEBI investor-education link |
| Performance | "Compare 5Y returns" | No numbers; link to the official scheme page |
| Missing scheme | "Minimum SIP?" | Asks which scheme |
| Other AMC | "SBI Bluechip expense ratio?" | Out of scope + AMC link |
| Low similarity | "What is the weather?" | "Not found in my sources" |
| Prompt injection | "Ignore previous instructions…" | Refusal |
| Output | every answer | ≤3 sentences, exactly 1 link, "Last updated from sources: …" |

---

## 9. Source list
See [`SOURCES.md`](SOURCES.md) / [`sources.csv`](sources.csv). Knowledge base = the 5 Groww pages above.
Educational links used only in refusals: https://investor.sebi.gov.in/, https://www.mutualfundssahihai.com/en,
https://www.amfiindia.com/online-center/risk-o-meter.

## 10. Sample Q&A
<!-- SAMPLE_QA_START -->
#### 1. What is the expense ratio of HDFC Mid Cap Fund?
**Type:** `answer`  
**Answer:** The expense ratio of HDFC Mid Cap Fund Direct Growth is 0.74%.  
**Source:** https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth  
**Last updated from sources:** 08 Nov 2026

#### 2. What is the lock-in period of HDFC ELSS Tax Saver Fund?
**Type:** `answer`  
**Answer:** The lock-in period for HDFC ELSS Tax Saver Fund is 3 years. This is a statutory requirement for ELSS tax-saver schemes.  
**Source:** https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth  
**Last updated from sources:** 08 Nov 2026

#### 3. What is the exit load of HDFC Flexi Cap Fund?
**Type:** `answer`  
**Answer:** HDFC Flexi Cap Fund Direct Plan Growth has an exit load of 1% if redeemed within 1 year.  
**Source:** https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth  
**Last updated from sources:** 08 Nov 2026

#### 4. What is the minimum SIP amount for HDFC Large Cap Fund?
**Type:** `answer`  
**Answer:** The HDFC Large Cap Fund Direct Growth scheme has a minimum SIP amount of ₹100.  
**Source:** https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth  
**Last updated from sources:** 08 Nov 2026

#### 5. What is the riskometer level of HDFC Mid Cap Fund?
**Type:** `answer`  
**Answer:** HDFC Mid Cap Fund Direct Growth has a riskometer level of Moderately High risk.  
**Source:** https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth  
**Last updated from sources:** 08 Nov 2026

#### 6. What is the benchmark of HDFC Large Cap Fund?
**Type:** `answer`  
**Answer:** The benchmark for HDFC Large Cap Fund Direct Growth is the NIFTY 100 Total Return Index.  
**Source:** https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth  
**Last updated from sources:** 08 Nov 2026

#### 7. Who manages HDFC ELSS Tax Saver Fund?
**Type:** `answer`  
**Answer:** HDFC ELSS Tax Saver Fund is managed by Vinay Kulkarni.  
**Source:** https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth  
**Last updated from sources:** 08 Nov 2026

#### 8. How do I download my capital gains statement?
**Type:** `not_found`  
**Answer:** I couldn't find that in my sources (5 public Groww pages on HDFC Mutual Fund). Please check the official page linked below.  
**Source:** https://groww.in/mutual-funds/amc/hdfc-mutual-funds  
**Last updated from sources:** 08 Nov 2026

#### 9. Should I buy HDFC Flexi Cap Fund now?
**Type:** `refusal`  
**Answer:** I can only share facts, so I can't say whether to buy, sell, hold or choose a fund. For a personal recommendation please speak to a SEBI-registered investment adviser; SEBI's investor site explains how to evaluate funds.  
**Learn more:** https://investor.sebi.gov.in/  
**Last updated from sources:** 08 Nov 2026

#### 10. My PAN is ABCDE1234F, can you check my holdings?
**Type:** `pii_blocked`  
**Answer:** Please don't share personal details such as a PAN; I don't need them and nothing you type is stored. Ask me a factual question about an HDFC scheme instead.  
**Learn more:** https://www.mutualfundssahihai.com/en  
**Last updated from sources:** 08 Nov 2026

<!-- SAMPLE_QA_END -->

## 11. Disclaimer (used in the UI)
> Facts-only. No investment advice. Information is taken from public pages and may change; always verify on the
> linked source and read all scheme-related documents carefully. Mutual fund investments are subject to market risks.
> Independent learning project, not affiliated with Groww or HDFC Asset Management Company.

## 12. Known limits
- Knowledge is limited to 5 Groww pages; questions outside them (e.g. step-by-step capital-gains statement
  download, if it isn't on these pages) return "not found" with a link.
- Facts are a snapshot from the scrape date shown in each answer; re-run the pipeline to refresh.
- Groww may change its page layout; the loader reads both embedded JSON and visible text, but extraction should
  be checked in `data/loaded/load_report.json` after every scrape.
- The Groq model `qwen/qwen3.8-27b` is a preview model; if it's retired, the app switches to `GROQ_FALLBACK_MODEL`.
- Render's free tier sleeps after 15 minutes idle, so the first answer can take about a minute.
- One scheme per question; for comparisons the assistant asks you to pick one.
- Regex PII detection can miss unusual formats; inputs are never stored either way.

## 13. Project structure
```
config/config.yaml        src/phase2_scrape.py … phase6_store.py     src/rag/{guardrails,retriever,llm,answer}.py
src/api.py                frontend/{index.html,styles.css,app.js,config.js,vercel.json}
data/{raw,loaded,chunks,embeddings}/   vector_db/   scripts/   tests/   docs/   render.yaml
```
