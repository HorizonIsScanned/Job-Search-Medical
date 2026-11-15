"""Bundesagentur für Arbeit Jobsuche (community-documented REST API).

Docs: https://github.com/bundesAPI/jobsuche-api
"""
from __future__ import annotations

import base64
import time

from common import Job, clean_text, get_json, log

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
            log(f"  BA item fields: {sorted(first)}; arbeitsort: {sorted(first.get('arbeitsort') or (first.get('arbeitsorte') or [{}])[0])}")
        return items
    if last:
        raise last
    return []


def _details(refnr: str) -> str:
    enc = base64.b64encode(refnr.encode()).decode()
    for path in (f"pc/v4/jobdetails/{enc}", f"pc/v2/jobdetails/{enc}"):
        try:
            d = get_json(f"{BASE}/{path}", headers=HEADERS, retries=0)
            return clean_text(d.get("stellenbeschreibung") or d.get("stellenangebotsBeschreibung") or "")
        except Exception:  # noqa: BLE001
            continue
    return ""


def fetch(cfg: dict, queries: list[str], first_run: bool) -> list[Job]:
    bcfg = cfg["bundesagentur"]
    days = bcfg["first_run_days"] if first_run else bcfg["days"]
    jobs: dict[str, Job] = {}
    for city in bcfg["cities"]:
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
                continue
            for it in items:
                refnr = it.get("refnr") or it.get("referenznummer") or ""
                if not refnr:
                    continue
                ort = it.get("arbeitsort") or (it.get("arbeitsorte") or [{}])[0] or {}
                url = it.get("externeUrl") or f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
                job = Job(
                    title=(it.get("titel") or it.get("stellenangebotsTitel") or it.get("stellenbezeichnung")
                           or it.get("beruf") or ""),
                    org=it.get("arbeitgeber") or it.get("arbeitgeberName") or it.get("firma") or "",
                    location=" ".join(x for x in (ort.get("plz"), ort.get("ort"), ort.get("land")) if x),
                    url=url,
                    source="Bundesagentur",
                    posted=it.get("aktuelleVeroeffentlichungsdatum") or it.get("eintrittsdatum") or "",
                    extra={"refnr": refnr},
                )
                jobs.setdefault(job.id, job)
            time.sleep(1.0)
    return list(jobs.values())


def enrich(job: Job) -> None:
    """Fetch the full description only for postings that survive the prefilter."""
    refnr = job.extra.get("refnr")
    if refnr and not job.description:
        job.description = _details(refnr)
