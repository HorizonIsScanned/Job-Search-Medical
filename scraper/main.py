"""Daily run: collect postings, filter, check requirements, store, notify.

State (data/state.json) is downloaded from and uploaded to a private Vercel
Blob store by scripts/blob.mjs; it is never committed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from common import Job, log  # noqa: E402
from match import Matcher, decide  # noqa: E402
import notify  # noqa: E402
from sources import ats, bundesagentur, jobspy_boards, sites  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"


def load_state() -> dict:
    if STATE.exists() and STATE.stat().st_size:
        return json.loads(STATE.read_text())
    return {"version": 1, "jobs": [], "seen": {}}


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "search.yaml").read_text())
    only = set(filter(None, os.environ.get("ONLY_SOURCES", "").split(",")))
    state = load_state()
    first_run = not state["jobs"] and not state["seen"]
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    seen: dict[str, str] = state["seen"]
    known = {j["id"] for j in state["jobs"]} | set(seen)
    matcher = Matcher(cfg)
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

    if cfg["bundesagentur"]["enabled"]:
        run("bundesagentur", lambda: bundesagentur.fetch(cfg, cfg["queries"], first_run))
    if cfg["jobspy"]["enabled"]:
        run("jobspy", lambda: jobspy_boards.fetch(cfg))
    run("ats", lambda: ats.fetch(cfg, cfg["jobspy"]["queries"]))
    run("sites", lambda: sites.fetch(cfg, matcher.is_wanted, known))

    # Dedup: by URL id, and by title+organisation across boards.
    fuzzy_known = {j.get("fuzzy") for j in state["jobs"]} | {k for k in seen if k.startswith("f:")}
    fresh: dict[str, Job] = {}
    fresh_fuzzy: set[str] = set()
    for j in collected:
        if j.id in known or j.id in fresh or ("f:" + j.fuzzy_key) in fuzzy_known or j.fuzzy_key in fresh_fuzzy:
            continue
        fresh[j.id] = j
        fresh_fuzzy.add(j.fuzzy_key)
    log(f"collected {len(collected)}, new {len(fresh)}")

    # Cheap rules first.
    candidates = []
    dropped = 0
    for j in fresh.values():
        if not (matcher.title_ok(j) and matcher.location_ok(j)):
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
            seen[j.id] = today
            dropped += 1
        else:
            kept.append(j)
    kept.sort(key=matcher.prefilter_score, reverse=True)
    limit = cfg["matching"]["max_llm_checks_per_run"]
    log(f"rules dropped {dropped}, checking {min(len(kept), limit)} of {len(kept)}")

    new_entries = []
    counts = {"match": 0, "check": 0, "reject": 0}
    deferred = 0
    for j in kept[:limit]:
        if matcher.client and matcher.exhausted:
            deferred += 1  # not recorded: checked again on the next run
            continue
        result = matcher.check(j) if j.description else None
        if result is None and j.description and matcher.client and matcher.exhausted:
            deferred += 1
            continue
        m = decide(j, result, matcher)
        counts[m["status"]] += 1
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
    log(f"result: {counts['match']} match, {counts['check']} check, {counts['reject']} reject, {deferred} deferred to next run")

    # Keep recent entries, forget old ones.
    cutoff = (now - timedelta(days=cfg["keep_days"])).isoformat()
    jobs = [j for j in state["jobs"] if j.get("first_seen", "") >= cutoff] + new_entries
    seen = {k: v for k, v in seen.items() if v >= cutoff[:10]}
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"version": 1, "updated": now.isoformat(), "jobs": jobs, "seen": seen,
                                 "last_run": {"collected": len(collected), "new": len(fresh), **counts,
                                              "failed_sources": len(failed)}},
                                ensure_ascii=False))

    if os.environ.get("NOTIFY", "1") == "1":
        notify.send_matches(new_entries, cfg)
        if len(failed) > cfg["notify"]["max_failed_sources"]:
            notify.send_alert(f"{len(failed)} Quellen sind fehlgeschlagen: {', '.join(sorted(set(failed)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
