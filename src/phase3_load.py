"""Phase 3 — Load raw HTML into clean, structured documents.

Run:  python -m src.phase3_load
Out:  data/loaded/<doc_id>.json  +  data/loaded/load_report.json

Each document has:
  facts    -> key facts (expense ratio, exit load, min SIP, lock-in, risk, benchmark, ...)
              read from Groww's embedded JSON (__NEXT_DATA__) with regex fallback on visible text
  sections -> visible text split by headings
  faqs     -> question/answer pairs (JSON-LD FAQPage, embedded JSON, or FAQ section)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from src.config import path, sources

# ----------------------------------------------------------------------------------------
# Fact definitions: label shown to users, candidate JSON keys, regex fallbacks on page text
# ----------------------------------------------------------------------------------------
RISK_LEVELS = r"(Very High|Moderately High|Moderate|Low to Moderate|Moderately Low|High|Low)"

SCHEME_FACTS: dict[str, dict[str, Any]] = {
    "expense_ratio": {
        "label": "Expense ratio",
        "keys": ["expense_ratio", "expenseRatio", "ter", "total_expense_ratio"],
        "regex": [r"Expense ratio\s*[:\-]?\s*([0-9]{1,2}\.[0-9]{1,3}\s?%)"],
    },
    "exit_load": {
        "label": "Exit load",
        "keys": ["exit_load", "exitLoad"],
        "regex": [
            r"(Exit load of [^\n;]{3,200})",
            r"Exit load\s*[:\-]?\s*\n?\s*(Nil|NIL|[0-9][^\n]{2,200})",
        ],
    },
    "min_sip": {
        "label": "Minimum SIP amount",
        "keys": ["min_sip_investment", "minSipInvestment", "min_sip_amount", "min_sip"],
        "regex": [
            r"Minimum SIP Investment is set to\s*(₹\s?[\d,]+)",
            r"Min\.?\s*(?:for\s*)?SIP(?:\s*amount)?\s*[:\-]?\s*(₹\s?[\d,]+)",
        ],
    },
    "min_lumpsum": {
        "label": "Minimum lumpsum (one-time) amount",
        "keys": ["min_investment_amount", "minInvestmentAmount", "min_lumpsum", "min_lumpsum_investment"],
        "regex": [
            r"Minimum Lumpsum Investment is\s*(₹\s?[\d,]+)",
            r"Min\.?\s*(?:for\s*)?(?:1st\s*)?(?:investment|lumpsum|one[- ]time)(?:\s*amount)?\s*[:\-]?\s*(₹\s?[\d,]+)",
        ],
    },
    "lock_in": {
        "label": "Lock-in period",
        "keys": ["lock_in", "lockIn", "lock_in_period", "lockin_period"],
        "regex": [
            r"lock[- ]in period of\s*(\d+\s*(?:years?|yrs?))",
            r"Lock[- ]in(?:\s*period)?\s*[:\-]?\s*\n?\s*(\d+\s*(?:Y|years?|yrs?)|Nil|No lock[- ]in|N/?A)",
        ],
    },
    "risk": {
        "label": "Riskometer (risk level)",
        "keys": ["nfo_risk", "risk", "risk_rating", "riskometer", "risk_level"],
        "regex": [
            r"rated\s+" + RISK_LEVELS + r"\s+risk",
            r"\b" + RISK_LEVELS + r"\s+Risk\b",
        ],
    },
    "benchmark": {
        "label": "Benchmark",
        "keys": ["benchmark_name", "benchmark", "benchmarkName", "fund_benchmark"],
        "regex": [
            r"(?:Fund\s+)?[Bb]enchmark\s*[:\-]?\s*\n?\s*((?:NIFTY|Nifty|S&P BSE|BSE)[^\n]{2,90})",
        ],
    },
    "aum": {
        "label": "Fund size (AUM)",
        "keys": ["aum", "fund_size", "fundSize", "aum_in_cr"],
        "regex": [r"Fund size(?:\s*\(AUM\))?\s*[:\-]?\s*\n?\s*(₹\s?[\d,\.]+\s?Cr)"],
    },
    "nav": {
        "label": "NAV",
        "keys": ["nav", "latest_nav", "current_nav"],
        "regex": [r"NAV\s*[:\-]?\s*\d{1,2}\s\w{3}\s'?\d{2,4}\s*\n?\s*(₹\s?[\d,\.]+)"],
    },
    "nav_date": {
        "label": "NAV date",
        "keys": ["nav_date", "navDate", "latest_nav_date"],
        "regex": [r"NAV\s*[:\-]?\s*(\d{1,2}\s\w{3}\s'?\d{2,4})"],
    },
    "launch_date": {
        "label": "Launch date",
        "keys": ["launch_date", "launchDate", "inception_date", "start_date"],
        "regex": [r"(?:Launch|Inception) date\s*[:\-]?\s*\n?\s*(\d{1,2}[\s\-]\w{3}[\s\-]\d{2,4})"],
    },
    "category": {
        "label": "Category",
        "keys": ["sub_category", "subCategory", "category"],
        "regex": [],
    },
    "fund_manager": {
        "label": "Fund manager(s)",
        "keys": ["fund_manager", "fundManager", "fund_manager_details", "fund_managers"],
        "regex": [r"Fund manager(?:s)?\s*[:\-]?\s*\n?\s*([A-Z][A-Za-z\.]+(?:\s[A-Z][A-Za-z\.]+){1,3})"],
    },
    "objective": {
        "label": "Investment objective",
        "keys": ["investment_objective", "description", "objective"],
        "regex": [r"Investment Objective\s*\n?\s*([^\n]{40,600})"],
    },
    "stamp_duty": {
        "label": "Stamp duty",
        "keys": ["stamp_duty", "stampDuty"],
        "regex": [r"Stamp duty\s*[:\-]?\s*\n?\s*([0-9.]+\s?%[^\n]{0,40})"],
    },
    "tax": {
        "label": "Tax implication",
        "keys": ["tax_impact", "tax_implication"],
        "regex": [r"Tax implication\s*\n?\s*([^\n]{30,500})"],
    },
    "fund_house": {
        "label": "Fund house",
        "keys": ["fund_house", "amc", "amc_name", "fundHouse"],
        "regex": [],
    },
    "isin": {
        "label": "ISIN",
        "keys": ["isin", "isin_code"],
        "regex": [r"\b(INF[0-9A-Z]{9})\b"],
    },
}

AMC_FACTS: dict[str, dict[str, Any]] = {
    "amc_aum": {
        "label": "Total AUM of the fund house",
        "keys": ["aum", "total_aum", "amc_aum"],
        "regex": [r"(?:Total\s+)?AUM\s*[:\-]?\s*\n?\s*(₹\s?[\d,\.]+\s?(?:Cr|Lakh Cr|L Cr))"],
    },
    "amc_launch_date": {
        "label": "Fund house launch / incorporation date",
        "keys": ["launch_date", "date_of_incorporation", "incorporation_date", "setup_date"],
        "regex": [r"(?:Date of Incorporation|Launch date|Incorporated on)\s*[:\-]?\s*\n?\s*([^\n]{6,30})"],
    },
    "amc_schemes": {
        "label": "Number of schemes",
        "keys": ["total_schemes", "no_of_schemes", "schemes_count", "fund_count"],
        "regex": [r"(?:No\.? of|Number of|Total)\s+schemes\s*[:\-]?\s*\n?\s*(\d{1,4})"],
    },
    "amc_ceo": {
        "label": "Managing Director / CEO",
        "keys": ["ceo", "ceo_name", "managing_director"],
        "regex": [r"(?:CEO|Managing Director)\s*[:\-]?\s*\n?\s*([A-Z][A-Za-z\.]+(?:\s[A-Z][A-Za-z\.]+){1,3})"],
    },
    "amc_cio": {
        "label": "Chief Investment Officer",
        "keys": ["cio", "cio_name"],
        "regex": [r"(?:CIO|Chief Investment Officer)\s*[:\-]?\s*\n?\s*([A-Z][A-Za-z\.]+(?:\s[A-Z][A-Za-z\.]+){1,3})"],
    },
    "amc_website": {
        "label": "Official website",
        "keys": ["website", "amc_website", "web_url"],
        "regex": [r"(https?://(?:www\.)?hdfcfund\.com[^\s\"']*)"],
    },
    "amc_address": {
        "label": "Registered address",
        "keys": ["address", "registered_address"],
        "regex": [r"Address\s*[:\-]?\s*\n?\s*([^\n]{20,250})"],
    },
}

NOISE_LINES = {
    "login", "sign up", "invest now", "explore", "search", "1m", "3m", "6m", "1y", "3y", "5y",
    "all", "monthly sip", "one-time", "see all", "show more", "read more", "download app",
    "add to watchlist", "share", "compare", "groww", "",
}

# ----------------------------------------------------------------------------------------
# JSON helpers
# ----------------------------------------------------------------------------------------

def _iter_dicts(obj: Any, depth: int = 0):
    """Yield (dict, depth) for every dict nested anywhere in obj."""
    if isinstance(obj, dict):
        yield obj, depth
        for v in obj.values():
            yield from _iter_dicts(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_dicts(v, depth + 1)


def _name_tokens(name: str) -> set[str]:
    stop = {"fund", "direct", "plan", "growth", "the", "mutual", "funds", "option", "-", "(amc)"}
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t and t not in stop}


def find_main_dict(data: Any, fact_defs: dict, scheme_name: str) -> dict | None:
    """Pick the dict that best describes THIS page (not 'similar funds' lists).

    Score = number of known fact keys present + bonus when its name matches the scheme,
    tie-break by shallower depth.
    """
    wanted = {k for d in fact_defs.values() for k in d["keys"]}
    target = _name_tokens(scheme_name)
    best, best_score = None, (0, 0, 0)
    for d, depth in _iter_dicts(data):
        hits = sum(1 for k in d if k in wanted and d[k] not in (None, "", [], {}))
        if hits < 2:
            continue
        name = str(d.get("scheme_name") or d.get("fund_name") or d.get("name") or d.get("amc_name") or "")
        name_bonus = len(target & _name_tokens(name)) if name else 0
        score = (hits + 3 * name_bonus, name_bonus, -depth)
        if score > best_score:
            best, best_score = d, score
    return best


def _format_value(fact: str, value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, dict):
        if fact == "lock_in":
            parts = [f"{value[k]} {k}" for k in ("years", "months", "days") if value.get(k)]
            return " ".join(parts) if parts else "No lock-in"
        value = value.get("name") or value.get("value") or json.dumps(value)[:200]
    if isinstance(value, list):
        names = []
        for v in value:
            if isinstance(v, dict):
                names.append(str(v.get("person_name") or v.get("name") or v.get("fund_manager") or ""))
            else:
                names.append(str(v))
        value = ", ".join(n for n in names if n)
        if not value:
            return None
    if isinstance(value, (int, float)):
        if fact == "expense_ratio":
            return f"{value}%"
        if fact in ("min_sip", "min_lumpsum"):
            return f"₹{int(value):,}"
        if fact in ("aum", "amc_aum"):
            return f"₹{value:,.2f} Cr"
        if fact == "nav":
            return f"₹{value:,.2f}"
        if fact == "lock_in":
            return "No lock-in" if value == 0 else f"{value} years"
        return str(value)
    text = re.sub(r"<[^>]+>", " ", str(value))  # strip any inline HTML
    text = re.sub(r"\s+", " ", text).strip()
    if fact == "expense_ratio" and re.fullmatch(r"[0-9.]+", text):
        text += "%"
    if fact in ("min_sip", "min_lumpsum") and re.fullmatch(r"[0-9.]+", text):
        text = f"₹{int(float(text)):,}"
    if fact == "risk" and "risk" not in text.lower():
        text += " risk"
    return text[:600] or None


def extract_facts(next_data: Any, text: str, fact_defs: dict, scheme_name: str) -> tuple[dict, dict]:
    """Return (facts, provenance) where provenance says json/regex for each fact."""
    facts, prov = {}, {}
    main = find_main_dict(next_data, fact_defs, scheme_name) if next_data else None
    for fact, d in fact_defs.items():
        val = None
        if main:
            for k in d["keys"]:
                if k in main:
                    val = _format_value(fact, main[k])
                    if val:
                        prov[fact] = f"json:{k}"
                        break
        if not val:
            for pattern in d["regex"]:
                m = re.search(pattern, text, flags=re.IGNORECASE if fact != "fund_manager" else 0)
                if m:
                    val = _format_value(fact, m.group(1).strip())
                    if val:
                        prov[fact] = "regex"
                        break
        if val:
            facts[fact] = val
    return facts, prov


# ----------------------------------------------------------------------------------------
# HTML helpers
# ----------------------------------------------------------------------------------------

def _clean_lines(text: str) -> str:
    out, prev = [], None
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line.lower() in NOISE_LINES or len(line) < 2:
            continue
        if line == prev:
            continue
        out.append(line)
        prev = line
    return "\n".join(out)


def extract_faqs(soup: BeautifulSoup, next_data: Any) -> list[dict]:
    faqs: list[dict] = []
    # 1) JSON-LD FAQPage
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for d, _ in _iter_dicts(data):
            if d.get("@type") == "Question" and d.get("name"):
                ans = d.get("acceptedAnswer", {})
                ans_text = ans.get("text") if isinstance(ans, dict) else str(ans)
                faqs.append({"q": d["name"], "a": ans_text or ""})
    # 2) embedded JSON lists with question/answer keys
    if next_data and not faqs:
        for d, _ in _iter_dicts(next_data):
            q = d.get("question") or d.get("q")
            a = d.get("answer") or d.get("a")
            if isinstance(q, str) and isinstance(a, str) and q.strip().endswith("?"):
                faqs.append({"q": q, "a": a})
    clean = []
    seen = set()
    for f in faqs:
        q = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", f["q"])).strip()
        a = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", f["a"] or "")).strip()
        if q and a and q.lower() not in seen:
            seen.add(q.lower())
            clean.append({"q": q, "a": a})
    return clean


def extract_sections(soup: BeautifulSoup) -> list[dict]:
    body = soup.body or soup
    for tag in body.find_all(["script", "style", "noscript", "svg", "iframe", "nav", "footer", "header", "form"]):
        tag.decompose()
    marker = "§§H§§"
    for h in body.find_all(["h1", "h2", "h3", "h4"]):
        h.replace_with(f"\n{marker}{h.get_text(' ', strip=True)}\n")
    text = body.get_text("\n")
    sections, current = [], {"heading": "Overview", "lines": []}
    for line in text.splitlines():
        if line.strip().startswith(marker):
            if current["lines"]:
                sections.append(current)
            current = {"heading": line.strip()[len(marker):].strip() or "Section", "lines": []}
        else:
            current["lines"].append(line)
    if current["lines"]:
        sections.append(current)
    result = []
    for s in sections:
        t = _clean_lines("\n".join(s["lines"]))
        if len(t) >= 40:
            result.append({"heading": s["heading"], "text": t})
    return result


def load_one(src: dict, html: str, scraped_at: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else src["label"]
    meta = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta.get("content", "").strip() if meta else ""

    next_data = None
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            next_data = json.loads(nd.string)
        except json.JSONDecodeError:
            next_data = None

    faqs = extract_faqs(soup, next_data)
    sections = extract_sections(BeautifulSoup(html, "lxml"))
    full_text = "\n".join(s["text"] for s in sections)
    if meta_desc:
        full_text = meta_desc + "\n" + full_text

    defs = SCHEME_FACTS if src["page_type"] == "scheme" else AMC_FACTS
    facts, prov = extract_facts(next_data, full_text, defs, src["scheme_name"])

    return {
        "doc_id": src["doc_id"],
        "url": src["url"],
        "page_type": src["page_type"],
        "scheme_name": src["scheme_name"],
        "category": src["category"],
        "title": title,
        "meta_description": meta_desc,
        "scraped_at": scraped_at,
        "facts": facts,
        "fact_labels": {k: defs[k]["label"] for k in facts},
        "fact_provenance": prov,
        "sections": sections,
        "faqs": faqs,
        "has_next_data": next_data is not None,
        "text_chars": len(full_text),
    }


def load_all() -> list[dict]:
    raw_dir, out_dir = path("raw_dir"), path("loaded_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = raw_dir / "manifest.json"
    manifest = {m["doc_id"]: m for m in json.loads(manifest_file.read_text(encoding="utf-8"))} if manifest_file.exists() else {}

    docs, report = [], []
    for src in sources():
        f = raw_dir / f"{src['doc_id']}.html"
        if not f.exists():
            print(f"[skip] {src['doc_id']}: no raw HTML (run phase 2 first)")
            continue
        scraped_iso = manifest.get(src["doc_id"], {}).get("scraped_at") or datetime.now().isoformat()
        scraped_at = scraped_iso[:10]
        doc = load_one(src, f.read_text(encoding="utf-8"), scraped_at)
        (out_dir / f"{src['doc_id']}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
        docs.append(doc)
        report.append({
            "doc_id": doc["doc_id"],
            "facts_found": sorted(doc["facts"]),
            "facts_missing": sorted(set((SCHEME_FACTS if doc["page_type"] == "scheme" else AMC_FACTS)) - set(doc["facts"])),
            "sections": len(doc["sections"]),
            "faqs": len(doc["faqs"]),
            "used_embedded_json": doc["has_next_data"],
            "text_chars": doc["text_chars"],
        })
        print(f"[ok] {doc['doc_id']}: {len(doc['facts'])} facts, {len(doc['sections'])} sections, {len(doc['faqs'])} FAQs")
        for k, v in doc["facts"].items():
            print(f"      - {k}: {v[:90]}")

    (out_dir / "load_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nPhase 3 complete: {len(docs)} documents saved to {out_dir}")
    return docs


if __name__ == "__main__":
    load_all()
