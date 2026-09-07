"""
Regex-based extractors for entity types that a generic NER model handles
poorly: phone numbers, vehicle registrations, financial account/UPI
identifiers. These run alongside spaCy's statistical NER rather than
instead of it -- see entity_extraction.py.

Patterns are tuned for Indian formats since this PS is for NCRB / an
Indian law-enforcement audience, but are written so new patterns
(e.g. IMEI, passport, Aadhaar-masked refs) can be added without touching
the extraction pipeline itself.
"""
import re

# +91 98765 43210 / 09876543210 / 9876543210 / with dashes or the common
# "XXXXX XXXXX" mid-number space/dash grouping.
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?91[\-\s]?)?[6-9]\d{4}[\-\s]?\d{5}(?!\d)"
)

# Indian vehicle registration: MP09AB1234, MP-09-AB-1234, DL 1C AB 1234 etc.
VEHICLE_RE = re.compile(
    r"\b[A-Z]{2}[\-\s]?\d{1,2}[\-\s]?[A-Z]{1,3}[\-\s]?\d{4}\b"
)

# UPI handle: name@bank
UPI_RE = re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b")

# Bank-style account number (9-18 digits, standalone)
ACCOUNT_RE = re.compile(r"(?<!\d)\d{9,18}(?!\d)")

# IMEI (15 digits)
IMEI_RE = re.compile(r"(?<!\d)\d{15}(?!\d)")


def find_phones(text: str) -> list[str]:
    normalized = set()
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        normalized.add(digits[-10:])  # drop a leading country code (91) if present
    return sorted(normalized)


def find_vehicles(text: str) -> list[str]:
    return sorted({m.group(0).replace(" ", "").replace("-", "").upper() for m in VEHICLE_RE.finditer(text)})


def find_upi_handles(text: str) -> list[str]:
    return sorted({m.group(0) for m in UPI_RE.finditer(text)})


def find_account_numbers(text: str) -> list[str]:
    # Filter out phone-number-length matches already caught by PHONE_RE
    phones = set(find_phones(text))
    return sorted({m.group(0) for m in ACCOUNT_RE.finditer(text) if m.group(0) not in phones})


RELATION_VERB_MAP: dict[str, str] = {
    # lemma -> relation type, used by the light-weight relation extractor
    "call": "CALLED",
    "phone": "CALLED",
    "meet": "MET_AT",
    "transfer": "TRANSACTED_WITH",
    "pay": "TRANSACTED_WITH",
    "send": "TRANSACTED_WITH",
    "own": "OWNS",
    "drive": "OWNS",
    "associate": "ASSOCIATED_WITH",
    "know": "ASSOCIATED_WITH",
    "work": "MEMBER_OF",
    "lead": "MEMBER_OF",
    "belong": "MEMBER_OF",
    "visit": "PRESENT_AT",
    "reside": "PRESENT_AT",
    "live": "PRESENT_AT",
}
