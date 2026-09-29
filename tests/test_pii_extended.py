from __future__ import annotations

import pytest

from app.pii import PII_PATTERNS, hash_user_id, scrub_text, summarize_text


def test_pii_patterns_ordering() -> None:
    keys = list(PII_PATTERNS.keys())
    assert keys[0] == "email"
    assert keys.index("credit_card") < keys.index("cccd")
    assert keys.index("credit_card") < keys.index("phone_vn")
    assert keys.index("cccd") < keys.index("phone_vn")


def test_scrub_email() -> None:
    text = "Please reach out to support.team@example.com for assistance."
    out = scrub_text(text)
    assert "support.team@example.com" not in out
    assert "[REDACTED_EMAIL]" in out


@pytest.mark.parametrize(
    "phone_number",
    [
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    ],
)
def test_scrub_vn_phone_formats(phone_number: str) -> None:
    text = f"Contact phone: {phone_number}"
    out = scrub_text(text)
    assert phone_number not in out
    assert "[REDACTED_PHONE_VN]" in out


def test_scrub_cccd() -> None:
    cccd = "012345678901"
    text = f"Citizen ID: {cccd}"
    out = scrub_text(text)
    assert cccd not in out
    assert "[REDACTED_CCCD]" in out


@pytest.mark.parametrize(
    "card_number",
    [
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "4111111111111111",
    ],
)
def test_scrub_credit_cards(card_number: str) -> None:
    text = f"Payment card is {card_number}"
    out = scrub_text(text)
    assert card_number not in out
    assert "[REDACTED_CREDIT_CARD]" in out
    assert "[REDACTED_CCCD]" not in out
    assert "[REDACTED_PHONE_VN]" not in out


def test_scrub_passport() -> None:
    passport = "C1234567"
    text = f"Passport number: {passport}"
    out = scrub_text(text)
    assert passport not in out
    assert "[REDACTED_PASSPORT]" in out


@pytest.mark.parametrize(
    "address",
    [
        "123 đường Lê Lợi",
        "12 Nguyễn Trãi",
        "số 5 đường Lê Lợi",
        "Số 5 Đường Lê Lợi",
        "123 phố Huế",
        "số 10 ngõ 5",
        "45 ngách 12",
        "67 hẻm 89",
        "10 phường Bến Nghé",
        "20 quận 1",
    ],
)
def test_scrub_vietnamese_address(address: str) -> None:
    text = f"Address is {address}."
    out = scrub_text(text)
    assert address not in out
    assert "[REDACTED_ADDRESS_VN]" in out


def test_english_sentence_preserved() -> None:
    sentence = "Explain why metrics traces and logs work together"
    out = scrub_text(sentence)
    assert out == sentence


def test_english_numbers_preserved() -> None:
    sentence = "In 2024, there are 12 items on page 5 with 3 errors."
    out = scrub_text(sentence)
    assert out == sentence


def test_summarize_text_scrubs_pii() -> None:
    raw_values = [
        "student@vinuni.edu.vn",
        "0901234567",
        "012345678901",
        "4111111111111111",
        "C1234567",
        "123 đường Lê Lợi",
    ]
    for val in raw_values:
        summary = summarize_text(f"Important user details: {val}")
        assert val not in summary
        assert "REDACTED_" in summary


def test_hash_user_id() -> None:
    hashed = hash_user_id("user-12345")
    assert len(hashed) == 12
    assert hash_user_id("user-12345") == hashed


def test_acceptance_criteria_exact_replacement() -> None:
    cases = [
        ("email: student@vinuni.edu.vn", "student@vinuni.edu.vn", "[REDACTED_EMAIL]"),
        ("phone: 0901234567", "0901234567", "[REDACTED_PHONE_VN]"),
        ("phone: 090 123 4567", "090 123 4567", "[REDACTED_PHONE_VN]"),
        ("phone: 090.123.4567", "090.123.4567", "[REDACTED_PHONE_VN]"),
        ("phone: 090-123-4567", "090-123-4567", "[REDACTED_PHONE_VN]"),
        ("phone: +84 90 123 4567", "+84 90 123 4567", "[REDACTED_PHONE_VN]"),
        ("cccd: 012345678901", "012345678901", "[REDACTED_CCCD]"),
        ("card: 4111 1111 1111 1111", "4111 1111 1111 1111", "[REDACTED_CREDIT_CARD]"),
        ("card: 4111-1111-1111-1111", "4111-1111-1111-1111", "[REDACTED_CREDIT_CARD]"),
        ("card: 4111111111111111", "4111111111111111", "[REDACTED_CREDIT_CARD]"),
        ("passport: C1234567", "C1234567", "[REDACTED_PASSPORT]"),
        ("address: 123 đường Lê Lợi", "123 đường Lê Lợi", "[REDACTED_ADDRESS_VN]"),
    ]
    for prompt, raw, token in cases:
        scrubbed = scrub_text(prompt)
        assert raw not in scrubbed
        assert token in scrubbed
        assert scrubbed == f"{prompt.split(':')[0]}: {token}"
        summary = summarize_text(prompt)
        assert raw not in summary
        assert token in summary
