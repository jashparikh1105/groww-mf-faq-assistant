"""Run the sample questions through the assistant and write SAMPLE_QA.md (deliverable)."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.answer import answer_question  # noqa: E402

QUESTIONS = [
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "What is the lock-in period of HDFC ELSS Tax Saver Fund?",
    "What is the exit load of HDFC Flexi Cap Fund?",
    "What is the minimum SIP amount for HDFC Large Cap Fund?",
    "What is the riskometer level of HDFC Mid Cap Fund?",
    "What is the benchmark of HDFC Large Cap Fund?",
    "Who manages HDFC ELSS Tax Saver Fund?",
    "How do I download my capital gains statement?",
    "Should I buy HDFC Flexi Cap Fund now?",
    "My PAN is ABCDE1234F, can you check my holdings?",
]


def main() -> None:
    lines = [
        "# Sample Q&A — HDFC Fund Facts Assistant",
        "",
        f"Generated on {datetime.now():%d %b %Y %H:%M} by running `python scripts/generate_sample_qa.py`.",
        "",
    ]
    for i, q in enumerate(QUESTIONS, 1):
        r = answer_question(q)
        label = "Learn more" if r["type"] in ("refusal", "pii_blocked") else "Source"
        lines += [
            f"## {i}. {q}",
            f"**Type:** `{r['type']}`  ",
            f"**Answer:** {r['answer']}  ",
            f"**{label}:** {r['source_url']}  ",
            f"**Last updated from sources:** {r['last_updated']}",
            "",
        ]
        print(f"{i:>2}. [{r['type']}] {q}\n    {r['answer']}\n    {r['source_url']}")
    md = "\n".join(lines)
    (ROOT / "SAMPLE_QA.md").write_text(md, encoding="utf-8")
    print("\nWrote SAMPLE_QA.md")

    # also refresh the copy inside README.md (between the markers)
    readme = ROOT / "README.md"
    start, end = "<!-- SAMPLE_QA_START -->", "<!-- SAMPLE_QA_END -->"
    text = readme.read_text(encoding="utf-8")
    if start in text and end in text:
        body = "\n".join(lines[4:]).replace("## ", "#### ")
        text = text.split(start)[0] + start + "\n" + body + "\n" + end + text.split(end)[1]
        readme.write_text(text, encoding="utf-8")
        print("Updated the Sample Q&A section in README.md")


if __name__ == "__main__":
    main()
