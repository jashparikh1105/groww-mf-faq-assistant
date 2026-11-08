"""Answer pipeline: guardrails -> retrieval -> LLM -> post-processing.

Every response has: answer (<=3 sentences), exactly one source_url, last_updated.
Questions are never written to disk or logs.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache

from src.config import get_config, path, source_by_id, sources
from src.rag import llm
from src.rag.guardrails import AMC_FACT_MAP, SCHEME_DISPLAY, SCHEME_SPECIFIC, classify
from src.rag.retriever import Hit, is_confident, retrieve

AMC_URL = source_by_id("hdfc-amc")["url"]

SYSTEM_PROMPT = """You are "HDFC Fund Facts Assistant", a facts-only helper for Groww users.
Answer the QUESTION using ONLY the numbered CONTEXT passages.
Rules:
1. State facts only. Never give advice, opinions, recommendations or predictions.
2. Never state, calculate or compare returns or performance.
3. Use at most 3 short sentences. Quote numbers exactly as written in the context.
4. Mention the scheme name in your answer.
5. If the CONTEXT does not contain the answer, reply with exactly: NOT_FOUND
6. Do not write any URL.
7. On the last line write: SOURCE: [n]  (n = the number of the passage you used)."""


# ------------------------------------------------------------------ helpers
@lru_cache(maxsize=1)
def corpus_date() -> str:
    """Latest scrape date from data/raw/manifest.json, formatted like 08 Nov 2026."""
    try:
        manifest = json.loads((path("raw_dir") / "manifest.json").read_text(encoding="utf-8"))
        iso = max(m["scraped_at"] for m in manifest if m.get("ok"))
        return format_date(iso[:10])
    except Exception:  # noqa: BLE001
        return datetime.now().strftime("%d %b %Y")


def format_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return iso_date


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z₹(\"'])")


def limit_sentences(text: str, n: int | None = None) -> str:
    n = n or get_config()["answer"]["max_sentences"]
    text = re.sub(r"https?://\S+", "", text)          # links are shown separately
    text = re.sub(r"\s+", " ", text).strip()
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p.strip()]
    out = " ".join(parts[:n])
    if out and out[-1] not in ".!?":
        out += "."
    return out


def build(kind: str, answer: str, url: str, scheme: str | None = None, model: str | None = None,
          last_updated: str | None = None) -> dict:
    answer = limit_sentences(answer)
    last = last_updated or corpus_date()
    label = "Learn more" if kind in ("refusal", "pii_blocked") else "Source"
    return {
        "type": kind,
        "answer": answer,
        "source_url": url,
        "last_updated": last,
        "scheme": scheme,
        "model": model,
        "text": f"{answer}\n{label}: {url}\nLast updated from sources: {last}",
    }


def scheme_url(scheme: str | None) -> str:
    s = source_by_id(scheme) if scheme else None
    return s["url"] if s else AMC_URL


def _extractive(hit: Hit) -> str:
    """Answer without an LLM: use the fact card / chunk text itself."""
    text = hit.text
    if "|" in text.split("\n", 1)[0]:          # drop the "<scheme> | <section>:" prefix
        text = text.split("\n", 1)[-1]
    text = text.replace("\nQ:", " Q:").replace("\nA:", " A:")
    return limit_sentences(text, 2)


def _context_block(hits: list[Hit]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        m = h.metadata
        lines.append(f"[{i}] ({m.get('scheme_name')} | {m.get('section') or m.get('chunk_type')})\n{h.text}")
    return "\n\n".join(lines)


# ------------------------------------------------------------------ main entry
def answer_question(question: str, scheme_hint: str | None = None) -> dict:
    cfg = get_config()
    edu = cfg["education_links"]
    question = (question or "")[: cfg["answer"]["max_question_chars"]]
    intent = classify(question)

    if intent.kind == "empty":
        return build("clarify", "Please type a factual question, for example: What is the exit load of HDFC Mid Cap Fund?", AMC_URL)
    if intent.kind == "pii":
        return build(
            "pii_blocked",
            f"Please don't share personal details such as a {intent.detail}; I don't need them and nothing you type is stored. "
            "Ask me a factual question about an HDFC scheme instead.",
            edu["general"],
        )
    if intent.kind == "injection":
        return build("refusal", "I can only answer factual questions about the HDFC Mutual Fund schemes in my sources.", edu["general"])
    if intent.kind == "advice":
        return build(
            "refusal",
            "I can only share facts, so I can't say whether to buy, sell, hold or choose a fund. "
            "For a personal recommendation please speak to a SEBI-registered investment adviser; SEBI's investor site explains how to evaluate funds.",
            edu["advice"],
        )
    if intent.kind == "performance":
        sch = (intent.schemes or [None])[0]
        return build(
            "refusal",
            "I don't calculate or compare returns. Please see the official, up-to-date performance figures on the scheme page linked below.",
            scheme_url(sch), scheme=sch,
        )
    if intent.kind == "other_amc":
        return build(
            "not_found",
            "I only cover HDFC Mutual Fund and four of its schemes (Large Cap, Flexi Cap, ELSS Tax Saver and Mid Cap) from Groww's public pages.",
            AMC_URL,
        )
    if intent.kind == "greeting":
        return build(
            "greeting",
            "Hi! Ask me a factual question about HDFC Large Cap, Flexi Cap, ELSS Tax Saver or Mid Cap funds, such as expense ratio, exit load, minimum SIP, lock-in, riskometer or benchmark.",
            AMC_URL,
        )

    schemes = intent.schemes or ([scheme_hint] if scheme_hint and source_by_id(scheme_hint) else [])
    fact = intent.fact

    if len(schemes) > 1:
        names = ", ".join(SCHEME_DISPLAY[s] for s in schemes)
        return build("clarify", f"I answer one scheme at a time. Which one do you mean: {names}?", AMC_URL)

    scheme = schemes[0] if schemes else None
    if scheme == "hdfc-amc" and fact in AMC_FACT_MAP:
        fact = AMC_FACT_MAP[fact]
    if scheme is None and fact in SCHEME_SPECIFIC:
        return build(
            "clarify",
            "Which scheme do you mean: HDFC Large Cap, HDFC Flexi Cap, HDFC ELSS Tax Saver or HDFC Mid Cap Fund?",
            AMC_URL,
        )

    try:
        hits = retrieve(question, scheme=scheme, fact=fact)
    except Exception as e:  # noqa: BLE001 - vector DB missing etc.
        return build("error", f"The knowledge base is not ready ({type(e).__name__}). Please run the ingestion pipeline.", AMC_URL)

    if not is_confident(hits):
        return build(
            "not_found",
            "I couldn't find that in my sources (5 public Groww pages on HDFC Mutual Fund). Please check the official page linked below.",
            scheme_url(scheme), scheme=scheme,
        )

    ctx_hits = hits[: cfg["retrieval"]["context_chunks_for_llm"]]
    chosen = ctx_hits[0]
    model_used = None
    try:
        raw, model_used = llm.generate(SYSTEM_PROMPT, f"QUESTION: {question}\n\nCONTEXT:\n{_context_block(ctx_hits)}")
        m = re.search(r"SOURCE:\s*\[?(\d+)\]?", raw, re.I)
        if m and 1 <= int(m.group(1)) <= len(ctx_hits):
            chosen = ctx_hits[int(m.group(1)) - 1]
        body = re.sub(r"SOURCE:.*$", "", raw, flags=re.I | re.S).strip()
        if not body or "NOT_FOUND" in body.upper():
            if chosen.pinned:                       # we do have the exact fact card
                body = _extractive(chosen)
            else:
                return build(
                    "not_found",
                    "I couldn't find that in my sources (5 public Groww pages on HDFC Mutual Fund). Please check the official page linked below.",
                    scheme_url(scheme), scheme=scheme, model=model_used,
                )
    except llm.LLMUnavailable:
        body = _extractive(chosen)
        model_used = "extractive (no LLM)"

    return build(
        "answer", body, chosen.metadata["source_url"], scheme=chosen.metadata.get("scheme"),
        model=model_used, last_updated=format_date(chosen.metadata.get("scraped_at", "")),
    )


def meta() -> dict:
    return {
        "title": get_config()["project"]["name"],
        "disclaimer": "Facts-only. No investment advice.",
        "welcome": "Hi! I answer factual questions about 4 HDFC Mutual Fund schemes using Groww's public pages.",
        "examples": [
            "What is the expense ratio of HDFC Mid Cap Fund?",
            "What is the lock-in period of HDFC ELSS Tax Saver?",
            "What is the exit load of HDFC Flexi Cap Fund?",
        ],
        "sources": [{"label": s["label"], "url": s["url"]} for s in sources()],
        "last_updated": corpus_date(),
        "llm": {"provider": llm.provider(), "model": llm.model_name(), "configured": llm.is_configured()},
    }
