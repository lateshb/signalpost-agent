# Sources, rights and limitations

## Sources used by the submitted run

| Source | Access | Used for | Licence / terms |
|---|---|---|---|
| Brønnøysundregistrene Enhetsregisteret (bulk CSV + `/api/enheter`) | Open public API, no key | Identity, address, industry, registered employees, website link | NLOD (Norwegian Licence for Open Government Data) |
| Enhetsregisteret roles, subunits, group structure endpoints | Open public API, no key | Leadership, workplaces, group relations | NLOD |
| Regnskapsregisteret (`/regnskapsregisteret/regnskap`) | Open public API, no key | Filed annual accounts | NLOD |
| Company-owned websites | Ordinary HTTP GET, honest user agent, robots.txt respected, bounded pages per site | Website verification, description, social links, job postings, news | Each site's own terms; only facts the company publishes about itself |
| DNS lookups of candidate domains | Standard resolver | Finding a website when the registry has none (registered email domain, legal-name domains) | n/a |
| NAV job vacancy feed (`pam-stilling-feed.nav.no`) | Official API, public token NAV publishes at `/api/publicToken` (no personal account) | Job postings, matched by employer organisation number | [NAV API terms](https://arbeidsplassen.nav.no/vilkar-api): free for anyone, republishing allowed; inactive ads must be removed (we publish only ads NAV marks active, every run) |

No search APIs, no paid data, no LLMs, no personal credentials. Third-party cost: $0 per batch.

NAV describes its public token as suitable for experiments and offers a free private token on request. By default the agent fetches the public token at run time. To use a registered token instead, set the environment variable `NAV_FEED_TOKEN` (optional; never committed).

## Not used

LinkedIn, Facebook/Meta, Instagram, Glassdoor, Indeed, Google Search/Maps/News and review sites are **not** fetched. Links to social profiles are only reported when the company's own verified website links to them; we don't visit those platforms.

The starter-kit scripts for LinkedIn, Brave Search, Google News, YouTube and reviews are left in the repo for reference but are not called by `scripts/run_competition_batch.py`.

## Safety

- Only public http(s) URLs; private, loopback and link-local addresses are blocked, including after redirects.
- Response size limits per page; sitemap reads capped.
- Secrets: none required. Environment variables are only used for run knobs (see README).

## Known gaps

- Sites that need JavaScript to show content are crawled statically only. Jobs or news loaded by JavaScript are missed.
- Domain guessing finds sites whose domain matches the legal name. Brand names that differ from the legal name are not found.
- Job postings are found on the company's own site and on NAV's job board. Ads only on other boards (e.g. FINN, which NAV's feed excludes) are not found.
- NAV's feed is read for the last 45 days; an older ad that is still active is missed.
- News is only taken from the company's own site; independent press coverage is not covered.
- A careers page with no listings is reported as `not_available` with a note, not as "not hiring".
- Group websites that show only the parent's org number are treated as not exact for the subsidiary and are not published.
- Annual-report PDFs are not parsed (registry financials cover the main figures).
- Jobs on a group's careers page that name a different company (for example a subsidiary) are not published for the parent; they would belong to the subsidiary's own profile.
- A registry-linked site whose legal name is a single word and whose homepage text cannot be extracted (heavy JavaScript) is reported as `ambiguous` rather than published.
