"""Turn internal company profiles into the official Signalpost envelope (see PRD.md section 7).

Every published claim must have evidence. Nothing here invents a value: a missing number stays out,
and the section state says why.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from .identity import _tokens

SCHEMA_VERSION = "signalpost-envelope-v1"
STATES = ("available", "not_available", "blocked", "not_applicable", "ambiguous", "failed")
SECTIONS = (
    "legal_identity", "annual_accounts", "leadership", "workplaces", "group",
    "website", "company_profiles", "hiring", "activity",
)
FINANCIAL_METRICS = ("revenue", "operating_result", "profit_before_tax", "annual_result", "assets", "equity", "debt")
REGISTRY_SOURCE = "https://data.brreg.no/enhetsregisteret/api/enheter/{org}"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def map_state(status: str | None) -> str:
    return {
        "available": "available",
        "not_found": "not_available",
        "not_applicable": "not_applicable",
        "blocked": "blocked",
        "source_error": "failed",
        "not_fetched": "failed",
    }.get(str(status or ""), "failed")


class _Builder:
    def __init__(self, org: str) -> None:
        self.org = org
        self.claims: list[dict[str, Any]] = []
        self.evidence: dict[str, dict[str, Any]] = {}
        self._claim_keys: set[str] = set()

    def add_evidence(
        self,
        *,
        source_url: str,
        source_class: str,
        retrieved_at: str | None,
        content_sha256: str | None,
        claim_span: str,
        extraction_method: str,
        effective_at: str | None = None,
        source_type: str | None = None,
    ) -> str:
        record = {
            "source_url": source_url,
            "source_class": source_class,
            "source_type": source_type or source_class,
            "retrieved_at": retrieved_at,
            "effective_at": effective_at,
            "content_sha256": content_sha256,
            "claim_span": str(claim_span)[:500],
            "extraction_method": extraction_method,
        }
        evidence_id = "ev-" + _sha([source_url, content_sha256, record["claim_span"], extraction_method])[:16]
        record["id"] = evidence_id
        self.evidence.setdefault(evidence_id, record)
        return evidence_id

    def add_claim(
        self,
        field: str,
        value: Any,
        evidence_ids: list[str],
        *,
        identity: Any = None,
        confidence: float = 1.0,
        reporting_period: str | None = None,
        effective_at: str | None = None,
        extraction_method: str = "deterministic",
        section: str,
    ) -> None:
        if value in (None, "", [], {}) or not evidence_ids:
            return
        claim_key = f"{field}:" + _sha(identity if identity is not None else value)[:16]
        if claim_key in self._claim_keys:
            return
        self._claim_keys.add(claim_key)
        self.claims.append({
            "claim_id": f"{self.org}:{claim_key}",
            "claim_key": claim_key,
            "section": section,
            "field": field,
            "value": value,
            "availability": "available",
            "confidence": confidence,
            "evidence_ids": evidence_ids,
            "reporting_period": reporting_period,
            "effective_at": effective_at,
            "extraction_method": extraction_method,
        })


def _registry_record(profile: dict[str, Any]) -> dict[str, Any]:
    return profile.get("evidence", {}).get("registry") or {}


def _legal_identity(profile: dict[str, Any]) -> dict[str, Any]:
    live = (profile.get("evidence", {}).get("registry_live") or {}).get("value") or {}
    raw = _registry_record(profile).get("value") or {}
    lowered = {str(key).casefold(): value for key, value in raw.items()} if isinstance(raw, dict) else {}
    address = live.get("business_address") or {
        "adresse": [lowered.get("forretningsadresse.adresse")] if lowered.get("forretningsadresse.adresse") else [],
        "postnummer": lowered.get("forretningsadresse.postnummer") or None,
        "poststed": lowered.get("forretningsadresse.poststed") or None,
        "kommune": profile.get("municipality") or lowered.get("forretningsadresse.kommune") or None,
    }
    industry = live.get("industry") or (
        {"kode": profile.get("industry_code"), "beskrivelse": profile.get("industry_label")} if profile.get("industry_code") else None
    )
    return {
        "organisation_number": profile.get("organisation_number"),
        "name": live.get("name") or profile.get("name") or None,
        "legal_form": live.get("legal_form") or profile.get("legal_form") or None,
        "address": address,
        "industry": industry,
        "registered_employees": live.get("employees") if live.get("employees") is not None else profile.get("employees"),
        "bankrupt": bool(live.get("bankrupt") if live.get("bankrupt") is not None else profile.get("bankrupt")),
        "liquidating": bool(live.get("liquidating") if live.get("liquidating") is not None else profile.get("liquidating")),
        "latest_submitted_accounts": live.get("latest_submitted_accounts") or profile.get("latest_submitted_accounts") or None,
    }


def _official_evidence(builder: _Builder, record: dict[str, Any], span: str, method: str, effective_at: str | None = None) -> str:
    return builder.add_evidence(
        source_url=record.get("source_url") or REGISTRY_SOURCE.format(org=builder.org),
        source_class="official_registry",
        source_type=record.get("source_type"),
        retrieved_at=record.get("retrieved_at"),
        content_sha256=record.get("content_sha256"),
        claim_span=span,
        extraction_method=method,
        effective_at=effective_at or record.get("effective_at"),
    )


_ENTITY_IN_TEXT = re.compile(r"([^,;|()\n]{2,60}?)\s+(?:AS|ASA)\b")


def _names_other_entity(text: Any, name_tokens: set[str]) -> bool:
    """True when a job title names a company ("..., Aeron AS") that is not this legal entity."""
    if not text or not name_tokens:
        return False
    for match in _ENTITY_IN_TEXT.finditer(str(text)):
        entity = set(_tokens(match.group(1).split(" - ")[-1].split(" – ")[-1]))
        if entity and not name_tokens <= entity:
            return True
    return False


def _period(record: dict[str, Any]) -> tuple[str | None, str | None]:
    period = record.get("period") or {}
    if isinstance(period, dict):
        start, end = period.get("fraDato"), period.get("tilDato")
        if start or end:
            return f"{start or '?'}/{end or '?'}", (str(end)[:4] if end else None)
    return None, None


def _site_pages(website_value: dict[str, Any]) -> list[dict[str, Any]]:
    return [page for page in website_value.get("pages") or [] if isinstance(page, dict)]


def _verification_label(assessment: dict[str, Any]) -> str:
    reasons = " ".join(assessment.get("reasons") or [])
    if "organisation number" in reasons:
        return "org_number_on_site"
    if "registered address" in reasons:
        return "legal_name_and_address_on_site"
    if "legal-name" in reasons or "legal name" in reasons:
        return "legal_name_on_registry_linked_site"
    return "other"


def build_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    runtime_ms: int | None = None,
) -> dict[str, Any]:
    org = str(profile.get("organisation_number"))
    builder = _Builder(org)
    sections: dict[str, dict[str, Any]] = {name: {"state": "not_available"} for name in SECTIONS}
    errors: list[dict[str, Any]] = list(profile.get("errors") or [])
    records = profile.get("evidence", {})
    identity = _legal_identity(profile)

    # Legal identity (official).
    registry = records.get("registry") or {}
    live = records.get("registry_live") or {}
    identity_record = live if live.get("status") == "available" else registry
    if identity_record.get("status") == "available":
        sections["legal_identity"] = {"state": "available"}
        method = "registry_live_api" if identity_record is live else "registry_bulk_snapshot_row"
        for field, value in (
            ("legal_name", identity["name"]),
            ("legal_form", identity["legal_form"]),
            ("business_address", identity["address"] if any((identity["address"] or {}).values()) else None),
            ("industry", identity["industry"]),
            ("registered_employees", identity["registered_employees"]),
            ("latest_submitted_accounts_year", identity["latest_submitted_accounts"]),
        ):
            if value is None or value == "":
                continue
            ev = _official_evidence(builder, identity_record, f"{field}={json.dumps(value, ensure_ascii=False)}"[:300], method)
            builder.add_claim(field, value, [ev], section="legal_identity", extraction_method=method,
                              effective_at=identity_record.get("retrieved_at"))
    else:
        sections["legal_identity"] = {"state": map_state(identity_record.get("status")) if identity_record else "failed"}

    # Annual accounts.
    financials = records.get("financials")
    if financials:
        state = map_state(financials.get("status"))
        rows = ((financials.get("value") or {}).get("records") or []) if state == "available" else []
        if state == "available" and not rows:
            state = "not_available"
        latest_period = None
        for row in rows:
            period, year = _period(row)
            if year and (latest_period is None or str(year) > str(latest_period)):  # API order is not newest-first
                latest_period = year
            for metric in FINANCIAL_METRICS:
                amount = row.get(metric)
                if amount is None:
                    continue
                ev = _official_evidence(builder, financials, f"{metric}={amount} {row.get('currency') or ''} period={period}", "regnskapsregisteret_api", effective_at=(row.get("period") or {}).get("tilDato") if isinstance(row.get("period"), dict) else None)
                builder.add_claim(
                    f"financials.{metric}",
                    {"amount": amount, "currency": row.get("currency"), "account_type": row.get("account_type"), "year": year},
                    [ev],
                    identity=[metric, period, row.get("account_type")],
                    reporting_period=period,
                    section="annual_accounts",
                    extraction_method="regnskapsregisteret_api",
                )
        sections["annual_accounts"] = {"state": state, "latest_period": latest_period, "years_returned": len(rows)}
    history = records.get("financial_history")
    if history and history.get("status") == "available":
        years = (history.get("value") or {}).get("years") or []
        if years:
            ev = _official_evidence(builder, history, f"filed years={','.join(years)}", "regnskapsregisteret_copies_api")
            builder.add_claim("financials.filed_years", years, [ev], section="annual_accounts", extraction_method="regnskapsregisteret_copies_api")

    # Leadership.
    roles_record = records.get("roles")
    if roles_record:
        state = map_state(roles_record.get("status"))
        active = [item for item in ((roles_record.get("value") or {}).get("roles") or []) if not item.get("inactive") and item.get("name")]
        if state == "available" and not active:
            state = "not_available"
        for item in active:
            value = {"name": item["name"], "role": item.get("role"), "role_code": item.get("role_code"),
                     "is_entity": bool(item.get("organisation_number"))}
            ev = _official_evidence(builder, roles_record, f"{item.get('role')}: {item['name']}", "registry_roles_api")
            builder.add_claim("leadership.role", value, [ev], identity=[item["name"], item.get("role_code")],
                              effective_at=item.get("last_changed"), section="leadership", extraction_method="registry_roles_api")
        sections["leadership"] = {"state": state, "count": len(active)}

    # Workplaces.
    locations = records.get("locations")
    if locations:
        state = map_state(locations.get("status"))
        rows = (locations.get("value") or {}).get("locations") or [] if state == "available" else []
        if state == "available" and not rows:
            state = "not_available"
        for row in rows[:200]:
            value = {"name": row.get("name"), "subunit_organisation_number": row.get("organisation_number"),
                     "address": row.get("address"), "employees": row.get("employees")}
            ev = _official_evidence(builder, locations, f"subunit {row.get('organisation_number')} {row.get('name')}", "registry_subunits_api")
            builder.add_claim("workplace", value, [ev], identity=[row.get("organisation_number")], section="workplaces",
                              extraction_method="registry_subunits_api")
        sections["workplaces"] = {"state": state, "count": len(rows)}

    # Group.
    group = records.get("group")
    if group:
        state = map_state(group.get("status"))
        if state == "not_available":
            state = "not_applicable"  # 404 from the group endpoint means the entity is not in a registered group
        members = []
        if state == "available":
            def walk(node: Any) -> None:
                if isinstance(node, dict):
                    number = node.get("organisasjonsnummer")
                    if number and str(number) != org:
                        members.append({"organisation_number": str(number), "name": node.get("navn")})
                    for child in node.values():
                        walk(child)
                elif isinstance(node, list):
                    for child in node:
                        walk(child)
            walk(group.get("value"))
            for member in {m["organisation_number"]: m for m in members}.values():
                ev = _official_evidence(builder, group, f"group entity {member['organisation_number']} {member.get('name') or ''}", "registry_group_api")
                builder.add_claim("group.related_entity", {**member, "relation": "same_registered_group"}, [ev],
                                  identity=[member["organisation_number"]], section="group", extraction_method="registry_group_api")
            if not members:
                state = "not_available"
        sections["group"] = {"state": state, "count": len({m['organisation_number'] for m in members})}

    # Website and everything that comes from it.
    website = records.get("website") or {}
    site_value = website.get("value") or {}
    assessment = site_value.get("identity_assessment") or {}
    verified = website.get("status") == "available" and bool(assessment.get("publishable"))
    if website:
        if verified:
            sections["website"] = {
                "state": "available",
                "verification": _verification_label(assessment),
                "found_by": ("email_domain" if (website.get("discovery") or {}).get("strategy") == "email_domain_v1" else "domain_guess") if website.get("discovery") else "registry_link",
            }
        elif website.get("status") == "available":
            sections["website"] = {"state": "ambiguous", "note": "; ".join(assessment.get("reasons") or [])[:300]}
        else:
            sections["website"] = {"state": map_state(website.get("status")), "note": str(website.get("note") or "")[:300]}
            if website.get("status") == "source_error":
                errors.append({"stage": "website", "message": str(website.get("note") or "")[:300]})
    if verified:
        home_url = site_value.get("final_url") or website.get("source_url")
        home_sha = site_value.get("content_sha256")
        retrieved = website.get("retrieved_at")
        ev_site = builder.add_evidence(
            source_url=home_url, source_class="company_owned", source_type=website.get("source_type"), retrieved_at=retrieved,
            content_sha256=home_sha, claim_span="; ".join(assessment.get("reasons") or [])[:400],
            extraction_method=assessment.get("method") or "identity_gate",
        )
        builder.add_claim("official_website", home_url, [ev_site], identity=[site_value.get("registered_domain")],
                          confidence=float(assessment.get("score") or 0.9), section="website",
                          extraction_method=assessment.get("method") or "identity_gate")
        if site_value.get("description"):
            ev = builder.add_evidence(source_url=home_url, source_class="company_owned", retrieved_at=retrieved,
                                      content_sha256=home_sha, claim_span=site_value["description"][:300],
                                      extraction_method="meta_description")
            builder.add_claim("company_description", site_value["description"][:1000], [ev], identity=["description"],
                              section="website", extraction_method="meta_description")
        brand = None
        for org_node in site_value.get("structured_organisations") or []:
            name = org_node.get("name") if isinstance(org_node, dict) else None
            if isinstance(name, str) and name.strip():
                brand = name.strip()
                break
        if brand:
            ev = builder.add_evidence(source_url=home_url, source_class="company_owned", retrieved_at=retrieved,
                                      content_sha256=home_sha, claim_span=f"JSON-LD Organization name: {brand}", extraction_method="json_ld_organization")
            builder.add_claim("public_brand", brand, [ev], identity=["brand"], section="website", extraction_method="json_ld_organization")
        socials = site_value.get("social_links") or []
        for link in socials:
            ev = builder.add_evidence(source_url=home_url, source_class="company_owned", retrieved_at=retrieved,
                                      content_sha256=home_sha, claim_span=f"link to {link['url']}", extraction_method="site_link_to_profile")
            builder.add_claim("company_profile", {"platform": link["platform"], "url": link["url"]}, [ev],
                              identity=[link["url"].casefold()], section="company_profiles", extraction_method="site_link_to_profile")
        sections["company_profiles"] = {"state": "available" if socials else "not_available", "count": len(socials)}

        name_tokens = set(_tokens(identity["name"]))
        jobs = news = 0
        hiring_pages = news_pages = 0
        for page in _site_pages(site_value):
            page_url = page.get("url") or home_url
            if page.get("page_kind") == "hiring":
                hiring_pages += 1
            if page.get("page_kind") == "news":
                news_pages += 1
            for job in page.get("jobs") or []:
                hiring_org = job.get("hiring_organization")
                if hiring_org and name_tokens and not (set(_tokens(hiring_org)) & name_tokens):
                    continue  # posting names a different employer
                if _names_other_entity(job.get("title"), name_tokens):
                    continue  # e.g. a subsidiary's job on the group's careers page: not this legal entity
                ev = builder.add_evidence(source_url=page_url, source_class="company_owned", retrieved_at=page.get("retrieved_at") or retrieved,
                                          content_sha256=page.get("content_sha256"), claim_span=job.get("claim_span") or job["title"],
                                          extraction_method=job.get("method") or "site_items")
                before = len(builder.claims)
                builder.add_claim(
                    "job_posting",
                    {k: job.get(k) for k in ("title", "url", "location", "date_posted", "closing_date")},
                    [ev], identity=[job.get("url"), job["title"].casefold()], confidence=0.9,
                    effective_at=job.get("date_posted"), section="hiring", extraction_method=job.get("method") or "site_items",
                )
                jobs += len(builder.claims) - before
            for item in page.get("news") or []:
                ev = builder.add_evidence(source_url=page_url, source_class="company_owned", retrieved_at=page.get("retrieved_at") or retrieved,
                                          content_sha256=page.get("content_sha256"), claim_span=item.get("claim_span") or item["title"],
                                          extraction_method=item.get("method") or "site_items", effective_at=item.get("published"))
                before = len(builder.claims)
                builder.add_claim(
                    "news_item", {"title": item["title"], "url": item["url"], "published": item["published"]},
                    [ev], identity=[item["url"]], confidence=0.9, effective_at=item["published"],
                    section="activity", extraction_method=item.get("method") or "site_items",
                )
                news += len(builder.claims) - before
        if jobs:
            sections["hiring"] = {"state": "available", "count": jobs}
        else:
            sections["hiring"] = {"state": "not_available", "count": 0,
                                  "note": "careers page checked; no listings found" if hiring_pages else "no careers page found on verified site"}
        news_dates = sorted((c["value"]["published"] for c in builder.claims if c["field"] == "news_item"), reverse=True)
        if news:
            sections["activity"] = {"state": "available", "count": news, "latest": news_dates[0] if news_dates else None}
        else:
            sections["activity"] = {"state": "not_available", "count": 0,
                                    "note": "news page checked; no dated items" if news_pages else "no news page found on verified site"}
    else:
        note = "no verified company website"
        for name in ("company_profiles", "hiring", "activity"):
            sections[name] = {"state": "not_available", "note": note}

    # Job postings from NAV's job board, matched by organisation number (company or registered subunit).
    nav = records.get("nav_jobs") or {}
    nav_jobs = ((nav.get("value") or {}).get("jobs") or []) if nav.get("status") == "available" else []
    added = 0
    for job in nav_jobs:
        ev = builder.add_evidence(
            source_url=job["url"], source_class="public_job_board", source_type="nav_job_vacancy_feed",
            retrieved_at=job.get("retrieved_at"), content_sha256=job.get("content_sha256"),
            claim_span=f"NAV ad {job.get('nav_uuid')}: employer {job.get('employer_name')} (org.nr {job.get('employer_orgnr')}) - {job['title']}",
            extraction_method="nav_feed_entry_orgnr_match", effective_at=job.get("date_posted"),
        )
        before = len(builder.claims)
        builder.add_claim(
            "job_posting",
            {**{k: job.get(k) for k in ("title", "url", "location", "date_posted", "closing_date")},
             "source": "arbeidsplassen.nav.no", "employer_orgnr": job.get("employer_orgnr")},
            [ev], identity=["nav", job.get("nav_uuid")], confidence=0.98, effective_at=job.get("date_posted"),
            section="hiring", extraction_method="nav_feed_entry_orgnr_match",
        )
        added += len(builder.claims) - before
    if added:
        site_jobs = (sections.get("hiring") or {}).get("count") if (sections.get("hiring") or {}).get("state") == "available" else 0
        sections["hiring"] = {"state": "available", "count": int(site_jobs or 0) + added,
                              "sources": [s for s, n in (("company website", site_jobs), ("arbeidsplassen.nav.no", added)) if n]}

    terminal_failed = bool(profile.get("terminal_failure"))
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "organisation_number": org,
        "run": {"run_id": run_id, "started_at": started_at, "completed_at": completed_at,
                "terminal_status": "failed" if terminal_failed else "completed"},
        "status": "failed" if terminal_failed else ("available" if builder.claims else "not_available"),
        "legal_identity": identity,
        "public_brand": next(({"name": c["value"], "state": "available"} for c in builder.claims if c["field"] == "public_brand"),
                             {"name": None, "state": "not_available"}),
        "sections": sections,
        "claims": builder.claims,
        "evidence": list(builder.evidence.values()),
        "summary": "",
        "unknowns": [],
        "refresh": {"previous_run_id": None},
        "changes": [],
        "errors": errors,
        "operations": {
            "requests": int((profile.get("run_metrics") or {}).get("requests") or 0),
            "bytes": int((profile.get("run_metrics") or {}).get("bytes") or 0),
            "runtime_ms": runtime_ms,
            "third_party_cost_usd": 0,
        },
        "attempts": profile.get("attempts") or [],
    }
    from .summary import summarize, summary_citations  # local import keeps modules small

    envelope["summary"], envelope["unknowns"] = summarize(envelope)
    envelope["summary_citations"] = summary_citations(envelope)
    return envelope


def failed_envelope(org: str, *, run_id: str, started_at: str, completed_at: str, stage: str, message: str) -> dict[str, Any]:
    """Terminal result for a company we could not process. Still a valid, scoreable row."""
    sections = {name: {"state": "failed"} for name in SECTIONS}
    return {
        "schema_version": SCHEMA_VERSION,
        "organisation_number": org,
        "run": {"run_id": run_id, "started_at": started_at, "completed_at": completed_at, "terminal_status": "failed"},
        "status": "failed",
        "legal_identity": {"organisation_number": org},
        "public_brand": {"name": None, "state": "failed"},
        "sections": sections,
        "claims": [],
        "evidence": [],
        "summary": "This company could not be processed in this run, so no facts are published. See errors.",
        "unknowns": ["All sections failed in this run"],
        "refresh": {"previous_run_id": None},
        "changes": [],
        "errors": [{"stage": stage, "message": str(message)[:500]}],
        "operations": {"requests": 0, "bytes": 0, "runtime_ms": None, "third_party_cost_usd": 0},
        "attempts": [],
    }


def validate_contract(envelopes: list[dict[str, Any]], expected_orgs: Iterable[str]) -> dict[str, Any]:
    expected = list(expected_orgs)
    orgs = [item.get("organisation_number") for item in envelopes]
    problems: list[dict[str, Any]] = []
    for item in envelopes:
        org = item.get("organisation_number")
        evidence_ids = {ev.get("id") for ev in item.get("evidence") or []}
        for ev in item.get("evidence") or []:
            if not ev.get("source_url") or not ev.get("retrieved_at"):
                problems.append({"organisation_number": org, "problem": "evidence missing source_url or retrieved_at", "id": ev.get("id")})
        for claim in item.get("claims") or []:
            if claim.get("availability") not in STATES:
                problems.append({"organisation_number": org, "problem": "bad claim availability", "claim": claim.get("claim_key")})
            if not claim.get("evidence_ids") or not set(claim["evidence_ids"]) <= evidence_ids:
                problems.append({"organisation_number": org, "problem": "claim without valid evidence", "claim": claim.get("claim_key")})
            value = claim.get("value")
            if isinstance(value, dict) and "amount" in value and value["amount"] is None:
                problems.append({"organisation_number": org, "problem": "null financial amount published", "claim": claim.get("claim_key")})
        for name, section in (item.get("sections") or {}).items():
            if section.get("state") not in STATES:
                problems.append({"organisation_number": org, "problem": f"bad state in section {name}", "state": section.get("state")})
        if item.get("status") not in STATES:
            problems.append({"organisation_number": org, "problem": "bad envelope status", "state": item.get("status")})
    checks = {
        "exact_expected_count": len(envelopes) == len(expected),
        "same_order_as_input": orgs == expected,
        "unique_organisation_numbers": len(orgs) == len(set(orgs)),
        "all_claims_have_evidence": not any(p["problem"].startswith("claim without") for p in problems),
        "all_states_valid": not any("state" in p["problem"] or "availability" in p["problem"] for p in problems),
        "no_null_financials": not any("financial" in p["problem"] for p in problems),
    }
    return {"passed": all(checks.values()) and not problems, "checks": checks, "problems": problems[:200]}
