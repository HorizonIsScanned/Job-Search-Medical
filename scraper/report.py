"""Per-run transparency report: which sources were read and what happened to every posting.

Contains only public posting data (title, employer, place, link) and run metrics,
never the candidate profile.
"""
from __future__ import annotations

SOURCES: list[dict] = []


def source(group: str, name: str, url: str, count: int, status: str = "ok", note: str = "") -> None:
    if status == "ok" and count == 0:
        status = "empty"
    SOURCES.append({"group": group, "name": name, "url": url, "count": count, "status": status, "note": note[:160]})
