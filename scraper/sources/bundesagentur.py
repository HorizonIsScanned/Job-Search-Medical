"""Bundesagentur für Arbeit Jobsuche (community-documented REST API).

Docs: https://github.com/bundesAPI/jobsuche-api
"""
from __future__ import annotations

import base64
import time

from common import Job, clean_text, get_json, log
import report

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}


_DEBUGGED = False


def _search(params: dict) -> list[dict]:
    global _DEBUGGED
    last: Exception | None = None
    for version in ("v6",):
        try:
            data = get_json(f"{BASE}/pc/{version}/jobs", headers=HEADERS, params=params, retries=3)
        except Exception as e:  # noqa: BLE001
            last = e
            continue
        items = data.get("ergebnisliste") or data.get("stellenangebote") or []
        if items and not _DEBUGGED:
            _DEBUGGED = True
            first = items[0]
            loc = (first.get("stellenlokationen") or [{}])[0]
            log(f"  BA location fields: {sorted(loc)} / {sorted((loc or {}).get('adresse') or {})}")
        return items
    if last:
        raise last
    return []


def _details(refnr: str) -> str:
    enc = base64.b64encode(refnr.encode()).decode()
    for path in (f"pc/v4/jobdetails/{enc}", f"pc/v3/jobdetails/{enc}"):
        try:
            d = get_json(f"{BASE}/{path}", headers=HEADERS, retries=0)
            return clean_text(d.get("stellenangebotsBeschreibung") or d.get("stellenbeschreibung") or "")
        except Exception as e:  # noqa: BLE001
            if not _DETAIL_STATS.get("logged"):
                _DETAIL_STATS["logged"] = 1
                log(f"  BA detail {path.split('/')[1]} failed ({type(e).__name__}: {str(e)[:60]})")
            continue
    return ""


def fetch(cfg: dict, queries: list[str], first_run: bool) -> list[Job]:
    bcfg = cfg["bundesagentur"]
    days = bcfg["first_run_days"] if first_run else bcfg["days"]
    jobs: dict[str, Job] = {}
    for city in bcfg["cities"]:
        before, failed_q = len(jobs), 0
        for q in queries:
            params = {
                "was": q, "wo": city, "umkreis": bcfg["radius_km"],
                "veroeffentlichtseit": days, "size": bcfg["size"], "page": 1,
                "angebotsart": 1,
            }
            try:
                items = _search(params)
            except Exception as e:  # noqa: BLE001
                log(f"  BA query failed ({type(e).__name__}: {str(e)[:80]})")
                failed_q += 1
                continue
            for it in items:
                refnr = it.get("refnr") or it.get("referenznummer") or ""
                if not refnr:
                    continue
                locs = it.get("stellenlokationen") or [it.get("arbeitsort") or {}]
                parts = []
                for loc in locs[:3]:
                    a = (loc or {}).get("adresse") or loc or {}
                    parts.append(" ".join(str(a.get(k)) for k in ("plz", "ort", "land") if a.get(k)))
                url = (it.get("externeURL") or it.get("externeUrl")
                       or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}")
                parttime = any(it.get(k) for k in ("arbeitszeitTeilzeitFlexibel", "arbeitszeitTeilzeitVormittag",
                                                   "arbeitszeitTeilzeitNachmittag", "arbeitszeitTeilzeitAbend"))
                job = Job(
                    title=(it.get("stellenangebotsTitel") or it.get("titel") or it.get("hauptberuf") or it.get("beruf") or ""),
                    org=it.get("firma") or it.get("arbeitgeber") or "",
                    location="; ".join(x for x in parts if x),
                    url=url,
                    source="Bundesagentur",
                    posted=it.get("datumErsteVeroeffentlichung") or it.get("aktuelleVeroeffentlichungsdatum") or "",
                    remote=bool(it.get("homeofficemoeglich")),
                    extra={"refnr": refnr, "teilzeit": parttime},
                )
                jobs.setdefault(job.id, job)
            time.sleep(1.0)
        report.source("Bundesagentur", f"Jobsuche {city}", f"https://www.arbeitsagentur.de/jobsuche/suche?wo={city}",
                      len(jobs) - before, "failed" if failed_q == len(queries) else "ok",
                      f"{len(queries)} Suchbegriffe, {bcfg['radius_km']} km, letzte {days} Tage"
                      + (f", {failed_q} Anfragen fehlgeschlagen" if failed_q else ""))
    return list(jobs.values())


_DETAIL_STATS = {"ok": 0, "empty": 0}


def enrich(job: Job) -> None:
    """Fetch the full description only for postings that survive the prefilter."""
    refnr = job.extra.get("refnr")
    if refnr and not job.description:
        job.description = _details(refnr)
        _DETAIL_STATS["ok" if job.description else "empty"] += 1


def detail_stats() -> str:
    return f"BA details: {_DETAIL_STATS['ok']} with text, {_DETAIL_STATS['empty']} empty"
