"""Guardrails: decide ANSWER vs REFUSE before any retrieval happens (W1 — thinking like a model).

Order of checks: empty -> PII -> prompt-injection -> advice -> performance -> other AMC -> greeting.
Also detects which scheme and which fact the user is asking about.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- PII (never stored)
PII_PATTERNS: dict[str, re.Pattern] = {
    "PAN": re.compile(r"\b[A-Za-z]{5}[0-9]{4}[A-Za-z]\b"),
    "Aadhaar": re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
    "phone number": re.compile(r"(?:\+?91[\s-]?)?(?<!\d)[6-9]\d{9}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "OTP/PIN": re.compile(r"\b(?:otp|cvv|m?pin|upi pin|password|passcode)\b\D{0,20}\d{3,8}", re.I),
    "account/folio number": re.compile(r"\b(?:account|a/c|acct|acc|folio|bank|demat|dp id|client id)\b\D{0,25}\d{6,18}", re.I),
    "long ID number": re.compile(r"(?<!\d)\d{11,18}(?!\d)"),
}

INJECTION = re.compile(
    r"ignore (?:all |the )?(?:previous|above|prior|earlier) (?:instructions|rules)|system prompt|jailbreak|"
    r"developer mode|pretend (?:you are|to be)|act as (?:a|an) (?!fact)|disregard (?:your|the) rules",
    re.I,
)

ADVICE = re.compile(
    r"\bshould\s+i\b|\bshall\s+i\b|\bcan\s+i\s+(?:buy|sell|invest)\b|\bwould you\b|\bdo you think\b|"
    r"\bis (?:it|this|hdfc[\w\s]{0,30}) (?:a )?(?:good|bad|wise|right|safe|smart)\b|"
    r"\b(?:good|bad|safe|right|smart) (?:time|fund|investment|choice|option|buy)\b|"
    r"\bworth (?:it|investing|buying)\b|\b(?:best|better|top|safest|worst)\b|\brecommend|\bsuggest|\badvi[cs]e|"
    r"\bbuy or sell\b|\b(?:buy|sell|hold|switch|redeem) (?:now|today|it)\b|\bportfolio\b|\ballocat|"
    r"\bwhere (?:should|to|can) i invest\b|\bwhich (?:one|fund|scheme)\b.*\b(?:choose|pick|go for|prefer|invest)\b|"
    r"\b(?:stock|share) tips?\b|\bpredict|\bforecast|\bwill (?:it|the nav|nav|the fund) (?:go up|rise|fall|grow|increase|crash)\b|"
    r"\bguarantee",
    re.I,
)

PERFORMANCE = re.compile(
    r"\breturns?\b(?! index)|\bcagr\b|\bxirr\b|\bperform(?:ance|ed|ing|s)?\b|\boutperform|\bunderperform|"
    r"\bhow much (?:will|would|can|did) (?:i|my money|it) (?:earn|make|get|grow|gain)\b|\bprofit\b|"
    r"\b(?:annuali[sz]ed|absolute|historical|past|trailing)\s+(?:return|gain)|\bbeat (?:the )?(?:benchmark|index|market|nifty)\b",
    re.I,
)

OTHER_AMCS = re.compile(
    r"\b(?:sbi|icici|axis|nippon|kotak|uti|mirae|parag parikh|ppfas|quant|tata|dsp|aditya birla|absl|franklin|"
    r"motilal|bandhan|canara|edelweiss|invesco|hsbc|baroda|lic mf|mahindra|sundaram|whiteoak|navi|groww mutual|"
    r"groww large cap|zerodha)\b",
    re.I,
)

GREETING = re.compile(r"^\s*(?:hi+|hello+|hey+|namaste|good (?:morning|afternoon|evening)|thanks?|thank you|ok(?:ay)?)\W*$", re.I)

# ---------------------------------------------------------------- scheme + fact detection
SCHEME_ALIASES: dict[str, list[str]] = {
    "hdfc-elss": [r"\belss\b", r"tax[\s-]?sav(?:er|ing)", r"\b80c\b", r"long term advantage"],
    "hdfc-flexi-cap": [r"flexi[\s-]?cap", r"\bflexi\b", r"hdfc equity fund", r"\bequity fund\b"],
    "hdfc-mid-cap": [r"mid[\s-]?cap", r"mid[\s-]?cap opportunities"],
    "hdfc-large-cap": [r"large[\s-]?cap", r"\btop[\s-]?100\b"],
    "hdfc-amc": [r"\bamc\b", r"fund house", r"asset management", r"hdfc mutual fund\b(?!.*(?:cap|elss|tax))",
                 r"\bceo\b", r"\bcio\b", r"how many (?:schemes|funds)", r"hdfc mf\b"],
}

SCHEME_DISPLAY = {
    "hdfc-large-cap": "HDFC Large Cap Fund",
    "hdfc-flexi-cap": "HDFC Flexi Cap Fund",
    "hdfc-elss": "HDFC ELSS Tax Saver Fund",
    "hdfc-mid-cap": "HDFC Mid Cap Fund",
    "hdfc-amc": "HDFC Mutual Fund (AMC)",
}

FACT_KEYWORDS: list[tuple[str, str]] = [  # order matters: first match wins
    ("statement", r"statement|\bcas\b|account statement|download"),
    ("stamp_duty", r"stamp duty"),
    ("exit_load", r"exit[\s-]?load|exit charge|redemption (?:charge|fee|load)|\bload\b|withdraw\w* (?:charge|fee|penalty)"),
    ("expense_ratio", r"expense|\bter\b|management fee|annual fee|fund charges?"),
    ("min_sip", r"\bsip\b"),
    ("min_lumpsum", r"lump[\s-]?sum|one[\s-]?time|minimum (?:investment|amount)|min(?:imum)? invest"),
    ("lock_in", r"lock[\s-]?in|locked|lock in period"),
    ("risk", r"risk"),
    ("benchmark", r"benchmark|index (?:it )?tracks?"),
    ("aum", r"\baum\b|fund size|assets under management|size of the fund|corpus"),
    ("nav", r"\bnav\b|net asset value|unit price"),
    ("fund_manager", r"manager|manages|who runs|who handles"),
    ("launch_date", r"launch|inception|started|since when|how old"),
    ("objective", r"objective|aim of|goal of|what does .* invest|invests? in|strategy"),
    ("tax", r"\btax|ltcg|stcg"),
    ("category", r"category|type of fund|kind of fund"),
    ("isin", r"\bisin\b"),
]

# facts that only make sense for one specific scheme
SCHEME_SPECIFIC = {"expense_ratio", "exit_load", "min_sip", "min_lumpsum", "lock_in", "risk", "benchmark",
                   "aum", "nav", "fund_manager", "launch_date", "objective", "category", "isin"}

AMC_FACT_MAP = {"aum": "amc_aum", "launch_date": "amc_launch_date", "fund_manager": "amc_cio"}


@dataclass
class Intent:
    kind: str                 # ok | empty | pii | injection | advice | performance | other_amc | greeting
    detail: str = ""
    schemes: list[str] | None = None
    fact: str | None = None


def detect_pii(text: str) -> str | None:
    for name, pattern in PII_PATTERNS.items():
        if pattern.search(text):
            return name
    return None


def detect_schemes(text: str) -> list[str]:
    found = []
    for scheme, patterns in SCHEME_ALIASES.items():
        if any(re.search(p, text, re.I) for p in patterns):
            found.append(scheme)
    # the AMC alias is only kept when no specific scheme is mentioned
    if len(found) > 1 and "hdfc-amc" in found:
        found.remove("hdfc-amc")
    return found


def detect_fact(text: str) -> str | None:
    for fact, pattern in FACT_KEYWORDS:
        if re.search(pattern, text, re.I):
            return fact
    return None


def classify(question: str) -> Intent:
    q = (question or "").strip()
    if not q:
        return Intent("empty")
    pii = detect_pii(q)
    if pii:
        return Intent("pii", detail=pii)
    if INJECTION.search(q):
        return Intent("injection")
    schemes = detect_schemes(q)
    fact = detect_fact(q)
    if ADVICE.search(q):
        return Intent("advice", schemes=schemes, fact=fact)
    if PERFORMANCE.search(q):
        return Intent("performance", schemes=schemes, fact=fact)
    if OTHER_AMCS.search(q):
        return Intent("other_amc", schemes=schemes, fact=fact)
    if GREETING.match(q):
        return Intent("greeting")
    return Intent("ok", schemes=schemes, fact=fact)
