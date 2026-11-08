"""End-to-end answer contract: one link, <=3 sentences, last-updated date, correct refusals."""
import re

import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.rag.answer import answer_question, limit_sentences

client = TestClient(app)
URL_RE = re.compile(r"https?://\S+")


def _check_contract(r):
    assert r["source_url"].startswith("https://")
    assert len(URL_RE.findall(r["answer"])) == 0              # link shown separately, exactly one
    assert len(URL_RE.findall(r["text"])) == 1
    assert "Last updated from sources:" in r["text"]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z₹(])", r["answer"]) if s]
    assert len(sentences) <= 3


@pytest.mark.parametrize("q,url_part,expect", [
    ("What is the expense ratio of HDFC Mid Cap Fund?", "hdfc-mid-cap", "0.22%"),
    ("ELSS lock-in?", "hdfc-elss-tax-saver", "3 years"),
    ("Exit load of HDFC Flexi Cap?", "hdfc-equity-fund", "1%"),
    ("Minimum SIP for HDFC Large Cap Fund", "hdfc-large-cap", "₹111"),
    ("Riskometer of HDFC Mid Cap", "hdfc-mid-cap", "Very High"),
    ("Benchmark of HDFC Large Cap Fund", "hdfc-large-cap", "NIFTY 100"),
])
def test_factual_answers(q, url_part, expect):
    r = answer_question(q)
    assert r["type"] == "answer", r
    assert url_part in r["source_url"]
    assert expect in r["answer"]
    assert r["last_updated"] == "08 Nov 2026"
    _check_contract(r)


@pytest.mark.parametrize("q,kind,url_part", [
    ("Should I buy HDFC Flexi Cap Fund now?", "refusal", "sebi.gov.in"),
    ("Which is the best HDFC fund?", "refusal", "sebi.gov.in"),
    ("Compare 5Y returns of HDFC Large Cap", "refusal", "hdfc-large-cap"),
    ("My PAN is ABCDE1234F", "pii_blocked", "mutualfundssahihai"),
    ("Minimum SIP?", "clarify", "amc/hdfc-mutual-funds"),
    ("Expense ratio of large cap and mid cap", "clarify", "amc/hdfc-mutual-funds"),
    ("Expense ratio of SBI Bluechip?", "not_found", "amc/hdfc-mutual-funds"),
    ("", "clarify", "groww.in"),
])
def test_guarded_responses(q, kind, url_part):
    r = answer_question(q)
    assert r["type"] == kind, r
    assert url_part in r["source_url"]
    _check_contract(r)


def test_scheme_hint_used_for_follow_up():
    r = answer_question("What is the expense ratio?", scheme_hint="hdfc-elss")
    assert r["type"] == "answer" and "0.33%" in r["answer"]


def test_long_input_truncated():
    r = answer_question("exit load of HDFC Mid Cap " + "x" * 3000)
    assert r["type"] in ("answer", "not_found")


def test_limit_sentences():
    assert limit_sentences("One. Two. Three. Four.") == "One. Two. Three."
    assert limit_sentences("Ratio is 0.77%. Next.") == "Ratio is 0.77%. Next."


def test_api_endpoints():
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["disclaimer"] == "Facts-only. No investment advice."
    assert len(meta["examples"]) == 3 and len(meta["sources"]) == 5
    r = client.post("/api/ask", json={"question": "What is the exit load of HDFC Mid Cap Fund?"}).json()
    assert r["type"] == "answer"
    assert client.get("/").status_code == 200


def test_llm_path_parses_source_and_strips_thinking(monkeypatch):
    """Simulate a Groq qwen reply (with <think> block) without calling the internet."""
    import httpx

    from src.rag import llm

    calls = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content":
                "<think>user wants exit load</think>HDFC Mid Cap Fund Direct Growth charges an exit load of 1% if redeemed "
                "within 1 year. Units held longer have no exit load. Extra sentence one. Extra sentence two.\nSOURCE: [1]"}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["url"], calls["body"] = url, json
        return FakeResp()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    r = answer_question("What is the exit load of HDFC Mid Cap Fund?")
    assert calls["url"].startswith("https://api.groq.com/openai/v1")
    assert calls["body"]["temperature"] == 0.0
    assert "<think>" not in r["answer"] and "SOURCE" not in r["answer"]
    assert r["answer"].count(".") <= 4 and "Extra sentence two" not in r["answer"]   # cut to 3 sentences
    assert "hdfc-mid-cap" in r["source_url"]
    assert r["model"] == llm.model_name()


def test_llm_not_found_falls_back(monkeypatch):
    import httpx

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "NOT_FOUND"}}]}

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResp())
    r = answer_question("What is the expense ratio of HDFC Mid Cap Fund?")
    assert r["type"] == "answer" and "0.22%" in r["answer"]     # pinned fact card used
