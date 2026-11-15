# Job Search Medical

A daily job board for a medical graduate looking for a PhD position or a
part-time role (~20 h/week) that uses medical knowledge. Focus areas: women's
health, imaging, neurology, ophthalmology.

Every morning a GitHub Actions cron job collects new postings, drops those
whose **required** qualifications the candidate does not meet, and pushes the
best new matches via [ntfy](https://ntfy.sh). Results are shown on a
password-protected Next.js page on Vercel.

**This repository is public and contains no personal data.** The candidate
profile, the results and all tokens live in GitHub/Vercel secrets and a
private Vercel Blob store. `scripts/pii_check.py` fails the build if names,
e-mail addresses or phone numbers show up in tracked files.

## How it works

```
GitHub Actions (cron, daily)
  ├─ load state from private Vercel Blob  (scripts/blob.mjs get)
  ├─ collect postings                     (scraper/sources/*)
  │    ├─ Bundesagentur Jobsuche API      bundesagentur.py
  │    ├─ Indeed, Google Jobs, LinkedIn   jobspy_boards.py  (JobSpy)
  │    ├─ ATS feeds (Workday, Personio, Greenhouse, Lever)  ats.py
  │    └─ career pages + niche boards     sites.py  (crawl4ai, JSON-LD JobPosting)
  ├─ dedup (URL, then title + employer)
  ├─ rules: excluded titles, locations, licence/C1 phrases, topic words
  ├─ strict requirement check with Claude  (scraper/match.py)
  │    every requirement → met / unmet / unclear against the profile
  │    any required item unmet → dropped · any unclear → "Prüfen" list
  ├─ save state to Blob                   (scripts/blob.mjs put)
  └─ ntfy push for new matches with score ≥ 60
Vercel (Next.js) ── reads the Blob, shows "Passt" and "Prüfen" lists
```

Search terms, locations, topic weights, sources and thresholds are in
[`config/search.yaml`](config/search.yaml).

## Secrets

GitHub → Settings → Secrets and variables → Actions:

| Name | What |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude API key for the requirement check |
| `PROFILE_JSON` | Candidate profile as JSON (see `examples/profile.example.json`) |
| `BLOB_READ_WRITE_TOKEN` | Token of the private Vercel Blob store |
| `NTFY_TOPIC` | Random ntfy topic for the daily push |
| `NTFY_ALERT_TOPIC` | Optional: separate topic for failure alerts |
| `PII_PATTERNS` | Comma-separated strings that must never appear in the repo |
| variable `BOARD_URL` | URL of the board, used as click target in the push |

Vercel project environment: `BLOB_READ_WRITE_TOKEN` (set by connecting the
Blob store), `BOARD_PASSWORD`, `BOARD_TITLE`.

## Run by hand

Actions → *Daily job search* → *Run workflow*. Options: switch off the push,
or run only some sources (`bundesagentur,jobspy,ats,sites`).

## Notes

- Sources are read once a day at low volume, without proxy rotation;
  crawl4ai respects robots.txt. LinkedIn, Indeed and Glassdoor restrict
  automated access in their terms; remove them from `jobspy.sites` if that
  matters to you.
- The board keeps postings for 60 days.
