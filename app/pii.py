from __future__ import annotations

import hashlib
import re

PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "cccd": r"\b\d{12}\b",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    "passport": r"\b[A-Z]\d{7}\b",
    "address_vn": r"(?i:\b(?:số\s+)?\d+[A-Za-z0-9\/-]*)(?:,\s*|\s+)(?:(?i:đường|phố|ngõ|ngách|hẻm|phường|quận)\b(?:\s+(?:[A-ZÀ-Ỹ0-9][a-zà-ỹA-ZÀ-Ỹ0-9\/-]*|[a-zà-ỹA-ZÀ-Ỹ0-9\/-]*[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ][a-zà-ỹA-ZÀ-Ỹ0-9\/-]*)){1,4}|(?:[A-ZÀ-Ỹ][a-zà-ỹA-ZÀ-Ỹ]*[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ][a-zà-ỹA-ZÀ-Ỹ]*)(?:\s+[A-ZÀ-Ỹ][a-zà-ỹA-ZÀ-Ỹ]*[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ][a-zà-ỹA-ZÀ-Ỹ]*){1,3})",
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
