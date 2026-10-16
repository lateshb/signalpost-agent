# Signalpost agent — PRD and build spec

Status: building on 16 Oct 2026. Freeze and submit by 18 Oct (last revision). Round ends 21 Oct.

## 1. What we are building

A batch program. It takes a file of Norwegian organisation numbers and returns one profile (an "envelope") per company. Each profile says what the company does, who leads it, where it operates, its latest filed numbers, whether it is hiring, and what dated activity it has, with a source for every fact. It never guesses: if a fact can't be tied to the exact company, it is left out and marked.

It runs again later and reports what changed.

## 2. Why this plan (scoring)

| Part | Points | What gets it |
|---|---:|---|
| Recall and coverage | 50 | External facts (website, profiles, jobs, news) for as many companies as possible. 70% is "how many companies", 30% is "how many facts" |
| Precision and evidence | 30 | Every fact is for the right company and has source + date |
| Summary | 12 | Short plain explanation built only from our facts, including what is unknown |
| UX | 8 | Easy to find and check facts, desktop and mobile |

Qualify at 65/100 on an official run. One wrong-company fact or one made-up number blocks qualification.

On the 5 Oct leaderboard nobody had qualified. The top entry had 60.8, with recall only 13.8/50 and near-full marks elsewhere. **So the job is: keep precision perfect, and raise recall.** Recall comes from external facts, because every entrant already gets the registry data.

The biggest recall lever is companies with no website in the registry. No website means no jobs, news or profiles for that company. So we find their website ourselves, safely.

## 3. Hard rules

1. One envelope per input, always, in input order. A crash for one company becomes a `failed` envelope, never a missing row.
2. The org number is the only identity key. Names, domains and handles are candidates until proven.
3. A website is published only if the identity gate passes. For sites we find ourselves, the gate is strict (section 6).
4. Never write 0 for a missing number. Missing is a state, not a value.
5. Every claim points to evidence: source URL, retrieval time, content hash, the text span, and the reporting period where relevant.
6. No LinkedIn, Meta, Glassdoor, Indeed or Google scraping in the submitted run. No paid or personal API keys required.
7. States used: `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, `failed`.

## 4. Pipeline

```
input file -> read + clean org numbers (bad/duplicate lines handled, not fatal)
  -> registry snapshot row (fallback: live registry API if missing from snapshot)
  -> official modules: live entity, annual accounts, roles, group, subunits
  -> website:
       registry website -> crawl -> identity gate (normal)
       no registry website (or it fails) -> guess domains -> crawl -> identity gate (strict)
  -> crawl of verified site: homepage + sitemap + up to 8 priority pages
       (about/contact, careers/jobs, news, people, locations; picked round-robin)
  -> extract: description, social links, job postings, dated news, org numbers, contact text
  -> contract adapter -> claims + evidence + section states + summary
  -> refresh diff against previous run (optional) -> changes
  -> validate -> write envelopes JSONL + report JSON + HTML viewer
