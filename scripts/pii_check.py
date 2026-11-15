"""Fail if personal data shows up in tracked files.

Patterns come from the PII_PATTERNS secret (comma separated, e.g. name,
e-mail, phone), so the check itself reveals nothing. Generic e-mail and
phone patterns are checked too.
"""
import os
import re
import subprocess
import sys

ALLOW_EMAIL = {"noreply@anthropic.com", "noreply@github.com"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+49[\s\d]{9,}|\b01[5-7]\d[\s/]?\d{6,}")

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
secret = [p.strip().lower() for p in os.environ.get("PII_PATTERNS", "").split(",") if p.strip()]
problems = []
for f in files:
    if f.endswith((".png", ".jpg", ".ico", ".lock")) or f == "package-lock.json":
        continue
    try:
        text = open(f, encoding="utf-8").read()
    except (UnicodeDecodeError, FileNotFoundError):
        continue
    low = text.lower()
    for p in secret:
        if p in low:
            problems.append(f"{f}: matches a protected pattern")
    for m in EMAIL.findall(text):
        if m.lower() not in ALLOW_EMAIL and not m.lower().endswith(("@example.com", "@example.org")):
            problems.append(f"{f}: e-mail address")
    if PHONE.search(text):
        problems.append(f"{f}: phone number")
if problems:
    print("Personal data check failed:")
    print("\n".join(sorted(set(problems))))
    sys.exit(1)
print(f"Personal data check passed ({len(files)} files, {len(secret)} protected patterns)")
