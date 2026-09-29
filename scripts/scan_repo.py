from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable, NamedTuple, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.pii import PII_PATTERNS


class Finding(NamedTuple):
    path: str
    line: int
    kind: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.kind}"


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".bmp",
    ".tiff",
    ".webp",
    ".svg",
}

BINARY_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".zip",
    ".tar",
    ".gz",
    ".whl",
    ".db",
    ".sqlite",
    ".parquet",
    ".arrow",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}

LANGFUSE_PK_PATTERN = re.compile(r"pk-lf-[A-Za-z0-9-]{8,}")
LANGFUSE_SK_PATTERN = re.compile(r"sk-lf-[A-Za-z0-9-]{8,}")
GENERIC_SECRET_PATTERN = re.compile(r"(?i:(?:api[_-]?key|secret))\s*[=:]\s*(\S{12,})")
REDACTED_PATTERN = re.compile(r"\[REDACTED(?:_[A-Za-z0-9_]+)?\]")
EMPTY_ENV_PATTERN = re.compile(
    r"^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:['\"]{2}\s*|\s*)(?:#.*)?$"
)


def is_allowlisted(path: Path, repo_root: Path | None = None) -> bool:
    root = (repo_root or REPO_ROOT).resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(root)
        rel_posix = rel.as_posix()
    except ValueError:
        rel_posix = path.as_posix()

    parts = Path(rel_posix).parts
    if parts and parts[0] == "tests":
        return True

    if rel_posix in (
        "data/sample_queries.jsonl",
        "data/expected_answers.jsonl",
        "PLAN.md",
    ):
        return True

    return False


def is_binary_or_skipped(path: Path) -> bool:
    if any(part in (".venv", ".git") for part in path.parts):
        return True

    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS or suffix in BINARY_EXTENSIONS:
        return True

    return False


def scan_file(path: Path, repo_root: Path | None = None) -> list[Finding]:
    if not path.is_file():
        return []

    if is_binary_or_skipped(path):
        return []

    if is_allowlisted(path, repo_root):
        return []

    root = (repo_root or REPO_ROOT).resolve()
    try:
        display_path = str(path.resolve().relative_to(root))
    except ValueError:
        display_path = str(path)

    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return []
    except (OSError, IOError):
        return []

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    findings: list[Finding] = []
    lines = content.splitlines()

    for line_no, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue

        if EMPTY_ENV_PATTERN.match(raw_line):
            continue

        # Mask [REDACTED_...] tokens so they don't produce false findings
        scrubbed = REDACTED_PATTERN.sub(lambda m: " " * len(m.group(0)), raw_line)
        if not scrubbed.strip():
            continue

        # 1. Detect Langfuse public key
        pk_matches = list(LANGFUSE_PK_PATTERN.finditer(scrubbed))
        if pk_matches:
            for _ in pk_matches:
                findings.append(
                    Finding(path=display_path, line=line_no, kind="langfuse_public_key")
                )
            for m in pk_matches:
                scrubbed = (
                    scrubbed[: m.start()]
                    + (" " * (m.end() - m.start()))
                    + scrubbed[m.end() :]
                )

        # 2. Detect Langfuse secret key
        sk_matches = list(LANGFUSE_SK_PATTERN.finditer(scrubbed))
        if sk_matches:
            for _ in sk_matches:
                findings.append(
                    Finding(path=display_path, line=line_no, kind="langfuse_secret_key")
                )
            for m in sk_matches:
                scrubbed = (
                    scrubbed[: m.start()]
                    + (" " * (m.end() - m.start()))
                    + scrubbed[m.end() :]
                )

        # 3. Detect generic secret
        gen_matches = list(GENERIC_SECRET_PATTERN.finditer(scrubbed))
        if gen_matches:
            for _ in gen_matches:
                findings.append(
                    Finding(path=display_path, line=line_no, kind="generic_secret")
                )
            for m in gen_matches:
                val_start = m.start(1)
                val_end = m.end(1)
                scrubbed = (
                    scrubbed[:val_start]
                    + (" " * (val_end - val_start))
                    + scrubbed[val_end:]
                )

        # 4. Detect raw PII using app.pii.PII_PATTERNS
        for pii_name, pattern_str in PII_PATTERNS.items():
            if re.search(pattern_str, scrubbed):
                findings.append(Finding(path=display_path, line=line_no, kind=pii_name))

    return findings


def scan_paths(
    paths: Iterable[Path | str] | Path | str,
    repo_root: Path | None = None,
) -> list[Finding]:
    root = (repo_root or REPO_ROOT).resolve()
    all_findings: list[Finding] = []

    if isinstance(paths, (str, Path)):
        items: Iterable[Path | str] = [paths]
    else:
        items = paths

    for item in items:
        p = Path(item)
        if not p.is_absolute():
            p = (root / p).resolve()
        else:
            p = p.resolve()

        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    all_findings.extend(scan_file(child, repo_root=root))
        elif p.is_file():
            all_findings.extend(scan_file(p, repo_root=root))

    return all_findings


def get_git_files(repo_root: Path | None = None) -> list[Path]:
    root = (repo_root or REPO_ROOT).resolve()
    cmd = ["git", "ls-files", "-co", "--exclude-standard"]
    try:
        res = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Error running git ls-files: {exc}", file=sys.stderr)
        return []

    files: list[Path] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if line:
            files.append(root / line)
    return files


def check_forbidden_tracked_files(repo_root: Path | None = None) -> list[Finding]:
    root = (repo_root or REPO_ROOT).resolve()
    cmd = ["git", "ls-files", "--", "config/challenge.json", ".env"]
    try:
        res = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    findings: list[Finding] = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if line in ("config/challenge.json", ".env"):
            findings.append(Finding(path=line, line=1, kind="forbidden_tracked_file"))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Scan repo for secrets and PII.")
    parser.add_argument("paths", nargs="*", help="Optional paths to scan")
    parser.add_argument("--repo-root", default=None, help="Repository root path")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT
    findings: list[Finding] = []

    if args.paths:
        findings.extend(scan_paths(args.paths, repo_root=root))
    else:
        findings.extend(check_forbidden_tracked_files(repo_root=root))
        git_files = get_git_files(repo_root=root)
        findings.extend(scan_paths(git_files, repo_root=root))

    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}:{finding.kind}")
        print(f"FOUND: {len(findings)} findings")
        return 1
    else:
        print("OK: no findings")
        return 0


if __name__ == "__main__":
    sys.exit(main())