```

Each company runs in its own worker with a time budget. A global deadline stops new work and writes `failed` envelopes for unfinished companies, so the run always finishes inside the time limit.

## 5. Field families and how each is filled

| Section | Field(s) | Source | Notes |
|---|---|---|---|
| Legal identity | name, form, address, industry, registered employees | Registry snapshot / live API | Official |
| Public brand | site title / JSON-LD name | Verified site | Only from verified site |
| Annual accounts | revenue, operating result, annual result, assets, equity, debt per year | Regnskapsregisteret API | Reporting period on every value; null stays null |
| Leadership | active roles (name, role) | Registry roles | Inactive roles dropped |
| Workplaces | registered subunits | Registry subunits | |
| Group | parent / group relation | Registry group endpoint | Labelled, never merged |
| Official website | URL + how verified | Registry link or domain guess | Gate required |
| Company profiles | LinkedIn/Facebook/etc. links found on the verified site | Verified site | Link only; we don't scrape the platforms |
| Hiring | job postings (title, URL, location, posted/closing date) | JSON-LD JobPosting, careers pages, links to ATS (Webcruiter, Jobbnorge, Teamtailor, Recman…) | Careers page with zero jobs = `not_available` with note, not "no hiring" |
| Activity | dated news items (title, date, URL) | JSON-LD Article, article meta, news pages with dates | Undated items are dropped |

## 6. Identity gate

Registry-linked site (normal mode) is `exact` if any of:
- the exact org number is shown on any crawled page of the site, or
- all legal-name words appear in homepage title/description/structured data/footer.

Downgraded to not publishable if: parked/for-sale page, or the homepage shows a different org number and not ours (likely parent or sister company).

Discovered site (strict mode) is `exact` only if:
- the exact org number is shown on the site, or
- the full legal name appears **and** the registered postcode plus street or city appear **and** no other org number is on the homepage.

Anything else: website section is `ambiguous`, nothing from the site is published.

Domain guesses: `<name>.no`, `<name-with-hyphens>.no`, `<name>.com`, and the name without "holding/invest/eiendom". Max 4. DNS check first, so dead guesses cost nothing. Skipped when the name is a single generic word ("Bygg AS").

## 7. Output envelope

```json
{
  "schema_version": "signalpost-envelope-v1",
  "organisation_number": "923609016",
  "run": {"run_id": "...", "started_at": "...", "completed_at": "...", "terminal_status": "completed|failed"},
  "status": "available|not_available|failed|...",
  "legal_identity": {"name": "...", "legal_form": "AS", "address": {...}, "industry": {...}},
  "public_brand": {"name": "...", "state": "available|not_available|ambiguous"},
  "sections": {
    "legal_identity": {"state": "available"},
    "annual_accounts": {"state": "...", "latest_period": "2025"},
    "leadership": {"state": "..."}, "workplaces": {"state": "..."}, "group": {"state": "..."},
    "website": {"state": "...", "verification": "org_number_on_site|..."},
    "company_profiles": {"state": "..."}, "hiring": {"state": "...", "count": 0},
    "activity": {"state": "...", "count": 0}
  },
  "claims": [{"claim_id": "...", "claim_key": "...", "field": "job_posting", "value": {...},
              "availability": "available", "confidence": 0.95, "evidence_ids": ["ev-..."],
              "reporting_period": null, "effective_at": null, "extraction_method": "..."}],
  "evidence": [{"id": "ev-...", "source_url": "...", "source_class": "official_registry|company_owned",
                "retrieved_at": "...", "effective_at": null, "content_sha256": "...", "claim_span": "...",
                "extraction_method": "..."}],
  "summary": "Plain text, 3-6 sentences, from claims only.",
  "unknowns": ["No website could be verified", "..."],
  "refresh": {"previous_run_id": null, "first_seen": {...}},
  "changes": [{"type": "new_job", "claim_key": "...", "before": null, "after": {...}}],
  "errors": [{"stage": "...", "message": "..."}],
  "operations": {"requests": 0, "runtime_ms": 0, "third_party_cost_usd": 0}
}
```

`claim_key` is stable across runs (built from field + identifying value, not timestamps), which makes refresh idempotent.

## 8. Refresh

- `--previous old_envelopes.jsonl` turns on diff mode. Old files are never modified.
- Compare claim keys: added -> `new_*`, removed -> `removed_*`/`closed_job`, value changed -> `changed_*`.
- If a section failed this run but had claims last run, carry those claims forward marked `carried_forward: true` and keep the section state `failed`. A network error never looks like "company has no jobs" or "revenue is 0".
- Same inputs twice = zero changes.

## 9. Summary (12 points)

Built from claims, no LLM needed (deterministic, free, reproducible):
what it does (industry + site description), who leads it (CEO/chair), where (address + number of workplaces), latest numbers (revenue/result with year), hiring and activity counts with latest date, what changed, and what is unknown.

## 10. UX (8 points)

`--html report.html` writes one self-contained page: search box, one card per company, every fact with a "source" link and date, section states shown as badges, works on mobile.

## 11. Run command

```bash
uv sync --frozen
uv run python scripts/run_competition_batch.py \
  --organisations input.jsonl --bulk enheter.csv.gz \
  --output out/envelopes.jsonl --report out/report.json --run-id day-1 \
  [--previous out/prev.jsonl] [--deadline-seconds 3000] [--workers 24] [--html out/report.html]
```

Input accepts JSON list, JSONL or plain text. Bulk snapshot can be gzipped or plain CSV. Exit code 0 only if validation passes.

## 12. Acceptance tests (must pass before submit)

1. 100 inputs -> 100 valid envelopes, same order, even with one invalid number, one duplicate, one missing-from-snapshot and one crashing company.
2. Every claim has at least one evidence id that exists; every evidence item has URL, time and hash.
3. No numeric claim with a null source value; no zeros invented.
4. Strict gate rejects a guessed site that only matches by name; accepts one with the org number in the footer.
5. Job and news extraction unit tests on fixture HTML (JSON-LD, ATS links, Norwegian dates).
6. Refresh: same file twice -> 0 changes; failed section -> claims carried forward.
7. Global deadline -> unfinished companies get `failed` envelopes and the run still exits with a full file.
8. Clean clone + `uv sync --frozen` + run command works.
9. Live 100-company smoke test on a laptop; hand-check 20 published websites for wrong-company matches.

## 13. Timeline

- 16 Oct: build all steps, unit + offline end-to-end tests, then live smoke test on laptop. Submit if v1 not yet in.
- 17 Oct: fix what the smoke test shows; hand-check websites; tune budgets for 1,000-company runs.
- 18 Oct: freeze, clean-clone check, submit final commit hash with report and declarations.

## 14. Out of scope

LinkedIn/Glassdoor/Indeed connectors, Google Maps, review sentiment, YouTube, learned routing, LLM extraction. Possible later, not before the freeze.

## 15. Open questions

- Official time budget per 1,000-company batch (defaults assume ~50 min; adjust `--deadline-seconds`).
- Exact input file format Builderr uses (we accept the common ones).
