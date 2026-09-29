from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from scripts import scan_repo
from scripts.scan_repo import (
    REPO_ROOT,
    Finding,
    check_forbidden_tracked_files,
    is_allowlisted,
    main,
    scan_paths,
)


def test_scan_paths_finds_fake_langfuse_key_and_email(tmp_path: Path) -> None:
    test_file = tmp_path / "sensitive.txt"
    test_file.write_text(
        "LANGFUSE_SECRET_KEY=sk-lf-abcdefgh12345678\n"
        "Contact me at alice@example.com for access\n",
        encoding="utf-8",
    )

    findings = scan_paths([test_file])

    assert len(findings) == 2
    kinds = {f.kind for f in findings}
    assert kinds == {"langfuse_secret_key", "email"}

    # Ensure output format does not contain the secret or email value
    for f in findings:
        formatted = str(f)
        assert f"{f.path}:{f.line}:{f.kind}" == formatted
        assert "sk-lf-abcdefgh12345678" not in formatted
        assert "alice@example.com" not in formatted


def test_env_example_empty_value_is_not_finding(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.example"
    env_file.write_text(
        "APP_ENV=dev\n"
        "LANGFUSE_PUBLIC_KEY=\n"
        "LANGFUSE_SECRET_KEY=\n"
        "OPTIONAL_API_KEY=\"\"\n"
        "OTHER_SECRET=''\n"
        "# Comment line\n",
        encoding="utf-8",
    )

    findings = scan_paths([env_file])
    assert len(findings) == 0


def test_redacted_tokens_are_not_findings(tmp_path: Path) -> None:
    log_file = tmp_path / "sample.log"
    log_file.write_text(
        "User email: [REDACTED_EMAIL]\n"
        "User phone: [REDACTED_PHONE_VN]\n"
        "User card: [REDACTED_CREDIT_CARD]\n"
        "User cccd: [REDACTED_CCCD]\n"
        "Token: [REDACTED_SECRET]\n"
        "[REDACTED_EMAIL]\n",
        encoding="utf-8",
    )

    findings = scan_paths([log_file])
    assert len(findings) == 0


def test_generic_secret_detection(tmp_path: Path) -> None:
    conf_file = tmp_path / "app_config.py"
    conf_file.write_text(
        'api_key = "abcdef1234567890"\n'
        'secret: "super-secret-token-1234"\n',
        encoding="utf-8",
    )

    findings = scan_paths([conf_file])
    assert len(findings) == 2
    assert all(f.kind == "generic_secret" for f in findings)
    for f in findings:
        formatted = str(f)
        assert "abcdef1234567890" not in formatted
        assert "super-secret-token-1234" not in formatted


def test_langfuse_public_key_detection(tmp_path: Path) -> None:
    conf_file = tmp_path / "config.txt"
    conf_file.write_text(
        "LANGFUSE_PUBLIC_KEY=pk-lf-abcdefgh12345678\n",
        encoding="utf-8",
    )

    findings = scan_paths([conf_file])
    assert len(findings) == 1
    assert findings[0].kind == "langfuse_public_key"
    assert "pk-lf-abcdefgh12345678" not in str(findings[0])


def test_binary_and_image_skipping(tmp_path: Path) -> None:
    png_file = tmp_path / "test.png"
    png_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00sk-lf-abcdefgh12345678")

    bin_file = tmp_path / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02sk-lf-abcdefgh12345678alice@example.com")

    findings = scan_paths([png_file, bin_file])
    assert len(findings) == 0


def test_allowlisted_paths() -> None:
    assert is_allowlisted(REPO_ROOT / "tests" / "test_pii.py")
    assert is_allowlisted(REPO_ROOT / "data" / "sample_queries.jsonl")
    assert is_allowlisted(REPO_ROOT / "data" / "expected_answers.jsonl")
    assert is_allowlisted(REPO_ROOT / "PLAN.md")
    assert not is_allowlisted(REPO_ROOT / "app" / "main.py")


def test_forbidden_tracked_files_detection() -> None:
    mock_res = MagicMock()
    mock_res.stdout = "config/challenge.json\n.env\n"
    mock_res.returncode = 0

    with patch("subprocess.run", return_value=mock_res):
        findings = check_forbidden_tracked_files(REPO_ROOT)
        assert len(findings) == 2
        assert {f.path for f in findings} == {"config/challenge.json", ".env"}
        assert all(f.kind == "forbidden_tracked_file" for f in findings)


def test_cli_exits_1_when_finding_present(tmp_path: Path) -> None:
    test_file = tmp_path / "leak.txt"
    test_file.write_text("sk-lf-secretkey12345678\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_repo.py"), str(test_file)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert proc.returncode == 1
    assert "FOUND: 1 findings" in proc.stdout
    assert f"{test_file}:1:langfuse_secret_key" in proc.stdout
    assert "sk-lf-secretkey12345678" not in proc.stdout
    assert "sk-lf-secretkey12345678" not in proc.stderr


def test_scan_repo_via_subprocess_on_repository_exits_0() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_repo.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )

    assert proc.returncode == 0, f"Stderr: {proc.stderr}\nStdout: {proc.stdout}"
    assert "OK: no findings" in proc.stdout
    assert "FOUND" not in proc.stdout
