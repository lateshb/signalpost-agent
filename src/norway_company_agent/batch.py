from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .evidence import evidence, utc_now
from .official import accounting_obligation_assessment
from .sampling import iter_bulk


TERMINAL_STATES = {
    "complete",
    "not_applicable",
    "not_found",
    "blocked_policy",
    "blocked_robots",
    "source_error",
    "budget_exhausted",
    "submission_error",
}


def read_organisation_inputs(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    values: list[Any]
    if source.suffix == ".json":
        body = json.loads(text)
        values = body if isinstance(body, list) else body.get("organisation_numbers", [])
    elif source.suffix == ".jsonl":
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        values = [line.strip() for line in text.splitlines() if line.strip()]
    records = []
    for value in values:
        org = value.get("organisation_number") if isinstance(value, dict) else value
        org = "".join(character for character in str(org or "") if character.isdigit())
        if len(org) != 9:
            raise ValueError(f"Invalid Norwegian organisation number: {value!r}")
        record = {"organisation_number": org}
        if isinstance(value, dict):
            for key in ("evaluation_split", "sample_slice"):
                if value.get(key) is not None:
                    record[key] = value[key]
        records.append(record)
    orgs = [record["organisation_number"] for record in records]
    if len(orgs) != len(set(orgs)):
        raise ValueError("Organisation-number input contains duplicates")
    return records


ORG_KEYS = ("organisation_number", "organisationNumber", "organization_number", "organizationNumber", "organisasjonsnummer", "orgnr", "org_number", "org", "id")


def _org_checksum_ok(org: str) -> bool:
    weights = (3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * w for d, w in zip(org[:8], weights))
    check = 11 - (total % 11)
    check = 0 if check == 11 else check
    return check != 10 and check == int(org[8])


def read_inputs_tolerant(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read org numbers without ever raising on bad rows.

    Returns (rows, issues). Each row has organisation_number (cleaned or raw text) and valid flag.
    Duplicates are kept once, in first-seen order.
    """
    source = Path(path)
    raw_bytes = source.read_bytes()
    if raw_bytes[:2] == b"\x1f\x8b":
        import gzip as _gzip
        raw_bytes = _gzip.decompress(raw_bytes)
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    values: list[Any] = []
    stripped = text.strip()
    if stripped.startswith("[") or stripped.startswith("{") and "\n" not in stripped:
        try:
            body = json.loads(stripped)
            if isinstance(body, dict):
                body = body.get("organisation_numbers") or body.get("organisations") or body.get("companies") or [body]
            values = list(body)
        except json.JSONDecodeError:
            values = []
    if not values:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    values.append(json.loads(line))
                    continue
                except json.JSONDecodeError:
                    pass
            values.append(line.split(",")[0].split(";")[0])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    issues = {"invalid": [], "duplicates": [], "header_lines_skipped": 0}
    for value in values:
        raw = next((value.get(key) for key in ORG_KEYS if isinstance(value, dict) and value.get(key) is not None), None) if isinstance(value, dict) else value
        digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
        if not digits and isinstance(raw, str) and raw and not rows:
            issues["header_lines_skipped"] += 1  # e.g. a CSV header line
            continue
        valid = len(digits) == 9
        org = digits if valid else (digits or str(raw or ""))
        if org in seen:
            issues["duplicates"].append(org)
            continue
        seen.add(org)
        row = {"organisation_number": org, "valid": valid, "checksum_ok": valid and _org_checksum_ok(digits)}
        if not valid:
            issues["invalid"].append(str(raw)[:40])
        rows.append(row)
    return rows, issues


def load_bulk_profiles(path: str | Path | None, organisation_numbers: Iterable[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Like profiles_from_bulk, but missing companies are reported, not fatal."""
    wanted = list(organisation_numbers)
    if not path or not Path(path).exists():
        return {}, {"registry_snapshot_sha256": None, "requested": len(wanted), "selected": 0, "missing": wanted, "note": "no snapshot supplied"}
    snapshot_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    retrieved_at = utc_now()
    wanted_set = set(wanted)
    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    snapshot_error = None
    try:
        for profile in iter_bulk(path):
            scanned += 1
            org = profile["organisation_number"]
            if org not in wanted_set or org in found:
                continue
            raw = profile.pop("raw", {})
            profile["evidence"] = {
                "registry": evidence("registry", "available", "official_registry_bulk",
                                     "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv",
                                     value=raw, retrieved_at=retrieved_at, content_sha256=snapshot_sha256, source_row_key=org),
                "accounting_obligation": accounting_obligation_assessment(profile),
            }
            found[org] = profile
            if len(found) == len(wanted_set):
                break
    except Exception as exc:  # unreadable snapshot: companies not yet found fall back to the live registry
        snapshot_error = f"{type(exc).__name__}: {exc}"
    missing = [org for org in wanted if org not in found]
    metadata = {"registry_snapshot_sha256": snapshot_sha256, "registry_rows_scanned": scanned,
                "requested": len(wanted), "selected": len(found), "missing": missing}
    if snapshot_error:
        metadata["snapshot_error"] = snapshot_error
    return found, metadata


def read_organisation_numbers(path: str | Path) -> list[str]:
    return [record["organisation_number"] for record in read_organisation_inputs(path)]


def profiles_from_bulk(path: str | Path, organisation_numbers: Iterable[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    requested = list(organisation_numbers)
    wanted = set(requested)
    snapshot_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    retrieved_at = utc_now()
    found: dict[str, dict[str, Any]] = {}
    scanned = 0
    for profile in iter_bulk(path):
        scanned += 1
        org = profile["organisation_number"]
        if org not in wanted:
            continue
        raw = profile.pop("raw", {})
        profile["evidence"] = {
            "registry": evidence(
                "registry",
                "available",
                "official_registry_bulk",
                "https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv",
                value=raw,
                retrieved_at=retrieved_at,
                content_sha256=snapshot_sha256,
                source_row_key=org,
            ),
            "accounting_obligation": accounting_obligation_assessment(profile),
        }
        found[org] = profile
        if len(found) == len(wanted):
            break
    missing = [org for org in requested if org not in found]
    if missing:
        raise ValueError(f"Organisation numbers absent from registry snapshot: {missing[:10]}")
    return [found[org] for org in requested], {
        "registry_snapshot_sha256": snapshot_sha256,
        "registry_rows_scanned": scanned,
        "requested": len(requested),
        "selected": len(found),
    }


def evidence_terminal_state(record: dict[str, Any] | None) -> str:
    if not record:
        return "submission_error"
    status = record.get("status")
    if status == "available":
        return "complete"
    if status == "not_applicable":
        return "not_applicable"
    if status == "not_found":
        return "not_found"
    if status == "blocked":
        note = str(record.get("note") or "").casefold()
        return "blocked_robots" if "robot" in note else "blocked_policy"
    if status == "source_error":
        return "source_error"
    return "submission_error"


def terminal_envelope(
    profile: dict[str, Any],
    *,
    run_id: str,
    modules: Iterable[str],
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    module_states = {}
    for module in modules:
        record = profile.get("evidence", {}).get(module)
        module_states[module] = {
            "state": evidence_terminal_state(record),
            "retry_count": int((record or {}).get("retry_count") or 0),
            "final_timestamp": (record or {}).get("retrieved_at") or completed_at,
        }
    entity_state = "submission_error" if any(item["state"] == "submission_error" for item in module_states.values()) else "complete"
    return {
        "run_id": run_id,
        "organisation_number": profile["organisation_number"],
        "state": entity_state,
        "started_at": started_at,
        "completed_at": completed_at,
        "modules": module_states,
        "profile": profile,
    }


def validate_envelopes(envelopes: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    orgs = [item.get("organisation_number") for item in envelopes]
    invalid_states = [
        {"organisation_number": item.get("organisation_number"), "state": state.get("state")}
        for item in envelopes
        for state in item.get("modules", {}).values()
        if state.get("state") not in TERMINAL_STATES
    ]
    checks = {
        "exact_expected_count": len(envelopes) == expected_count,
        "unique_organisation_numbers": len(orgs) == len(set(orgs)),
        "all_entity_states_terminal": all(item.get("state") in TERMINAL_STATES for item in envelopes),
        "all_module_states_terminal": not invalid_states,
        "zero_silent_drops": len(envelopes) == expected_count and len(orgs) == len(set(orgs)),
    }
    return {"passed": all(checks.values()), "checks": checks, "invalid_states": invalid_states}


def profile_complete_for_modules(profile: dict[str, Any], modules: Iterable[str]) -> bool:
    records = profile.get("evidence", {})
    return all(module in records and records[module].get("status") != "not_fetched" for module in modules)
