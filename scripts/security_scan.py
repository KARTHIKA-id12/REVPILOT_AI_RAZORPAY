#!/usr/bin/env python3
"""Small dependency-free secret hygiene check for CI and demo preparation."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml", ".toml", ".env"}
PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*['\"][^'\"]{16,}"), "hard-coded credential"),
]
ALLOWLIST = {
    "change-me-in-env", "dev-only-not-for-production", "RevPilotDemo123!", "unit-test-secret",
    "whsec_test_secret_for_ci", "whsec_test_12345",
}


def scan() -> list[str]:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if any(value in line for value in ALLOWLIST):
                continue
            for pattern, label in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{number}: {label}")
    return findings


if __name__ == "__main__":
    findings = scan()
    if findings:
        print("\n".join(findings))
        sys.exit(1)
    print("Secret scan passed: no credential-shaped literals found.")