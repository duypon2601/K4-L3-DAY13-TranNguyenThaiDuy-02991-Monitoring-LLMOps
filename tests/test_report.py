from __future__ import annotations

from pathlib import Path
import re
import pytest

from app.pii import PII_PATTERNS

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "submission" / "REPORT.md"
EVIDENCE_README_PATH = REPO_ROOT / "submission" / "evidence" / "README.md"
ROOT_README_PATH = REPO_ROOT / "README.md"

ORIGINAL_SECTION_HEADINGS = [
    "## 1. Thông tin học viên",
    "## 2. Evidence index",
    "## 3. Kết quả kỹ thuật",
    "## 4. Logging và PII",
    "## 5. Tracing và prompt versioning",
    "## 6. Dashboard, SLO và alerts",
    "## 7. Điều tra challenge",
    "## 8. Giải thích và tự đánh giá",
    "## 9. Checklist trước khi nộp",
]


def test_report_exists() -> None:
    assert REPORT_PATH.is_file(), f"File not found: {REPORT_PATH}"


def test_report_contains_all_nine_headings() -> None:
    content = REPORT_PATH.read_text(encoding="utf-8")
    for heading in ORIGINAL_SECTION_HEADINGS:
        assert heading in content, f"Missing section heading: {heading}"


def test_report_student_information() -> None:
    content = REPORT_PATH.read_text(encoding="utf-8")
    assert "Trần Nguyễn Thái Duy" in content, "Missing student name: Trần Nguyễn Thái Duy"
    assert "K4-L3A" in content, "Missing class: K4-L3A"
    expected_repo = "https://github.com/duypon2601/K4-L3-DAY13-TranNguyenThaiDuy-02991-Monitoring-LLMOps"
    assert expected_repo in content, f"Missing repository URL: {expected_repo}"


def test_report_bullets_in_sections_4_5_6_8() -> None:
    content = REPORT_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    target_sections = {
        "## 4. Logging và PII",
        "## 5. Tracing và prompt versioning",
        "## 6. Dashboard, SLO và alerts",
        "## 8. Giải thích và tự đánh giá",
    }

    current_section: str | None = None
    section_bullets: dict[str, list[tuple[str, str]]] = {s: [] for s in target_sections}

    bullet_pattern = re.compile(r"^\s*-\s*\*\*(.*?):\*\*\s*(.*)$")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            current_section = stripped if stripped in target_sections else None
            continue

        if current_section:
            m = bullet_pattern.match(line)
            if m:
                label = m.group(1).strip()
                val = m.group(2).strip()
                section_bullets[current_section].append((label, val))

    # Verify that each section has bullets and every bullet has text or <CẦN ĐIỀN>
    for sec, bullets in section_bullets.items():
        assert bullets, f"No bullets found in section {sec}"
        for label, val in bullets:
            assert len(val) > 0, f"Empty content after colon for bullet '**{label}:**' in {sec}"
            is_valid = val == "<CẦN ĐIỀN>" or "<CẦN ĐIỀN>" in val or len(val) >= 5
            assert is_valid, f"Bullet '**{label}:**' in {sec} has invalid content: {val}"


def test_report_evidence_relative_links() -> None:
    content = REPORT_PATH.read_text(encoding="utf-8")

    # Check for forbidden absolute paths
    for forbidden in ["/Users/", "C:\\", "/home/"]:
        assert forbidden not in content, f"Found forbidden absolute path '{forbidden}' in REPORT.md"

    # Find all evidence references
    evidence_matches = re.findall(r"`(evidence/[^`]+)`", content)
    assert len(evidence_matches) >= 14, f"Expected at least 14 evidence paths, found {len(evidence_matches)}"

    for path in evidence_matches:
        assert path.startswith("evidence/"), f"Path must start with evidence/: {path}"
        assert not path.startswith("/"), f"Path must be relative: {path}"


def test_report_no_langfuse_keys_and_no_pii() -> None:
    content = REPORT_PATH.read_text(encoding="utf-8")

    # No Langfuse secret/public keys followed by characters
    assert not re.search(r"pk-lf-[A-Za-z0-9-]{4,}", content), "Found string matching pk-lf- in REPORT.md"
    assert not re.search(r"sk-lf-[A-Za-z0-9-]{4,}", content), "Found string matching sk-lf- in REPORT.md"

    # No PII per app.pii.PII_PATTERNS
    for kind, pattern in PII_PATTERNS.items():
        match = re.search(pattern, content)
        assert match is None, f"Found raw PII of kind '{kind}' in REPORT.md: {match.group(0) if match else ''}"


def test_evidence_readme_contents() -> None:
    assert EVIDENCE_README_PATH.is_file(), f"File not found: {EVIDENCE_README_PATH}"
    content = EVIDENCE_README_PATH.read_text(encoding="utf-8")

    assert "pytest -q > submission/evidence/01-pytest.txt" in content
    assert "validate_logs.py" in content
    assert "validate_dashboard.py" in content
    assert "scan_repo.py" in content
    assert "build_dashboard.py" in content


def test_root_readme_additional_tools() -> None:
    assert ROOT_README_PATH.is_file(), f"File not found: {ROOT_README_PATH}"
    content = ROOT_README_PATH.read_text(encoding="utf-8")

    assert "## Công cụ bổ sung" in content
    assert "build_dashboard.py" in content
    assert "scan_repo.py" in content
