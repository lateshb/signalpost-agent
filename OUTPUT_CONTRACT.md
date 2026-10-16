# Output contract

One JSON object per line, one per unique input organisation number, in input order. Full field list and reasoning: [PRD.md](PRD.md) section 7.

Key parts:

- `organisation_number`, `schema_version`, `run` (`run_id`, `started_at`, `completed_at`, `terminal_status`)
- `status`: overall state of the envelope
- `legal_identity`, `public_brand`
- `sections`: state per section — `legal_identity`, `annual_accounts`, `leadership`, `workplaces`, `group`, `website`, `company_profiles`, `hiring`, `activity`
- `claims`: each with `claim_key` (stable across runs), `field`, `value`, `availability`, `confidence`, `evidence_ids`, `reporting_period`, `effective_at`, `extraction_method`, `first_observed_at`, `last_observed_at`
- `evidence`: each with `id`, `source_url`, `source_class`, `retrieved_at`, `effective_at`, `content_sha256`, `claim_span`, `extraction_method`
- `summary`, `unknowns`
- `refresh`, `changes` (typed: `new_job`, `closed_job`, `new_role`, `removed_role`, `new_location`, `website_found`, `changed_description`, …)
- `errors`, `operations` (`requests`, `runtime_ms`, `third_party_cost_usd`)

Allowed states everywhere: `available`, `not_available`, `blocked`, `not_applicable`, `ambiguous`, `failed`. Missing values are never written as zero. A checked source with zero items (for example a careers page with no listings) is `not_available` with a note, which is different from a source we could not check (`failed` or `blocked`).
