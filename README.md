# Signalpost Agent

Research any Norwegian company from its organisation number — with a source for every fact.

Give it a list of organisation numbers. For each company it returns one profile: what the company does, who leads it, where it operates, its latest filed accounts, whether it is hiring and what it has published recently. Every fact links to the page or register it came from, with the date it was retrieved. Anything it cannot tie to the exact company is left out and marked, never guessed. Run it again later and it reports what changed.

Built for the [Builderr Signalpost challenge](https://builderr.ai/challenges/signalpost).

## What it finds

- **Company record** — legal name, form, address, industry, registered employees (Brønnøysund register)
- **Filed accounts** — revenue, results, assets, equity and debt per year, with the reporting period (Regnskapsregisteret)
- **People and places** — board and management roles, registered workplaces, group relations
- **Website and profiles** — the company's verified website and the social profiles it links to
- **Hiring** — job postings from the company's own careers pages and from NAV's job board (matched by organisation number)
- **Activity** — dated news and press items from the company's own site
- **What changed** since the last run, and **what is unknown**

No API keys, no paid services, no LLM. Third-party cost: $0.

## Run it

Needs [Python 3.11 or newer](https://www.python.org/downloads/) (on Windows, tick **Add python.exe to PATH** when installing).

1. **Get the code:** `git clone https://github.com/lateshb/signalpost-agent.git` — or **Code → Download ZIP** on GitHub and unzip it.
2. **Start it:**
   - Windows: double-click **`run.bat`** (or type `run.bat` in Command Prompt, `.un.bat` in PowerShell)
   - macOS / Linux: `./run.sh`
3. **Look at the results:** the results page opens in your browser when the run finishes.

The first run sets up its own environment and installs everything (about a minute). It then researches 11 example companies (about 5 minutes) — swap in your own list with `run.bat my-companies.txt` or `./run.sh my-companies.txt` (one organisation number per line).

In the results page you can search, filter, tick **Compare** on 2–4 companies to see them side by side, and click any **source** link to check a fact.

## For evaluators: install step and run command

In an empty virtual environment, from the repository folder:

```bash
pip install -r requirements.txt
```

```bash
python scripts/run_competition_batch.py INPUT_FILE
```

- `INPUT_FILE`: plain text (one organisation number per line), JSON list or JSONL (`{"organisation_number": "..."}`). Bad or duplicate rows never crash the run.
- Writes `out/envelopes.jsonl` (exactly one result per unique input, in input order), `out/report.json` (run report and contract check) and `out/report.html` (results page). Exit code 0 when the contract check passes.
- Everything is installed from prebuilt packages with pinned versions; nothing is compiled. Works with Python 3.11+ on Windows, macOS and Linux.
- With uv instead of pip: `uv sync --frozen` then `uv run python scripts/run_competition_batch.py INPUT_FILE` (Python 3.12 and versions pinned in `uv.lock`).

Useful options (all optional):

| Option | Default | What it does |
|---|---|---|
| `--bulk REGISTRY_SNAPSHOT` | none | Brreg bulk CSV (plain or gzipped) as identity anchor; companies missing from it are looked up live |
| `--previous OLD_ENVELOPES.jsonl` | none | Refresh mode: report what changed since that run (the old file is only read) |
| `--deadline-seconds N` | 3000 | Hard stop: unfinished companies get a `failed` result and all files are written before this |
| `--workers N` | 24 | Companies researched in parallel |
| `--output`, `--report`, `--html`, `--run-id` | `out/…`, `run-<time>` | Output paths and run name |
| `--no-nav-jobs` | off | Skip NAV's job feed (about 4 minutes faster) |
| `--no-discovery` | off | Only use the website listed in the register |

Optional environment variable: `NAV_FEED_TOKEN` (a private token for NAV's job feed; without it the public token NAV publishes is used).

## Results

| Run | Result |
|---|---|
| [100-company smoke test](smoke/) (random companies from the public list) | 100/100 results, contract check passed, no timeouts, $0 |
| Refresh rerun of the same 100 | 0 false changes |
| [Demo](demo/) on 11 companies with a public footprint | hiring for 5 (29 postings), dated news for 3 (23 items), every item checked by hand |
| Clean install, exactly as Builderr checks | fresh clone, empty environment, one install step, run command: passes |

Details: [SUBMISSION.md](SUBMISSION.md). Requirement-by-requirement check against the challenge page: [COMPLIANCE.md](COMPLIANCE.md).

## Quality bar

- **The right company or nothing.** A website is published only if it shows the organisation number, or the full legal name (plus the registered address for sites we discovered ourselves). Parked domains, franchise brands, parent or sister companies are withheld as `ambiguous`.
- **Every fact has evidence:** source URL, retrieval time, content hash, the supporting text, and the reporting period for financial figures.
- **Missing is never zero.** A figure that is not in the filing is left out, not written as 0.
- **Jobs are real postings.** NAV ads only when NAV's record names our organisation number or a registered subunit; site links only when they point at one posting. Career info pages, PDFs, login links and other companies' postings are not jobs.
- **News has its own publication date.** Contact, service and index pages are not news; event dates and future dates are not publication dates.
- **One result per input, always** — including companies that crash, time out or are missing from the snapshot.
- **Refresh is honest.** Re-running the same data gives no changes; a source that fails keeps its last known values instead of looking like a change.

## How it works

1. **Identity:** the registry snapshot row, or the live register, anchors every company by organisation number.
2. **Official data:** live entity record, annual accounts, roles, group relations and registered workplaces (Brønnøysund open APIs).
3. **Website:** the site listed in the register; if there is none or it does not verify, the domain of the registered email address, then a few domains built from the legal name — each one must pass the identity gate.
4. **Crawl:** homepage, sitemap and up to 8 pages across about/contact, careers (job listings first), news, people and locations. Robots.txt is respected.
5. **Extract:** structured data (JSON-LD JobPosting/Article) first, then posting and news links with their own dates.
6. **NAV jobs:** while companies are researched, a background thread reads NAV's official job vacancy feed (last 45 days, active ads); ads are matched by employer organisation number.
7. **Profile:** claims, evidence and a section state for every area (`available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, `failed`), plus a plain summary where every sentence cites its sources.
8. **Refresh:** with `--previous`, stable claim keys give typed changes (`new_job`, `closed_job`, `new_role`, …) with evidence for both sides.

## Reproduce the 100-company smoke test

```bash
python scripts/run_competition_batch.py smoke/smoke-companies.txt --output out/smoke-envelopes.jsonl --report out/smoke-report.json --html out/smoke-report.html
```

To draw a fresh random sample from the public list of 411,160 companies:

```bash
curl -L "https://builderr.ai/signalpost-company-universe-2025.jsonl.gz" -o signalpost-universe.jsonl.gz
```

```bash
python select_entry_batch.py --universe signalpost-universe.jsonl.gz --count 100 --output my-sample.jsonl
```

Then check `out/smoke-report.json`: `emitted_envelopes` is 100 and `validation.passed` is true.

## Tests

```bash
pip install pytest
```

```bash
python -m pytest -q
```

141 tests: extraction, identity gate, NAV matching, the result contract, refresh, tolerant input, and end-to-end runs with a crashing company, a deadline hit, a company missing from the snapshot and a bad input row.

## In this repository

| Path | What it is |
|---|---|
| `run.bat`, `run.sh` | One-click runners (set up, install, run, open results) |
| `scripts/run_competition_batch.py` | The agent's command |
| `src/norway_company_agent/` | Research, identity gate, extraction, NAV jobs, contract, refresh, results page |
| `smoke/`, `demo/` | Saved results of the live test runs (output only; the agent never reads them) |
| `vendor/` | One prebuilt dependency (`jstyleson`, MIT) so installs never compile anything |
| [SUBMISSION.md](SUBMISSION.md), [COMPLIANCE.md](COMPLIANCE.md), [LIMITATIONS.md](LIMITATIONS.md), [PRD.md](PRD.md) | Submission details, requirement check, sources and licences, design |

Other scripts in `scripts/` (Brave discovery, LinkedIn experiments, Google News, YouTube, reviews) come from the starter kit and are **not** used by the agent.

## Sources and licences

Brønnøysundregistrene Enhetsregisteret and Regnskapsregisteret open APIs (NLOD) · NAV job vacancy feed (official API, [NAV API terms](https://arbeidsplassen.nav.no/vilkar-api)) · company-owned websites, robots.txt respected. No search APIs, no LinkedIn, Meta, Google, Glassdoor or Indeed. Full details: [LIMITATIONS.md](LIMITATIONS.md).
