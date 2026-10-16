# Submission

Everything Builderr asks for in the submission email, in one place.

## Run command

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

`--bulk` is optional (companies missing from it are looked up in the live registry). Time and parallelism can be set with `--deadline-seconds` (default 3000) and `--workers` (default 24); see [README.md](README.md). Exit code 0 when the output contract check passes.

## 100-company smoke test

Files in [`smoke/`](smoke/):

- `smoke-companies.txt`: the 100 organisation numbers (from `select_entry_batch.py --count 100` on the public universe)
- `smoke-report.json`: run report
- `smoke-envelopes.jsonl`: one envelope per company
- `smoke-report.html`: browsable profiles with source links

Run `smoke-001`, 16 Oct 2026, on a laptop:

| | |
|---|---|
| Envelopes emitted | 100 of 100, validation passed |
| Companies with section available | annual accounts 100, leadership 100, workplaces 73, website 6, company profiles 2, activity 2, hiring 0 |
| Websites found by domain guessing | 4 (registry listed a website for only 7 of the 100) |
| Time per company | p50 6.6 s, p95 43.1 s |
| Wall time | 92.6 s |
| Requests | 846 |
| Third-party cost | $0 |

All six published websites were checked by hand against the registry name and address; no wrong-company matches were found.

## Models, APIs and licences

- Models: none. No LLM is used; summaries are built deterministically from claims.
- APIs: Brønnøysundregistrene Enhetsregisteret and Regnskapsregisteret open APIs (no key), licensed under NLOD.
- Web: company-owned websites only, robots.txt respected. No search APIs, no LinkedIn/Meta/Google/Glassdoor/Indeed.
- Secrets: none required.

Full details: [LIMITATIONS.md](LIMITATIONS.md).

## Expected cost per official batch

$0 third-party cost. Compute only.
