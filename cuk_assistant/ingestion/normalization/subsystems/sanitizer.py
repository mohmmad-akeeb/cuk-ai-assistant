"""PII Sanitizer for extracted text and record metadata.

Scrubs phone numbers, DOBs, roll numbers, and sensitive personal identifiers.
"""

from __future__ import annotations

import re
from typing import Any

# Regex patterns for sensitive personal data
_MOBILE_RE = re.compile(r"\b[6-9]\d{9}\b")
_PHONE_GENERIC_RE = re.compile(r"\b(?:\+91[- ]?)?[6-9]\d{9}\b")
_DOB_ISO_RE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}T00:00:00\b")
_DOB_TEXT_RE = re.compile(
    r"\b(?:DOB|Date\s*of\s*Birth|D\.O\.B)[\s:]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})\b",
    re.IGNORECASE,
)
_ROLL_NO_RE = re.compile(
    r"\b(?:Roll\s*(?:No|Number)|Registration\s*(?:No|Number))[\s:]*([A-Za-z0-9\-_/]{4,16})\b",
    re.IGNORECASE,
)

_SENSITIVE_RECORD_KEYS: set[str] = {
    "dob",
    "dateofbirth",
    "mobileno",
    "mobile_no",
    "phone",
    "phoneno",
    "personal_email",
    "aadhar",
    "aadharno",
    "pan",
    "panno",
    "bankaccount",
    "accountno",
    "ifsc",
    "salary",
}


def scrub_phone_numbers(text: str) -> str:
    """Replace mobile and contact numbers with [REDACTED-PHONE]."""
    text = _PHONE_GENERIC_RE.sub("[REDACTED-PHONE]", text)
    text = _MOBILE_RE.sub("[REDACTED-PHONE]", text)
    return text


def scrub_dob(text: str) -> str:
    """Replace date of birth representations with [REDACTED-DOB]."""
    text = _DOB_ISO_RE.sub("[REDACTED-DOB]", text)
    text = _DOB_TEXT_RE.sub(r"DOB: [REDACTED-DOB]", text)
    return text


def scrub_roll_numbers(text: str) -> str:
    """Redact student roll / registration numbers."""
    return _ROLL_NO_RE.sub(r"Roll No: [REDACTED-ROLL-NO]", text)


def mask_email(email: str) -> str:
    """Mask email addresses, e.g. j***@cukashmir.ac.in."""
    if not email or "@" not in email:
        return email
    user, domain = email.split("@", 1)
    masked_user = user[0] + "*" if len(user) <= 2 else user[0] + "*" * (len(user) - 2) + user[-1]
    return f"{masked_user}@{domain}"


def scrub_pii(text: str) -> str:
    """Apply all text PII scrubbing guards."""
    if not text:
        return ""
    text = scrub_phone_numbers(text)
    text = scrub_dob(text)
    text = scrub_roll_numbers(text)
    return text


def sanitize_record_dict(record: dict[str, Any]) -> dict[str, Any]:
    """Strip known PII keys from a raw record dictionary."""
    clean: dict[str, Any] = {}
    for k, v in record.items():
        if k.lower().replace("_", "") in _SENSITIVE_RECORD_KEYS:
            continue
        if isinstance(v, str):
            clean[k] = scrub_pii(v)
        elif isinstance(v, dict):
            clean[k] = sanitize_record_dict(v)
        elif isinstance(v, list):
            clean[k] = [
                sanitize_record_dict(item)
                if isinstance(item, dict)
                else (scrub_pii(item) if isinstance(item, str) else item)
                for item in v
            ]
        else:
            clean[k] = v
    return clean


__all__ = [
    "mask_email",
    "sanitize_record_dict",
    "scrub_dob",
    "scrub_phone_numbers",
    "scrub_pii",
    "scrub_roll_numbers",
]

class Sanitizer:
    @staticmethod
    def scrub_pii(text: str) -> str:
        return scrub_pii(text)

    @staticmethod
    def sanitize_record_dict(record: dict[str, Any]) -> dict[str, Any]:
        return sanitize_record_dict(record)
