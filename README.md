# Signalpost agent

Give it Norwegian organisation numbers. It returns one profile per company: legal identity, latest filed accounts, leadership, workplaces, verified website, social profiles, job postings and dated news, with a source for every fact. Facts that can't be tied to the exact company are left out and marked. Run it again with `--previous` and it reports what changed.

Plan and design: [PRD.md](PRD.md). Sources and licences: [LIMITATIONS.md](LIMITATIONS.md). Submission details and the 100-company smoke-test result: [SUBMISSION.md](SUBMISSION.md), [`smoke/`](smoke/).

## Run command (official)

```bash
uv sync --frozen
uv run python scripts/run_competition_batch.py \
  --organisations INPUT_FILE \
  --bulk REGISTRY_SNAPSHOT \
  --output out/envelopes.jsonl \
  --report out/report.json \
  --run-id RUN_ID \
  --html out/report.html
```

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
| `--no-discovery` | | off | Skip website discovery by domain guessing |

No API keys are needed. Third-party cost per batch: $0.

## 100-company smoke test

```bash
uv sync --frozen
curl -L 'https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv' -o brreg-enheter.csv.gz
curl -L 'https://builderr.ai/signalpost-company-universe-2025.jsonl.gz' -o signalpost-universe.jsonl.gz

uv run python select_entry_batch.py --universe signalpost-universe.jsonl.gz --count 100 --output smoke-companies.jsonl

uv run python scripts/run_competition_batch.py \
  --organisations smoke-companies.jsonl --bulk brreg-enheter.csv.gz \
  --output out/smoke-envelopes.jsonl --report out/smoke-report.json \
  --run-id smoke-001 --html out/smoke-report.html
```

Then check `out/smoke-report.json`: `emitted_envelopes` should be 100, `validation.passed` true, and `companies_with_section_available` shows coverage per section. Open `out/smoke-report.html` to browse the profiles and click through to sources.

Refresh check (should report 0 changes for an unchanged snapshot, apart from real changes on live sites):

```bash
uv run python scripts/run_competition_batch.py \
  --organisations smoke-companies.jsonl --bulk brreg-enheter.csv.gz \
  --output out/smoke-envelopes-2.jsonl --report out/smoke-report-2.json \
  --run-id smoke-002 --previous out/smoke-envelopes.jsonl
```

## Tests

```bash
uv run --with pytest pytest -q
```

`tests/test_signalpost_v2.py` covers the new parts: job and news extraction, org-number detection, the strict identity gate, domain guessing, the envelope contract, refresh (idempotent + carry-forward), tolerant input, and an end-to-end runner test with a crashing company, a company that hits the deadline, one missing from the snapshot and a bad input row.

## How it works (short)

1. Registry snapshot row (or live registry) gives the identity anchor.
2. Official APIs: live entity, annual accounts, roles, group, subunits.
3. Website: the registry-linked site, or if there is none, a few domains guessed from the legal name (`fjordbygg.no`, `fjord-bygg.no`, `fjordbygg.com`). A guessed site is only used if it shows our org number, or the full legal name plus the registered address.
4. Crawl of the verified site: homepage, sitemap, and up to 8 pages picked across about/contact, careers, news, people and locations. Robots.txt is respected.
5. Extraction: JSON-LD JobPosting/Article first, then article meta, then careers-page and applicant-system links (Webcruiter, Jobbnorge, Teamtailor and others), then dated news links. Undated items are dropped.
6. Contract adapter builds claims, evidence and section states; a plain summary is written from the claims only.

## Older scripts

The other scripts in `scripts/` (Brave discovery, LinkedIn experiments, Google News, YouTube, reviews) are from the starter kit. They are **not** used by the submitted run.
