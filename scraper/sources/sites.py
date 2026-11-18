"""Career pages and niche boards via crawl4ai (https://github.com/unclecode/crawl4ai).

Listing page -> links that look like postings -> each new posting is read
from its schema.org/JobPosting JSON-LD, or as cleaned markdown if it has none.
robots.txt is respected (check_robots_txt=True).
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urljoin

from common import USER_AGENT, Job, clean_text, log, normalize_url
import report

JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _walk(obj):
    if isinstance(obj, list):
        for o in obj:
            yield from _walk(o)
    elif isinstance(obj, dict):
        yield obj
        for k in ("@graph", "itemListElement", "item"):
            if k in obj:
                yield from _walk(obj[k])


def job_postings_from_html(html: str) -> list[dict]:
    out = []
    for raw in JSONLD_RE.findall(html or ""):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for o in _walk(data):
            t = o.get("@type")
            if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                out.append(o)
    return out


def _place(p: dict) -> str:
    locs = p.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    parts = []
    for loc in locs:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            parts.append(addr)
        else:
            parts.append(" ".join(str(addr.get(k, "")) for k in ("postalCode", "addressLocality", "addressCountry") if addr.get(k)))
    return "; ".join(x for x in parts if x)


def job_from_posting(p: dict, url: str, source: str, default_org: str, default_loc: str) -> Job:
    org = p.get("hiringOrganization") or {}
    org_name = org.get("name") if isinstance(org, dict) else str(org)
    remote = str(p.get("jobLocationType", "")).upper() == "TELECOMMUTE"
    desc = clean_text(" ".join(str(p.get(k, "")) for k in ("description", "qualifications", "skills", "responsibilities", "educationRequirements", "experienceRequirements")))
    emp = p.get("employmentType")
    return Job(
        title=clean_text(p.get("title", ""), 300),
        org=org_name or default_org,
        location=_place(p) or default_loc,
        url=p.get("url") or url,
        source=source,
        description=desc,
        posted=str(p.get("datePosted", "")),
        remote=remote,
        extra={"employmentType": emp} if emp else {},
    )


async def _crawl(crawler, url: str, js: bool = False):
    from crawl4ai import CacheMode, CrawlerRunConfig

    cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=45000,
        wait_until="networkidle" if js else "domcontentloaded",
        delay_before_return_html=5.0 if js else 2.0,
        scan_full_page=js,
        check_robots_txt=True,
        excluded_tags=["nav", "footer", "header", "aside"],
        word_count_threshold=5,
    )
    res = await crawler.arun(url, config=cfg)
    if not res.success:
        raise RuntimeError(res.error_message or f"HTTP {res.status_code}")
    return res


def _markdown(res) -> str:
    md = getattr(res, "markdown", "") or ""
    md = getattr(md, "fit_markdown", None) or getattr(md, "raw_markdown", None) or str(md)
    return clean_text(md)


def _title_from_markdown(md: str) -> str:
    for line in md.splitlines():
        line = line.strip().lstrip("#").strip()
        if 8 <= len(line) <= 200:
            return line
    return ""


async def _run(sites: list[dict], is_wanted, known_ids: set[str], max_details: int) -> tuple[list[Job], int]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    jobs: list[Job] = []
    failed = 0
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, user_agent=USER_AGENT, verbose=False)) as crawler:
        for site in sites:
            name = site["name"]
            try:
                res = await _crawl(crawler, site["url"], bool(site.get("js")))
            except Exception as e:  # noqa: BLE001
                log(f"  {name}: listing failed ({type(e).__name__}: {str(e)[:100]})")
                report.source("Karriereseiten", name, site["url"], 0, "failed", f"{type(e).__name__}: {str(e)[:100]}")
                failed += 1
                continue
            # 1) Listing page may already carry full JobPosting JSON-LD.
            postings = job_postings_from_html(res.html)
            for p in postings:
                j = job_from_posting(p, site["url"], name, name, site.get("location", ""))
                if j.title:
                    jobs.append(j)
            # 2) Otherwise follow links that look like postings.
            pat = re.compile(site.get("link_pattern") or r"job|stelle|position|vacanc|karriere", re.I)
            links = {}
            for group in ("internal", "external"):
                for lk in (res.links or {}).get(group, []):
                    href = urljoin(site["url"], lk.get("href", ""))
                    text = clean_text(lk.get("text", ""), 300)
                    if pat.search(href) and normalize_url(href) != normalize_url(site["url"]):
                        links.setdefault(normalize_url(href), text)
            if not links and not postings:
                sample = [lk.get("href", "") for lk in (res.links or {}).get("internal", [])][:15]
                log(f"  {name}: no posting links, sample: {sample}")
            n = 0
            start = len(jobs)
            skip_known = skip_title = 0
            for href, text in links.items():
                probe = Job(title=text, org=name, location=site.get("location", ""), url=href, source=name)
                if probe.id in known_ids:
                    skip_known += 1
                    continue
                if text and not is_wanted(probe):
                    skip_title += 1
                    continue
                if n >= max_details:
                    break
                n += 1
                try:
                    d = await _crawl(crawler, href)
                except Exception:  # noqa: BLE001
                    continue
                ps = job_postings_from_html(d.html)
                if ps:
                    j = job_from_posting(ps[0], href, name, name, site.get("location", ""))
                    j.url = href
                else:
                    md = _markdown(d)
                    j = Job(title=text or _title_from_markdown(md), org=name, location=site.get("location", ""),
                            url=href, source=name, description=md)
                if j.title:
                    jobs.append(j)
            log(f"  {name}: {len(postings)} JSON-LD, {len(links)} links, {n} details read")
            report.source("Karriereseiten", name, site["url"], len(jobs) - start + len(postings),
                          note=f"{len(links)} Links erkannt, {skip_known} schon bekannt, {skip_title} per Titel aussortiert, {n} gelesen"
                          + (", JSON-LD auf der Übersicht" if postings else ""))
    return jobs, failed


def fetch(cfg: dict, is_wanted, known_ids: set[str], max_details: int = 25) -> tuple[list[Job], int]:
    return asyncio.run(_run(cfg.get("sites") or [], is_wanted, known_ids, max_details))
