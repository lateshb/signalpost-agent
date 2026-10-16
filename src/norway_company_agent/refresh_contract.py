"""Refresh for contract envelopes: diff by stable claim_key, carry forward on failure.

- Same inputs twice -> no changes (claim keys don't depend on timestamps).
- A section that failed or was blocked this run keeps last run's claims, marked carried_forward,
  so a network error never looks like "jobs closed" or "revenue gone".
- The previous file is only read, never modified.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ADDED = {
    "job_posting": "new_job", "news_item": "new_activity", "leadership.role": "new_role", "workplace": "new_location",
    "official_website": "website_found", "company_profile": "new_profile", "group.related_entity": "new_group_relation",
}
REMOVED = {
    "job_posting": "closed_job", "leadership.role": "removed_role", "workplace": "removed_location",
    "official_website": "website_lost", "company_profile": "removed_profile", "group.related_entity": "removed_group_relation",
}
IGNORE_REMOVAL = {"news_item"}  # older news scrolling off a page is not a material change
CARRY_STATES = {"failed", "blocked"}


def load_previous(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("schema_version") and row.get("organisation_number"):
            rows[str(row["organisation_number"])] = row
    return rows


def _change_type(field: str, kind: str) -> str:
    if kind == "added":
        if field.startswith("financials."):
            return "new_filing_value"
        return ADDED.get(field, f"new_{field.replace('.', '_')}")
    if kind == "removed":
        return REMOVED.get(field, f"removed_{field.replace('.', '_')}")
    if field == "company_description":
        return "changed_description"
    return f"changed_{field.replace('.', '_')}"


def apply_refresh(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    completed_at = (current.get("run") or {}).get("completed_at")
    claims = current.get("claims") or []
    if not previous:
        for claim in claims:
            claim.setdefault("first_observed_at", completed_at)
            claim["last_observed_at"] = completed_at
        current["refresh"] = {"previous_run_id": None, "mode": "first_run"}
        return current

    prev_run = previous.get("run") or {}
    prev_claims = {c["claim_key"]: c for c in previous.get("claims") or [] if c.get("claim_key")}
    prev_evidence = {e["id"]: e for e in previous.get("evidence") or [] if e.get("id")}
    prev_sections = previous.get("sections") or {}
    cur_sections = current.get("sections") or {}

    # Carry forward sections that failed this run but had data last run.
    carried_sections = [
        name for name, section in cur_sections.items()
        if section.get("state") in CARRY_STATES and (prev_sections.get(name) or {}).get("state") == "available"
    ]
    current_keys = {c["claim_key"] for c in claims}
    evidence_ids = {e["id"] for e in current.get("evidence") or []}
    for key, old in prev_claims.items():
        if old.get("section") in carried_sections and key not in current_keys:
            copy = {**old, "carried_forward": True, "last_observed_at": old.get("last_observed_at") or prev_run.get("completed_at")}
            claims.append(copy)
            current_keys.add(key)
            for ev_id in old.get("evidence_ids") or []:
                if ev_id in prev_evidence and ev_id not in evidence_ids:
                    current.setdefault("evidence", []).append(prev_evidence[ev_id])
                    evidence_ids.add(ev_id)
    for name in carried_sections:
        cur_sections[name]["carried_forward_from_run"] = prev_run.get("run_id")

    changes: list[dict[str, Any]] = []
    for claim in claims:
        if claim.get("carried_forward"):
            continue
        old = prev_claims.get(claim["claim_key"])
        claim["first_observed_at"] = (old or {}).get("first_observed_at") or ((old or {}) and prev_run.get("completed_at")) or completed_at
        claim["last_observed_at"] = completed_at
        if old is None:
            changes.append({"type": _change_type(claim["field"], "added"), "field": claim["field"], "claim_key": claim["claim_key"],
                            "before": None, "after": claim["value"], "evidence_after": claim["evidence_ids"]})
        elif json.dumps(old.get("value"), sort_keys=True, default=str) != json.dumps(claim.get("value"), sort_keys=True, default=str):
            changes.append({"type": _change_type(claim["field"], "changed"), "field": claim["field"], "claim_key": claim["claim_key"],
                            "before": old.get("value"), "after": claim["value"],
                            "evidence_before": old.get("evidence_ids"), "evidence_after": claim["evidence_ids"]})
    for key, old in prev_claims.items():
        if key in current_keys or old.get("field") in IGNORE_REMOVAL:
            continue
        section_state = (cur_sections.get(old.get("section")) or {}).get("state")
        if section_state in CARRY_STATES:
            continue
        changes.append({"type": _change_type(old["field"], "removed"), "field": old["field"], "claim_key": key,
                        "before": old.get("value"), "after": None, "evidence_before": old.get("evidence_ids")})

    material = {"new_job", "closed_job", "new_role", "removed_role", "new_location", "removed_location", "website_found",
                "website_lost", "new_filing_value", "changed_description", "new_activity"}
    for change in changes:
        change["material"] = change["type"] in material or change["type"].startswith("changed_financials")
    current["claims"] = claims
    current["changes"] = changes
    current["refresh"] = {
        "previous_run_id": prev_run.get("run_id"),
        "previous_completed_at": prev_run.get("completed_at"),
        "mode": "diff",
        "carried_forward_sections": carried_sections,
        "change_count": len(changes),
    }
    return current
