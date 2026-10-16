# Submission

Everything Builderr asks for in the submission email, in one place.

## Install step and run command

Needs Python 3.11+ (Windows, macOS or Linux). In an empty virtual environment, from the repository folder:

```bash
pip install -r requirements.txt
```

```bash
python scripts/run_competition_batch.py INPUT_FILE
```

Writes `out/envelopes.jsonl` (exactly one result per unique input, in input order), `out/report.json` and `out/report.html`; exit code 0 when the contract check passes. The agent researches only the organisation numbers in `INPUT_FILE`, live, at run time. Optional: `--bulk REGISTRY_SNAPSHOT` (identity anchor; missing companies are looked up live), `--previous OLD_ENVELOPES.jsonl` (refresh diff), `--deadline-seconds N` (default 3000; set a little below the run's time budget). All dependencies install from prebuilt, pinned packages; nothing is compiled. With uv: `uv sync --frozen` then `uv run python scripts/run_competition_batch.py INPUT_FILE`.

## 100-company smoke test

Files in [`smoke/`](smoke/):

- `smoke-companies.txt`: the 100 organisation numbers (from `select_entry_batch.py --count 100` on the public universe)
- `smoke-report.json`: run report
- `smoke-envelopes.jsonl`: one envelope per company
- `smoke-report.html`: browsable profiles with source links

Run `smoke-007`, 16 Oct 2026, on a laptop, live:

| | |
|---|---|
| Envelopes emitted | 100 of 100, validation passed, no timeouts |
| Companies with section available | annual accounts 100, leadership 100, workplaces 73, website 6, company profiles 2, activity 1, hiring 0 |
| Websites found by discovery | 4 (the registry listed a website for only 7 of the 100) |
| NAV job feed | loaded (9,408 active ads, last 45 days); none of the candidate ads belonged to these 100 companies |
| Time per company | p50 8.5 s, p95 59 s |
| Wall time | 316 s (research about 2 min; the rest is the one-off NAV feed read, which overlaps with research on bigger batches) |
| Requests | 906 |
| Third-party cost | $0 |

All six published websites were checked by hand against the registry name and address; no wrong-company matches were found.

Refresh check: rerunning the same 100 companies with `--previous smoke/smoke-envelopes.jsonl` produced 0 changes for all 100 companies (idempotent; run `smoke-007-refresh`).

The 100 companies are a random sample of the public universe and are mostly very small; most have no website or job ads to find. A second live run on 11 companies with a public footprint shows the external sources working:

## Live demo on companies with a public footprint

Files in [`demo/`](demo/) (`demo-companies.txt`, report, envelopes, `demo-report.html`). Run `demo-004`, same code:

| | |
|---|---|
| Envelopes emitted | 11 of 11, validation passed |
| Hiring | 5 of 11 companies, 29 postings: 12 from NAV for 4 companies (every employer org number checked against the registry: all are registered subunits of the company), 17 from AF Gruppen's own listings page |
| Dated activity | 3 of 11 (AF Gruppen 15 items, Kitron 6, Entra 2), each with its own publication date |
| Verified websites | 4 of 11; social profiles linked from them for all 4 |
| Withheld | DIPS (registry-linked site, but too little homepage text to confirm a one-word name), TGS (site timed out) |

Every job and news item in both runs was read by hand: no career info pages, files, logins, future dates or other companies' postings are published.

## Models, APIs and licences

- Models: none. No LLM is used; summaries are built deterministically from claims.
- APIs: Brønnøysundregistrene Enhetsregisteret and Regnskapsregisteret open APIs (no key), licensed under NLOD.
- NAV job vacancy feed (pam-stilling-feed.nav.no), official API, using the public token NAV publishes for everyone; NAV API terms (free, republishing allowed, only active ads are published). Ads are published only when NAV's record names our organisation number or a registered subunit.
- Web: company-owned websites only, robots.txt respected. No search APIs, no LinkedIn/Meta/Google/Glassdoor/Indeed.
- Secrets: none required. Optional `NAV_FEED_TOKEN` environment variable for a private NAV token.

Full details: [LIMITATIONS.md](LIMITATIONS.md).

## Expected cost per official batch

$0 third-party cost. Compute only.
