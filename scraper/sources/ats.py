"""Public feeds of applicant tracking systems (Workday, Personio, Greenhouse, Lever).

Idea from https://github.com/riley-dorrington/job-board-aggregator: many
employers expose their career page as JSON/XML, which is stabler than HTML.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from common import Job, clean_text, get_json, get_text, log


def _workday(e: dict, queries: list[str]) -> list[Job]:
    base = f"https://{e['host']}/wday/cxs/{e['tenant']}/{e['site']}"
    seen: dict[str, Job] = {}
    for q in queries:
        data = get_json(f"{base}/jobs", method="POST",
                        body={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": q},
                        headers={"Content-Type": "application/json", "Accept": "application/json"})
        for p in data.get("jobPostings") or []:
            path = p.get("externalPath", "")
            url = f"https://{e['host']}/{e['site']}{path}"
            j = Job(title=p.get("title", ""), org=e["name"], location=p.get("locationsText", ""),
                    url=url, source=e["name"], posted=p.get("postedOn", ""), extra={"wd_path": path, "wd_base": base})
            seen.setdefault(j.id, j)
    return list(seen.values())


def _workday_detail(job: Job) -> None:
    try:
        d = get_json(f"{job.extra['wd_base']}{job.extra['wd_path']}", retries=0)
        info = d.get("jobPostingInfo") or {}
        job.description = clean_text(info.get("jobDescription", ""))
        job.remote = "remote" in (info.get("remoteType") or "").lower() or job.remote
        job.location = info.get("location") or job.location
    except Exception:  # noqa: BLE001
        pass


def _personio(e: dict) -> list[Job]:
    root = ET.fromstring(get_text(f"https://{e['id']}.jobs.personio.de/xml"))
    out = []
    for pos in root.findall("position"):
        pid = pos.findtext("id", "")
        desc = " ".join(clean_text(v.findtext("value", "")) for v in pos.iter("jobDescription"))
        out.append(Job(title=pos.findtext("name", ""), org=e["name"], location=pos.findtext("office", ""),
                       url=f"https://{e['id']}.jobs.personio.de/job/{pid}", source=e["name"],
                       description=desc, posted=pos.findtext("createdAt", "")))
    return out


def _greenhouse(e: dict) -> list[Job]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{e['id']}/jobs", params={"content": "true"})
    return [Job(title=p.get("title", ""), org=e["name"], location=(p.get("location") or {}).get("name", ""),
                url=p.get("absolute_url", ""), source=e["name"], description=clean_text(p.get("content", "")),
                posted=p.get("updated_at", "")) for p in data.get("jobs", [])]


def _lever(e: dict) -> list[Job]:
    data = get_json(f"https://api.lever.co/v0/postings/{e['id']}", params={"mode": "json"})
    return [Job(title=p.get("text", ""), org=e["name"], location=(p.get("categories") or {}).get("location", ""),
                url=p.get("hostedUrl", ""), source=e["name"],
                description=clean_text((p.get("descriptionPlain") or "") + " " + " ".join(
                    clean_text(l.get("content", "")) for l in p.get("lists", []))),
                remote="remote" in (p.get("workplaceType") or "").lower()) for p in data]


def fetch(cfg: dict, queries: list[str]) -> tuple[list[Job], int]:
    jobs: list[Job] = []
    failed = 0
    for e in cfg.get("ats") or []:
        try:
            t = e["type"]
            if t == "workday":
                got = _workday(e, queries)
            elif t == "personio":
                got = _personio(e)
            elif t == "greenhouse":
                got = _greenhouse(e)
            elif t == "lever":
                got = _lever(e)
            else:
                continue
            log(f"  {e['name']}: {len(got)} postings")
            jobs += got
        except Exception as ex:  # noqa: BLE001
            log(f"  {e['name']}: feed failed ({type(ex).__name__})")
            failed += 1
    return jobs, failed


def enrich(job: Job) -> None:
    if "wd_path" in job.extra and not job.description:
        _workday_detail(job)
