# Signalpost agent

Give it Norwegian organisation numbers. It returns one profile per company: legal identity, latest filed accounts, leadership, workplaces, verified website, social profiles, job postings and dated news, with a source for every fact. Facts that can't be tied to the exact company are left out and marked. Run it again with `--previous` and it reports what changed.

It researches only the organisation numbers in the input file it is given at run time, and fetches everything live (registry APIs, company websites, NAV's job feed). Nothing is precomputed; `smoke/` is the output of a test run, not data the agent reads.

Requirement-by-requirement check against the challenge page: [COMPLIANCE.md](COMPLIANCE.md).

Plan and design: [PRD.md](PRD.md). Sources and licences: [LIMITATIONS.md](LIMITATIONS.md). Submission details and the 100-company smoke-test result: [SUBMISSION.md](SUBMISSION.md), [`smoke/`](smoke/).

## Install (any PC)

Works on Windows, macOS and Linux. Needs internet access while running.

**Option A — uv (recommended; what the official run uses).** Install uv once:

- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Or with any existing Python: `pip install uv` (then use `python -m uv` if `uv` is not on your PATH)

Open a new terminal, then in the repository folder run `uv sync --frozen`. uv downloads the pinned Python 3.12 and the exact dependency versions from `uv.lock`.

**Option B — plain Python and pip (no uv).** Python 3.11 or newer:

```bash
python -m venv .venv
```

Activate it (`.venv\Scripts\activate` on Windows, `source .venv/bin/activate` on macOS/Linux), then:

```bash
pip install "setuptools==80.9.0" wheel
```

```bash
pip install --no-build-isolation -r requirements.txt
```

One dependency, `jstyleson`, ships only as source code; pinning the build tool keeps a clean install reproducible. The uv route pins it in `pyproject.toml`.

Then run the commands below with `python` instead of `uv run python`. `requirements.txt` is exported from `uv.lock` with the same pinned versions.

## Run command (official)

```bash
uv sync --frozen
```

```bash
uv run python scripts/run_competition_batch.py --organisations INPUT_FILE --bulk REGISTRY_SNAPSHOT --output out/envelopes.jsonl --report out/report.json --run-id RUN_ID --html out/report.html
```

Each command is one line so it pastes the same into Windows (cmd or PowerShell), macOS and Linux terminals.

- `INPUT_FILE`: JSON list, JSONL (`{"organisation_number": "..."}`) or plain text, one number per line. Bad or duplicate rows never crash the run.
- `REGISTRY_SNAPSHOT`: Brreg entity bulk CSV, gzipped or plain. Optional; companies missing from it are looked up in the live registry.
- Output: one envelope per unique input, in input order. Exit code 0 when the contract check passes.
- Refresh: add `--previous out/old-envelopes.jsonl`. The old file is only read.

Useful knobs (flags or environment variables):

| Flag | Env | Default | What it does |
|---|---|---|---|
| `--deadline-seconds` | `SIGNALPOST_DEADLINE_SECONDS` | 3000 | Hard stop. Unfinished companies get a `failed` envelope and the file is written |
| `--workers` | `SIGNALPOST_WORKERS` | 24 | Companies in parallel |
| `--company-budget-seconds` | `SIGNALPOST_COMPANY_BUDGET_SECONDS` | 75 | Time per company for website crawling and discovery |
| `--no-discovery` | | off | Skip website discovery (registered email domain, then domains from the legal name) |
| `--no-nav-jobs` | | off | Skip job postings from NAV's job vacancy feed |

No API keys are needed. Optional: `NAV_FEED_TOKEN` (a private token for NAV's job feed; without it the public token NAV publishes is used). Third-party cost per batch: $0.

## 100-company smoke test

`curl` ships with Windows 10+, macOS and Linux. The registry snapshot is optional (about 155 MB); without `--bulk` every company is looked up in the live registry instead.

```bash
curl -L "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv" -o brreg-enheter.csv.gz
```

```bash
curl -L "https://builderr.ai/signalpost-company-universe-2025.jsonl.gz" -o signalpost-universe.jsonl.gz
```

```bash
uv run python select_entry_batch.py --universe signalpost-universe.jsonl.gz --count 100 --output smoke-companies.jsonl
```

```bash
uv run python scripts/run_competition_batch.py --organisations smoke-companies.jsonl --bulk brreg-enheter.csv.gz --output out/smoke-envelopes.jsonl --report out/smoke-report.json --run-id smoke-001 --html out/smoke-report.html
```

To re-run the exact 100 companies in this repository's result, use `--organisations smoke/smoke-companies.txt`.

Then check `out/smoke-report.json`: `emitted_envelopes` should be 100, `validation.passed` true, and `companies_with_section_available` shows coverage per section. Open `out/smoke-report.html` to browse the profiles and click through to sources.

Refresh check (should report 0 changes for an unchanged snapshot, apart from real changes on live sites):

```bash
uv run python scripts/run_competition_batch.py --organisations smoke-companies.jsonl --bulk brreg-enheter.csv.gz --output out/smoke-envelopes-2.jsonl --report out/smoke-report-2.json --run-id smoke-002 --previous out/smoke-envelopes.jsonl
```

## Tests

```bash
uv run --with pytest pytest -q
```

Without uv: `pip install pytest`, then `python -m pytest -q`. Checked on Windows with Python 3.11 (pip route) and 3.12 (uv route).

`tests/test_signalpost_v2.py` covers the new parts: job and news extraction, org-number detection, the strict identity gate, domain guessing, the envelope contract, refresh (idempotent + carry-forward), tolerant input, and an end-to-end runner test with a crashing company, a company that hits the deadline, one missing from the snapshot and a bad input row.

## How it works (short)

1. Registry snapshot row (or live registry) gives the identity anchor.
2. Official APIs: live entity, annual accounts, roles, group, subunits.
3. Website: the registry-linked site. If there is none, or it does not verify: the domain of the email address registered in Brønnøysund (mailbox providers and shared service providers skipped), then a few domains built from the legal name (`fjordbygg.no`, `fjord-bygg.no`, `fjordbygg.com`). A discovered site is only used if it shows our org number, or the full legal name plus the registered address.
4. Crawl of the verified site: homepage, sitemap, and up to 8 pages picked across about/contact, careers, news, people and locations. Robots.txt is respected.
5. Extraction: JSON-LD JobPosting/Article first, then article meta, then careers-page and applicant-system links (Webcruiter, Jobbnorge, Teamtailor and others), then dated news links. Undated items are dropped.
6. Jobs from NAV (arbeidsplassen.nav.no): while companies are researched, a background thread reads NAV's official job vacancy feed (last 45 days, active ads only). A company's name only picks candidate ads; an ad is published only if NAV's own record names the employer by our organisation number or one of our registered subunits.
7. Contract adapter builds claims, evidence and section states; a plain summary is written from the claims only.
8. `--html` writes a one-file viewer: search, filters, sorting, a profile per company with a source link on every fact, side-by-side comparison of up to 4 companies, works on mobile and in dark mode.

## Older scripts

The other scripts in `scripts/` (Brave discovery, LinkedIn experiments, Google News, YouTube, reviews) are from the starter kit. They are **not** used by the submitted run.
