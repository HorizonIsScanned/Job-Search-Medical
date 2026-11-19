"""Daily run: collect postings, filter, check requirements, store, notify.

State (data/state.json) is downloaded from and uploaded to a private Vercel
Blob store by scripts/blob.mjs; it is never committed.
"""
from __future__ import annotations

import json
from collections import Counter
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from common import Job, log  # noqa: E402
from match import Matcher, all_jobspy_queries, all_queries, decide, languages_from_text  # noqa: E402
import notify  # noqa: E402
import report  # noqa: E402
from sources import ats, bundesagentur, jobspy_boards, sites  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
RUNS = ROOT / "data" / "runs.json"
KEEP_RUNS = 30


def load_state() -> dict:
    if STATE.exists() and STATE.stat().st_size:
        return json.loads(STATE.read_text())
    return {"version": 1, "jobs": [], "seen": {}}


def now_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def matcher_loc_ok(cfg: dict, entry: dict) -> bool:
    """Re-apply the place rule to stored board entries (rules can get stricter)."""
    m = Matcher.__new__(Matcher)
    m.loc_aliases = [a.lower() for loc in cfg["locations"] for a in loc["aliases"]]
    m.remote_words = [w.lower() for w in cfg.get("remote_words", [])]
    return m.location_ok(Job(title=entry.get("title", ""), org="", location=entry.get("location", ""),
                             url=entry.get("url", ""), source="",
                             remote=bool(entry["match"].get("fully_remote", False if "role" in entry["match"] else entry.get("remote")))))


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "search.yaml").read_text())
    only = set(filter(None, os.environ.get("ONLY_SOURCES", "").split(",")))
    state = load_state()
    if os.environ.get("FRESH_START") == "true":
        # Search rules changed: forget earlier verdicts so every posting is judged again (backup stays in Blob history).
        log(f"fresh start: clearing {len(state['jobs'])} board entries and {len(state['seen'])} seen ids")
        state = {**state, "jobs": [], "seen": {}}
    # Entries that could not be checked (model overloaded) leave the board and are collected and checked again.
    # Entries without a requirement check (no description) are dropped for good: nothing to verify against the CV.
    unchecked = [j for j in state["jobs"] if j["match"].get("summary", "").startswith("Nicht automatisch geprüft")]
    for j in unchecked:
        if not j.get("description"):
            state["seen"][j["id"]] = now_day()
    excl_title = [w.lower() for w in cfg.get("exclude_title", [])]
    state["jobs"] = [j for j in state["jobs"] if j not in unchecked and matcher_loc_ok(cfg, j)
                     and not any(w in j.get("title", "").lower() for w in excl_title)]  # rules can get stricter
    first_run = not state["jobs"] and not state["seen"]
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    seen: dict[str, str] = state["seen"]
    known = {j["id"] for j in state["jobs"]} | set(seen)
    matcher = Matcher(cfg)
    started = now
    postings: list[dict] = []  # transparency log: every posting and what happened to it

    def note(j: Job, outcome: str, reason: str = "", score: int | None = None) -> None:
        postings.append({"title": j.title[:200], "org": j.org[:120], "location": j.location[:120], "url": j.url,
                         "source": j.source, "outcome": outcome, "reason": reason[:240],
                         **({"score": score} if score is not None else {})})
    if not matcher.client:
        log("WARNING: LLM key or PROFILE_JSON missing, requirement check disabled")

    collected: list[Job] = []
    failed: list[str] = []

    def run(name, fn):
        if only and name not in only:
            return
        log(f"[{name}]")
        try:
            res = fn()
            if isinstance(res, tuple):
                res, nfail = res
                if nfail:
                    failed.extend([name] * nfail)
            log(f"  -> {len(res)} postings")
            collected.extend(res)
        except Exception as e:  # noqa: BLE001
            log(f"  source failed ({type(e).__name__}: {str(e)[:120]})")
            failed.append(name)

    cro_queries = list(cfg["jobspy"]["queries"])  # CRO feeds: research terms only
    cfg["jobspy"]["queries"] = all_jobspy_queries(cfg)
    if cfg["bundesagentur"]["enabled"]:
        run("bundesagentur", lambda: bundesagentur.fetch(cfg, all_queries(cfg), first_run))
    if cfg["jobspy"]["enabled"]:
        run("jobspy", lambda: jobspy_boards.fetch(cfg))
    run("ats", lambda: ats.fetch(cfg, cro_queries))
    run("sites", lambda: sites.fetch(cfg, matcher.is_wanted, known))

    # Dedup: by URL id, and by title+organisation across boards.
    fuzzy_known = {j.get("fuzzy") for j in state["jobs"]} | {k for k in seen if k.startswith("f:")}
    fresh: dict[str, Job] = {}
    fresh_fuzzy: set[str] = set()
    for j in collected:
        if j.id in known or ("f:" + j.fuzzy_key) in fuzzy_known:
            note(j, "known", "in einem früheren Lauf bereits bewertet")
            continue
        if j.id in fresh or j.fuzzy_key in fresh_fuzzy:
            note(j, "duplicate", "in diesem Lauf schon aus einer anderen Quelle")
            continue
        fresh[j.id] = j
        fresh_fuzzy.add(j.fuzzy_key)
    log(f"collected {len(collected)}, new {len(fresh)}")

    # Cheap rules first.
    candidates = []
    dropped = 0
    reasons: dict[str, list[str]] = {"title": [], "location": [], "text": [], "no topic": []}
    for j in fresh.values():
        if not matcher.title_ok(j) or not matcher.location_ok(j):
            why = "title" if not matcher.title_ok(j) else "location"
            reasons[why].append(f"{j.title} | {j.location}")
            note(j, why, matcher.title_reason(j) if why == "title" else "Ort nicht in der Suchliste und nicht remote")
            seen[j.id] = today
            dropped += 1
            continue
        candidates.append(j)
    for j in candidates:
        bundesagentur.enrich(j)
        ats.enrich(j)
    log(bundesagentur.detail_stats())
    kept = []
    for j in candidates:
        if not matcher.text_ok(j) or matcher.prefilter_score(j) < cfg["matching"]["min_prefilter_score"]:
            why = "text" if not matcher.text_ok(j) else "no_topic"
            reasons["text" if why == "text" else "no topic"].append(j.title)
            note(j, why, matcher.text_reason(j) if why == "text" else "kein Begriff aus den Themen oder Suchbegriffen")
            seen[j.id] = today
            dropped += 1
        else:
            kept.append(j)
    for why, titles in reasons.items():
        # Job titles and places only (public posting data, no profile content).
        log(f"  dropped for {why}: {len(titles)}; e.g. {titles[:12]}")
    kept.sort(key=matcher.prefilter_score, reverse=True)
    # Pool for the local model on the laptop: public posting data only.
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "pool.json").write_text(json.dumps(
        {"created": now.isoformat(), "jobs": [{**j.to_dict(), "description": j.description[:14000]} for j in kept]},
        ensure_ascii=False))
    limit = cfg["matching"]["max_llm_checks_per_run"]
    log(f"rules dropped {dropped}, checking {min(len(kept), limit)} of {len(kept)}")

    new_entries = []
    counts = {"match": 0, "check": 0, "reject": 0}
    deferred = 0
    for j in kept[limit:]:
        note(j, "over_limit", f"mehr als {limit} Kandidaten, wird im nächsten Lauf geprüft", matcher.prefilter_score(j))
    budget = cfg["matching"].get("max_check_minutes", 60) * 60
    t0 = time.monotonic()
    for i, j in enumerate(kept[:limit]):
        if i and i % 20 == 0:
            log(f"  checked {i} of {min(len(kept), limit)} in {int(time.monotonic() - t0)} s")
        if time.monotonic() - t0 > budget:
            deferred += 1  # time budget: leave room to save results before the job timeout
            note(j, "deferred", "Zeitbudget des Laufs erreicht, nächster Lauf", matcher.prefilter_score(j))
            continue
        if matcher.client and matcher.exhausted:
            deferred += 1  # not recorded: checked again on the next run
            note(j, "deferred", "Gemini-Tageskontingent aufgebraucht, nächster Lauf")
            continue
        if not j.description:
            seen[j.id] = today  # nothing to check the requirements against: never shown
            note(j, "text", "keine Beschreibung, Anforderungen nicht prüfbar")
            continue
        result = matcher.check(j)
        if result is None and j.description and matcher.client:
            deferred += 1  # quota used up or model overloaded: not recorded, checked again next run
            note(j, "deferred", "Gemini-Tageskontingent aufgebraucht, nächster Lauf" if matcher.exhausted
                 else "Prüfung fehlgeschlagen (Gemini überlastet), nächster Lauf")
            continue
        m = decide(j, result, matcher)
        counts[m["status"]] += 1
        note(j, m["status"], m.get("reject_reason") or ", ".join(m.get("notes") or []) or m.get("summary", ""), m["score"])
        if m["status"] == "reject":
            seen[j.id] = today
            seen["f:" + j.fuzzy_key] = today
            continue
        entry = j.to_dict()
        entry["description"] = j.description[:4000]
        entry["fuzzy"] = "f:" + j.fuzzy_key
        entry["first_seen"] = now.isoformat()
        entry["match"] = m
        new_entries.append(entry)
    why_reject = Counter(p["reason"].split(";")[0].split(":")[0].split("(")[0].strip()
                         for p in postings if p["outcome"] == "reject")
    log(f"reject reasons (first rule hit): {dict(why_reject.most_common())}")
    log(f"result: {counts['match']} match, {counts['check']} check, {counts['reject']} reject, {deferred} deferred to next run")

    # Keep recent entries, forget old ones.
    cutoff = (now - timedelta(days=cfg["keep_days"])).isoformat()
    jobs = [j for j in state["jobs"] if j.get("first_seen", "") >= cutoff
            and not ("" < (j["match"].get("deadline") or "") < today)] + new_entries  # drop passed deadlines
    for j in jobs:  # entries from before the language field existed
        if "languages" not in j["match"]:
            j["match"]["languages"] = languages_from_text(j.get("description", ""))
    seen = {k: v for k, v in seen.items() if v >= cutoff[:10]}
    # Board summary: public posting data only (title, employer, place, verdict), never profile content.
    for j in sorted(jobs, key=lambda x: (x["match"]["status"] != "match", -x["match"]["score"])):
        mm = j["match"]
        log(f"  board {mm['status']:5} {mm['score']:3} | {j['title'][:90]} | {j['org'][:50]} | {j['location'][:40]}"
            f" | {mm.get('role', '')} | {', '.join(mm.get('notes') or [])}")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"version": 1, "updated": now.isoformat(), "jobs": jobs, "seen": seen,
                                 "last_run": {"collected": len(collected), "new": len(fresh), **counts,
                                              "failed_sources": len(failed)}},
                                ensure_ascii=False))

    # Transparency log for the "Läufe" page.
    runs = json.loads(RUNS.read_text()) if RUNS.exists() and RUNS.stat().st_size else []
    finished = datetime.now(timezone.utc)
    runs.insert(0, {
        "id": started.strftime("%Y%m%d-%H%M%S"),
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "seconds": int((finished - started).total_seconds()),
        "trigger": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "run_url": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                    if os.environ.get("GITHUB_RUN_ID") else ""),
        "llm": {"provider": matcher.provider, "models": getattr(matcher, "used_models", []), "checked": sum(counts.values()),
                "limit": limit},
        "counts": {"collected": len(collected), "new": len(fresh), "dropped": dropped, "candidates": len(kept),
                   "deferred": deferred, **counts, "failed_sources": len(failed)},
        "sources": report.SOURCES,
        "postings": postings,
    })
    RUNS.write_text(json.dumps(runs[:KEEP_RUNS], ensure_ascii=False))

    # Tell the workflow whether a catch-up run is worth it: postings left unchecked
    # because Gemini was overloaded, the time budget ran out or the check limit was hit.
    backlog = deferred + max(0, len(kept) - limit)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"backlog={backlog}\nquota_exhausted={'true' if matcher.exhausted else 'false'}\n")
    log(f"backlog for catch-up: {backlog} (quota exhausted: {matcher.exhausted})")

    if os.environ.get("NOTIFY", "1") == "1":
        notify.send_matches(new_entries, cfg)
        if len(failed) > cfg["notify"]["max_failed_sources"]:
            notify.send_alert(f"{len(failed)} Quellen sind fehlgeschlagen: {', '.join(sorted(set(failed)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
