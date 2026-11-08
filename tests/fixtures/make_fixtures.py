"""Builds FAKE Groww-like HTML pages for offline tests.

All values below are invented test data (marked FIXTURE) — they are NOT real fund facts and
are never written to the real data/ folder.
"""
import json
from pathlib import Path

SCHEMES = {
    "hdfc-large-cap": dict(name="HDFC Large Cap Fund Direct Growth", er="0.11", load="Exit load of 1% if redeemed within 1 year",
                           sip=111, lump=112, risk="Very High", bench="NIFTY 100 Total Return Index", lock=None),
    "hdfc-mid-cap": dict(name="HDFC Mid Cap Fund Direct Growth", er="0.22", load="Exit load of 1% if redeemed within 1 year",
                         sip=221, lump=222, risk="Very High", bench="NIFTY Midcap 150 Total Return Index", lock=None),
    "hdfc-elss": dict(name="HDFC ELSS Tax Saver Fund Direct Plan Growth", er="0.33", load="Nil",
                      sip=500, lump=500, risk="Very High", bench="NIFTY 500 Total Return Index",
                      lock={"years": 3, "months": 0, "days": 0}),
}


def scheme_page(doc_id: str, d: dict) -> str:
    main = {
        "scheme_name": d["name"], "fund_house": "HDFC Mutual Fund", "expense_ratio": d["er"], "exit_load": d["load"],
        "min_sip_investment": d["sip"], "min_investment_amount": d["lump"], "nfo_risk": d["risk"],
        "benchmark_name": d["bench"], "lock_in": d["lock"], "aum": 12345.67, "nav": 100.5, "nav_date": "07-Nov-2026",
        "launch_date": "01-Jan-2013", "sub_category": doc_id.split("-", 1)[1].replace("-", " ").title(),
        "description": f"FIXTURE objective: {d['name']} aims to generate long-term capital appreciation.",
        "fund_manager_details": [{"person_name": "Fixture Manager One"}, {"person_name": "Fixture Manager Two"}],
        "stamp_duty": "0.005% (from July 1st, 2020)",
        "similar_funds": [{"scheme_name": "Some Other Fund Direct Growth", "expense_ratio": "9.99", "nfo_risk": "Low",
                           "min_sip_investment": 9999, "benchmark_name": "WRONG INDEX"}],
    }
    next_data = {"props": {"pageProps": {"mfServerSideData": main}}}
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"What is the expense ratio of {d['name']}?",
         "acceptedAnswer": {"@type": "Answer", "text": f"The expense ratio is {d['er']}% (FIXTURE)."}},
        {"@type": "Question", "name": "How can I download my capital gains statement?",
         "acceptedAnswer": {"@type": "Answer", "text": "FIXTURE: Go to Mutual Funds > Reports > Capital gains statement and download it."}},
    ]}
    return f"""<!DOCTYPE html><html><head><title>{d['name']} - FIXTURE</title>
<meta name="description" content="FIXTURE page for {d['name']}">
<script type="application/ld+json">{json.dumps(faq_ld)}</script></head>
<body><nav>Login Sign up</nav>
<h1>{d['name']}</h1><div>Equity</div><div>{d['risk']} Risk</div>
<h2>Exit load, stamp duty and tax</h2><div>Exit load</div><div>{d['load']}</div>
<div>Stamp duty</div><div>0.005% (from July 1st, 2020)</div>
<h2>Investment Objective</h2><p>{main['description']} The scheme invests predominantly in equity and equity related instruments.</p>
<h2>Fund management</h2><p>Fixture Manager One has managed this fund since 2022. Education: FIXTURE.</p>
<footer>Groww footer</footer>
<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>
{'<div>' + ('filler text ' * 2000) + '</div>'}
</body></html>"""


def flexi_page_without_json() -> str:
    """No __NEXT_DATA__ -> exercises the regex fallback on visible text."""
    return """<!DOCTYPE html><html><head><title>HDFC Flexi Cap Fund Direct Plan Growth - FIXTURE</title></head><body>
<h1>HDFC Flexi Cap Fund Direct Plan Growth</h1>
<div>Min. for SIP</div><div>₹444</div><div>Fund size (AUM)</div><div>₹4,444.44 Cr</div>
<div>Expense ratio</div><div>0.44%</div>
<h2>Exit load, stamp duty and tax</h2>
<p>The HDFC Flexi Cap Fund Direct Plan Growth is rated Very High risk. Minimum SIP Investment is set to ₹444.
Minimum Lumpsum Investment is ₹445. Exit load of 1% if redeemed within 1 year</p>
<div>Benchmark</div><div>NIFTY 500 Total Return Index</div>
<h2>Investment Objective</h2><p>FIXTURE: To generate capital appreciation from a portfolio of equity and equity related securities.</p>
</body></html>"""


def amc_page() -> str:
    data = {"props": {"pageProps": {"amcData": {"amc_name": "HDFC Mutual Fund", "aum": 900000.5, "launch_date": "30-Jun-2000",
                                                 "total_schemes": 99, "ceo": "Fixture Ceo Name", "website": "https://www.hdfcfund.com"}}}}
    return f"""<!DOCTYPE html><html><head><title>HDFC Mutual Fund - FIXTURE</title></head><body>
<h1>HDFC Mutual Fund</h1><h2>About HDFC Mutual Fund</h2>
<p>FIXTURE: HDFC Mutual Fund is one of the largest mutual fund houses in India, offering equity, debt and hybrid schemes.</p>
<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>"""


def write_all(raw_dir: Path) -> list[dict]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    pages = {k: scheme_page(k, v) for k, v in SCHEMES.items()}
    pages["hdfc-flexi-cap"] = flexi_page_without_json()
    pages["hdfc-amc"] = amc_page()
    manifest = []
    for doc_id, html in pages.items():
        (raw_dir / f"{doc_id}.html").write_text(html, encoding="utf-8")
        manifest.append({"doc_id": doc_id, "ok": True, "status": 200, "scraped_at": "2026-11-08T10:00:00+00:00"})
    (raw_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest
