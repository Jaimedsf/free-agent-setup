"""Fail if the repository contains personal paths, e-mails, secrets or the excluded vendor names.

Usage: python scripts/privacy_scan.py   (scans files tracked by git)
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from freeagent.policy import forbidden_words  # noqa: E402

PATTERNS = [
    ("user path", re.compile(r"[A-Za-z]:\\Users\\(?![%$<])[^\\\s\"']+")),
    ("user path", re.compile(r"/home/(?!runner/)[a-z][\w-]*/")),
    # domain must end in a letters-only TLD, so `action@v10.3.2` version pins are not e-mails
    ("e-mail", re.compile(r"[\w.+-]+@(?!users\.noreply\.github\.com)[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")),
    ("secret", re.compile(r"nvapi-[\w-]{8,}")),
    ("secret", re.compile(r"sk-[\w-]{16,}")),
    ("secret", re.compile(r"gh[pousr]_\w{20,}")),
]
WORDS = re.compile("|".join(map(re.escape, forbidden_words())), re.IGNORECASE)


def scan(paths: list[Path]) -> list[str]:
    findings = []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(lines, 1):
            for reason, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path}:{n}: {reason}")
            if WORDS.search(line):
                findings.append(f"{path}:{n}: forbidden vendor name")
    return findings


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    findings = scan([Path(f) for f in files])
    print("\n".join(findings) or "privacy scan: clean")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
