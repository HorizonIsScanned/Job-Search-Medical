"""Indeed, Google Jobs and LinkedIn via JobSpy (https://github.com/speedyapply/JobSpy).

Runs once a day at low volume and without proxy rotation.
"""
from __future__ import annotations

import math

from common import Job, clean_text, log
import report


def _val(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v)


def fetch(cfg: dict) -> list[Job]:
    from jobspy import scrape_jobs  # heavy import

    jcfg = cfg["jobspy"]
    jobs: dict[str, Job] = {}
    for place in jcfg["places"]:
        per_site = {s: 0 for s in jcfg["sites"]}
        failed_q = 0
        for q in jcfg["queries"]:
            try:
                df = scrape_jobs(
                    site_name=jcfg["sites"],
                    search_term=q,
                    google_search_term=f"{q} jobs near {place['location']} since last week",
                    location=place["location"],
                    country_indeed=place["country"],
                    results_wanted=jcfg["results_wanted"],
                    hours_old=jcfg["hours_old"],
                    linkedin_fetch_description=True,
                    is_remote=bool(place.get("remote")),
                    description_format="markdown",
                    verbose=0,
                )
            except Exception as e:  # noqa: BLE001
                log(f"  JobSpy query failed ({type(e).__name__})")
                failed_q += 1
                continue
            for row in df.to_dict("records"):
                job = Job(
                    title=_val(row.get("title")),
                    org=_val(row.get("company")),
                    location=_val(row.get("location")) or place["location"],
                    url=_val(row.get("job_url_direct")) or _val(row.get("job_url")),
                    source=_val(row.get("site")).capitalize() or "JobSpy",
                    description=clean_text(_val(row.get("description"))),
                    posted=_val(row.get("date_posted")),
                    remote=bool(place.get("remote")) or (bool(row.get("is_remote")) if _val(row.get("is_remote")) else False),
                )
                if job.title and job.url and job.id not in jobs:
                    jobs[job.id] = job
                    site = _val(row.get("site")).lower()
                    per_site[site] = per_site.get(site, 0) + 1
        where = "Remote" if place.get("remote") else place["location"]
        for site, n in per_site.items():
            report.source("Jobbörsen (JobSpy)", f"{site.capitalize()} {where}", "", n,
                          "failed" if failed_q == len(jcfg["queries"]) else "ok",
                          f"{len(jcfg['queries'])} Suchbegriffe" + (f", {failed_q} fehlgeschlagen" if failed_q else ""))
    return list(jobs.values())
