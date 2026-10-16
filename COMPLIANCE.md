# Compliance with the challenge page

Every requirement on https://builderr.ai/challenges/signalpost (and the linked brief, evaluation contract, source policy and playbook), with where this agent meets it. Checked 16 Oct 2026.

## 01 · What to build

| Requirement | How this agent meets it | Where |
|---|---|---|
| Give it a Norwegian company number; it finds public facts | Reads org numbers from the input file Builderr supplies at run time; researches each one live | `scripts/run_competition_batch.py` |
| Company details, people, locations, financial results, jobs and public activity where available | Legal identity, leadership roles, registered workplaces, filed annual accounts (all years returned), job postings (company site + NAV job board), dated news from the company site, social profiles linked from the verified site | `official.py`, `website.py`, `site_items.py`, `nav_jobs.py`, `contract.py` |
| Check each fact belongs to the right company | Org number is the only identity key. Websites must pass an identity gate (org number on the site, or full legal name + registered address for discovered sites). NAV jobs must name our org number or a registered subunit | `identity.py`, `domain_guess.py`, `nav_jobs.py` |
| Link it to its source and date | Every claim has evidence: source URL, retrieval time, content SHA-256, the supporting text span, extraction method; reporting period on financial values | `contract.py` (`add_evidence`, `add_claim`) |
| Clearly mark anything you could not find | Every section has a state; `unknowns` lists what was not found and why | `contract.py`, `summary.py` |
| Keep profiles current; show what changed; preserve earlier evidence | `--previous` turns on diff mode: typed changes (`new_job`, `closed_job`, `new_role`, `website_found`, …) with evidence for both sides; first-seen dates kept; failed sources carry the last value forward; the previous file is never modified | `refresh_contract.py` |
| Must work from a company number, including companies it has not researched before | No precomputed data is used. The registry snapshot is optional (identity anchor only); companies missing from it are looked up live | `batch.py`, `profile_from_live` |

## 02 · What to submit

| Requirement | Where |
|---|---|
| 100-company smoke-test result showing one complete result per input | `smoke/` (input list, run report, envelopes, HTML viewer) |
| Repository link, exact commit hash, one command | `SUBMISSION.md`, `README.md` |
| Models, APIs, licences, expected cost per official run, contact | `SUBMISSION.md`, `LIMITATIONS.md` |
| No precomputed profiles or company manifest needed | None are used by the agent |

## 03 · How we test it

| Requirement | How this agent meets it |
|---|---|
| Builderr chooses the batch; the shared set can grow (1,000 → 1,100) | Batch size comes from the input file; nothing is hard-coded. `--expected-count` is optional |
| Fixed time and resource budget; finish and return one result per company | `--deadline-seconds` (default 3000) is a hard stop: unfinished companies get a `failed` envelope and the file is always written. Per-company budget `--company-budget-seconds` (default 75). NAV feed loading is capped at 40% of the deadline and runs in the background |
| Timeouts or dropped results are not scored | One envelope per unique input, in input order, validated before exit (`validation.passed`) |

## 04 · Common traps

| Trap | Status |
|---|---|
| Agent picks its own companies | Reads only `--organisations` |
| Handles one company at a time | Batch runner with `--workers` (default 24) |
| No single command | `python scripts/run_competition_batch.py INPUT_FILE` (`README.md`, `SUBMISSION.md`); `run.bat` / `run.sh` for one-click local runs |
| Does not install on a clean machine | One install step, `pip install -r requirements.txt`, from prebuilt pinned packages (nothing compiled; one source-only dependency is vendored as a wheel). Checked by cloning the exact commit into a new folder, empty virtual environment, that install step, then the run command. `uv.lock` + `.python-version` also pinned for uv users |
| Returns fewer results than inputs | Crashes, timeouts, invalid rows, duplicates and companies missing from the snapshot all still produce an envelope (end-to-end test) |
| "You cannot use an LLM" | We chose not to: summaries are deterministic and built only from claims, so no model key is needed |

## 05 · How you score

| Dimension | What the agent does for it |
|---|---|
| Recall and coverage (50) | Official data for every company; website from the registry, else the registered email domain, else legal-name domains; up to 8 crawled pages per verified site (about, contact, careers, news, people, locations) plus sitemap; JSON-LD JobPosting/Article, ATS links, dated news; social profiles linked from the site; NAV job postings matched by org number |
| Precision and evidence (30) | Strict identity gates; nothing published from an unverified site; NAV jobs only when NAV's record names our org number or a registered subunit; a job link must point at one posting (career info pages, PDFs and ATS login links are not jobs); a posting that names another company (e.g. a subsidiary on the group's careers page) is not published for this one; a news item must sit under a news/press/blog section and carry its own publication date, never a future date (contact, service and index pages are not news); undated items dropped; missing values never written as zero; every claim has evidence |
| Synthesis (12) | Plain summary of what the company does, where, who leads it, latest filed numbers (newest year), hiring and activity, what changed, and what is unknown. Each sentence carries `summary_citations` (claim keys + evidence ids) |
| UX (8) | `--html` viewer: search, sort, filters; a profile per company with a source link and date on every fact; side-by-side comparison of up to 4 companies (tick “Compare”); works on desktop and mobile, light and dark |

## 06 · Qualification

| Requirement | Status |
|---|---|
| Result for every company, including missing or blocked | Yes |
| Never replace missing values with zero | Null financial values are skipped; zeros are only published when the filing reports 0 (checked against the live API) |
| Source, retrieval date and reporting period for every claim | Yes; validator check `all_claims_have_evidence` |
| Preserve earlier evidence, no duplicates on rerun | Stable claim keys; rerunning the same 100 companies gives 0 changes; before-side evidence of every change is kept in the envelope |
| Unsafe source or secret handling | No secrets required. Only public http(s) URLs; private, loopback and link-local addresses blocked, including after redirects; robots.txt respected; response size limits |
| Better to miss information than publish it under the wrong company | Uncertain website matches are `ambiguous` and nothing from that site is published |
| States: available, not_available, blocked, not_applicable, ambiguous, failed | Exactly these six |

## Full technical requirements

| Requirement | Status |
|---|---|
| Exactly one terminal envelope per input; distinct states | Yes |
| Refresh idempotent; same snapshot → no duplicates or false changes | Yes (test + live rerun) |
| Document source rights, server-side secrets and safe URL handling | `LIMITATIONS.md` |
| Pinned dependencies and one reproducible run command | `uv.lock`, `.python-version`, `README.md` |
| Up to four revised commit hashes before 18 Oct | First submission is version 1 |

## Source policy

| Rule | Status |
|---|---|
| Search results are candidates, not evidence | No search APIs are used; discovered domains are fetched and must pass the identity gate |
| Profiles/domains must resolve to the exact legal entity | Identity gate; NAV org-number match |
| Group/parent/subsidiary relations labelled, not collapsed | `group.related_entity` claims with the relation; a site showing only another org number is not published |
| Every claim records source, retrieval time, effective/reporting date, content hash, extraction method | Yes |
| No unofficial LinkedIn, Meta, Glassdoor, Indeed or Google clients | None are called by the submitted run (starter-kit experiments are left in `scripts/` but unused) |
| Official or licensed APIs; pages whose terms and robots permit access | Brønnøysund open APIs (NLOD); NAV job feed (official API, NAV's published public token, NAV API terms); company websites with robots.txt respected |
