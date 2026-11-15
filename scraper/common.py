"""Shared job model and helpers."""
from __future__ import annotations

import hashlib
import html
import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 job-search-medical/1.0"
)
HTTP = requests.Session()
HTTP.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"})

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "from", "trk"}


@dataclass
class Job:
    title: str
    org: str
    location: str
    url: str
    source: str
    description: str = ""
    posted: str = ""
    remote: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        key = normalize_url(self.url) if self.url else f"{norm(self.title)}|{norm(self.org)}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    @property
    def fuzzy_key(self) -> str:
        """Same posting seen on two boards: same title + organisation."""
        return hashlib.sha1(f"{norm(self.title)}|{norm(self.org)[:20]}".encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\((m|w|d|f|x|div|gn)[/|,\s\w]*\)", " ", s)
    s = re.sub(r"[^a-z0-9äöüß]+", " ", s)
    return " ".join(s.split())


def normalize_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(q), ""))
    except ValueError:
        return url.strip()


def clean_text(s: str, limit: int = 15000) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()[:limit]


def get_json(url: str, *, headers: dict | None = None, params: dict | None = None,
             method: str = "GET", body: dict | None = None, timeout: int = 30, retries: int = 2):
    last = None
    for attempt in range(retries + 1):
        try:
            r = HTTP.request(method, url, headers=headers, params=params, json=body, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:  # ValueError: bad JSON
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def get_text(url: str, timeout: int = 30) -> str:
    r = HTTP.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def log(msg: str) -> None:
    """Logs are public in a public repo: never log profile content."""
    print(msg, flush=True)
