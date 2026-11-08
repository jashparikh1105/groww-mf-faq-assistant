# PRD — HDFC Fund Facts Assistant (Groww MF FAQ, Facts-Only)

*Derived from `ProblemStatement.txt`*

## 1. Summary
A small RAG chatbot that answers factual questions about 4 HDFC Mutual Fund schemes and the
HDFC AMC, using only 5 public Groww pages. Every answer is short (≤3 sentences), carries one
source link and a "Last updated from sources" date. It refuses advice, return comparisons
and any input that contains personal data.

## 2. Users & jobs-to-be-done
| User | Job | Example |
|---|---|---|
| Retail investor comparing schemes | Get one fact quickly, with proof | "Exit load of HDFC Mid Cap?" |
| Groww support agent | Paste a verified answer + link into a ticket | "Minimum SIP for HDFC ELSS?" |
| Content team | Check scheme facts before publishing | "Benchmark of HDFC Flexi Cap?" |

## 3. Scope
**In scope (corpus = 5 URLs):** HDFC Mutual Fund AMC page; HDFC Large Cap, HDFC Flexi Cap,
HDFC ELSS Tax Saver, HDFC Mid Cap (all Direct Plan – Growth).

**Supported fact types:** expense ratio, exit load, min SIP, min lumpsum, lock-in, riskometer
(risk level), benchmark, fund size (AUM), NAV + NAV date, fund manager(s), launch date,
category, investment objective, stamp duty, tax implication, AMC details, FAQs present on the
pages.

**Out of scope:** other AMCs/schemes, returns/performance computation, advice, account
actions, anything needing login, internal links of the pages.

## 4. User stories & acceptance criteria
| ID | Story | Acceptance criteria |
|---|---|---|
| US1 | As an investor I ask "Expense ratio of HDFC Mid Cap?" | Answer contains the value from the page, the HDFC Mid Cap Groww URL, ≤3 sentences, last-updated date |
| US2 | I ask "ELSS lock-in?" | Answer states the lock-in found on the ELSS page + ELSS URL |
| US3 | I ask "Should I buy HDFC Flexi Cap?" | Polite refusal, no opinion, one educational link (AMFI/SEBI) |
| US4 | I type my PAN / phone / email | Request is blocked before retrieval; nothing is stored or logged |
| US5 | I ask "Which gave better returns, Large Cap or Mid Cap?" | No numbers computed; points to the official scheme page |
| US6 | I ask "Expense ratio?" without naming a scheme | Assistant asks which of the 4 schemes I mean |
| US7 | I ask about a scheme outside the corpus | Says it only covers the 5 sources, links the AMC page |
| US8 | I open the app | See welcome line, 3 clickable example questions, "Facts-only. No investment advice." |

## 5. Functional requirements
1. **Ingestion pipeline** (offline, run locally): scrape → load → chunk → embed → store, each
   stage writing its output to `data/` or `vector_db/`.
2. **Query pipeline** (online): guardrails → scheme & fact detection → retrieval (ChromaDB)
   → LLM answer from context → post-processing (≤3 sentences, 1 link, date).
3. **Guardrails:** PII detector, advice/opinion classifier, performance/returns detector,
   out-of-scope detector, missing-scheme clarifier, low-similarity "not found" path.
4. **LLM-optional mode:** if no API key is set or the LLM fails, return an extractive answer
   from the best-matching fact chunk (so the demo never breaks).
5. **Config-driven:** URLs, chunk sizes, model names, top-k, thresholds in `config/config.yaml`;
   secrets and model choice in `.env`.

## 6. Non-functional requirements
| Area | Requirement |
|---|---|
| Accuracy | Facts come only from retrieved chunks; temperature 0 |
| Latency | < 3 s per answer when the server is warm |
| Privacy | Queries never written to disk; PII rejected with regex before any processing |
| Cost | Free tiers only (Groq free key, Render free, Vercel Hobby) |
| Transparency | Source link + "Last updated from sources: <scrape date>" on every answer |
| Portability | Runs on Windows/macOS/Linux with Python 3.11 |

## 7. Answer format (contract)
```
<answer, max 3 sentences>
Source: <one URL>
Last updated from sources: <DD Mon YYYY>
```
Refusal format:
```
<polite one-line refusal + what I can do>
Learn more: <educational URL>
```

## 8. Success metrics
- ≥ 90% correct fact + correct URL on the sample question set.
- 100% refusal on advice and PII test cases (automated tests).
- 0 answers above 3 sentences (enforced in code).

## 9. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Groww changes page layout | Loader reads both embedded JSON (`__NEXT_DATA__`) and visible text; regex fallbacks |
| Groww blocks scraping | Browser-like headers + optional Playwright fallback; raw HTML is cached in `data/raw/` |
| Preview LLM model is withdrawn | Automatic fallback model in `.env` (`openai/gpt-oss-20b`) |
| Free host sleeps (cold start) | UI shows "waking up server" message; documented in README |
| Fact not in 5 pages (e.g., capital-gains statement steps) | "Not found in my sources" + AMC link; listed in Known limits |

## 10. Release plan
Phase 1–6 ingestion → Phase 7 retrieval/API → Phase 8 UI → tests → GitHub → Render (API)
+ Vercel (UI).
