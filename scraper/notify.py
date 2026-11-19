"""Push notifications via ntfy (https://ntfy.sh). The topic is a secret."""
from __future__ import annotations

import os

import requests

from common import log


def _send(title: str, body: str, *, priority: str = "default", click: str = "", tags: str = "", alert: bool = False) -> None:
    topic = (alert and os.environ.get("NTFY_ALERT_TOPIC")) or os.environ.get("NTFY_TOPIC")
    if not topic:
        log("ntfy: no topic configured, skipping")
        return
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title.encode("utf-8"), "Priority": priority, "Markdown": "yes"}
    if click:
        headers["Click"] = click
    if tags:
        headers["Tags"] = tags
    try:
        r = requests.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=20)
        r.raise_for_status()
        log("ntfy: sent")
    except requests.RequestException as e:
        log(f"ntfy: failed ({type(e).__name__})")


def send_matches(new: list[dict], cfg: dict) -> None:
    send_research([j for j in new if j["match"].get("stream", "research") == "research"], cfg)
    send_bridge([j for j in new if j["match"].get("stream") == "bridge"], cfg)


def send_bridge(new: list[dict], cfg: dict) -> None:
    """One summary push per run for the transition stream, so the phone does not ring all day."""
    hits = sorted([j for j in new if j["match"]["status"] == "match"], key=lambda j: -j["match"]["score"])
    if not hits:
        log("ntfy: no new transition jobs")
        return
    lines = [f"- **{j['title']}** · {j['org']}" for j in hits[:5]]
    if len(hits) > 5:
        lines.append(f"\n… und {len(hits) - 5} weitere auf dem Board.")
    _send(f"{len(hits)} neue Übergangsjob{'s' if len(hits) != 1 else ''}", "\n".join(lines),
          click=os.environ.get("BOARD_URL", ""), tags="briefcase")


def send_research(new: list[dict], cfg: dict) -> None:
    ncfg = cfg["notify"]
    hits = sorted([j for j in new if j["match"]["status"] == "match" and j["match"]["score"] >= ncfg["min_score"]],
                  key=lambda j: -j["match"]["score"])
    if not hits:
        log("ntfy: no new matches above threshold")
        return
    board = os.environ.get("BOARD_URL", "")
    lines = []
    for j in hits[: ncfg["max_items"]]:
        kind = "Promotion" if j["match"].get("kind") == "phd" else "Job"
        lines.append(f"- **{j['title']}** · {j['org']} · {kind} · Score {j['match']['score']}\n  {j['url']}")
    if len(hits) > ncfg["max_items"]:
        lines.append(f"\n… und {len(hits) - ncfg['max_items']} weitere auf dem Board.")
    top = hits[0]["match"]["score"]
    title = f"{len(hits)} neue passende Stelle{'n' if len(hits) != 1 else ''}"
    _send(title, "\n".join(lines), priority="high" if top >= ncfg["high_priority_score"] else "default",
          click=board, tags="stethoscope")


def send_alert(text: str) -> None:
    _send("Jobboard: Problem beim täglichen Lauf", text, priority="low", tags="warning",
          click=os.environ.get("RUN_URL", ""), alert=True)
