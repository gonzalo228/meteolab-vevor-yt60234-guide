#!/usr/bin/env python3
"""Conservative pre-publication scanner; review findings manually."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP = {".git", "__pycache__", ".venv"}
BLOCKED_SUFFIXES = {".pcap", ".pcapng", ".cap", ".key", ".pem", ".p12", ".pfx"}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----"),
    "IPv4 privata": re.compile(r"(?<![\d.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2}(?![\d.])"),
    "MAC address": re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"),
    "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "AWS access key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        rel = path.relative_to(root)
        if path.suffix.lower() in BLOCKED_SUFFIXES or path.name in {".env", "id_rsa", "id_ed25519"}:
            findings.append(f"{rel}: tipo di file vietato")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"{rel}: file binario da verificare")
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{rel}:{number}: possibile {label}")
    return findings


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    results = scan(target)
    print("\n".join(results) if results else "Nessun pattern sensibile comune rilevato.")
    raise SystemExit(bool(results))

