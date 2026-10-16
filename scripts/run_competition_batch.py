#!/usr/bin/env python3
"""Signalpost batch runner: org numbers in, one contract envelope per company out.

    uv run python scripts/run_competition_batch.py --organisations input.jsonl --bulk enheter.csv.gz \
        --output out/envelopes.jsonl --report out/report.json --run-id day-1

Guarantees (see PRD.md):
- exactly one envelope per unique input, in input order, even if a company crashes or the deadline hits
- the output file is always written; exit code 0 when the contract validation passes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import load_bulk_profiles, read_inputs_tolerant  # noqa: E402
from norway_company_agent.contract import build_envelope, failed_envelope, validate_contract  # noqa: E402
from norway_company_agent.domain_guess import discover_website, no_site_found_evidence  # noqa: E402
from norway_company_agent.evidence import utc_now  # noqa: E402
from norway_company_agent.identity import apply_website_identity_gate  # noqa: E402
from norway_company_agent.official import accounting_obligation_assessment, fetch_official_modules  # noqa: E402
from norway_company_agent.refresh_contract import apply_refresh, load_previous  # noqa: E402
from norway_company_agent.summary import summarize  # noqa: E402
from norway_company_agent.website import fetch_website  # noqa: E402

DEFAULT_MODULES = "registry,registry_live,financials,roles,group,locations,website"
AGENT_VERSION = "signalpost-agent-2026-10-16"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
    temporary.replace(path)


def profile_from_live(org: str, records: dict) -> dict:
    """Build a profile when the company is missing from the registry snapshot."""
    live = records.get("registry_live") or {}
    value = live.get("value") or {}
    address = value.get("business_address") or {}
    industry = value.get("industry") or {}
    profile = {
        "organisation_number": org,
        "name": value.get("name") or "",
        "legal_form": value.get("legal_form") or "",
        "employees": value.get("employees"),
        "bankrupt": bool(value.get("bankrupt")),
        "liquidating": bool(value.get("liquidating")),
        "municipality": address.get("kommune") or "",
        "industry_code": industry.get("kode") or "",
        "industry_label": industry.get("beskrivelse") or "",
        "website": value.get("website") or "",
        "latest_submitted_accounts": value.get("latest_submitted_accounts") or "",
        "evidence": {},
    }
    if live.get("status") == "available":
        profile["evidence"]["registry"] = {**live, "field": "registry"}
        profile["evidence"]["accounting_obligation"] = accounting_obligation_assessment(profile)
    else:
        profile["evidence"]["registry"] = {**live, "field": "registry"} if live else {"status": "source_error", "note": "registry lookup failed"}
    return profile


def research_company(org: str, bulk_profile: dict | None, modules: list[str], *, budget: float, discovery: bool) -> dict:
    started = time.monotonic()
    fetch_modules = set(modules) - {"registry", "accounting_obligation", "website"}
    if bulk_profile is None:
        fetch_modules.add("registry_live")
    records, metrics = fetch_official_modules(org, fetch_modules)
    profile = bulk_profile if bulk_profile is not None else profile_from_live(org, records)
    profile["evidence"].update(records)
    requests = len(metrics)
    bytes_received = sum(item.bytes_received for item in metrics)
    attempts: list[dict] = []

    if "website" in modules and (profile["evidence"].get("registry") or {}).get("status") == "available":
        live_site = ((records.get("registry_live") or {}).get("value") or {}).get("website")
        site_url = profile.get("website") or live_site
        website = None
        verified = False
        remaining = lambda: max(5.0, budget - (time.monotonic() - started))  # noqa: E731
        if site_url:
            record, site_metrics = fetch_website(site_url, budget_seconds=remaining() * 0.6)
            requests += site_metrics.get("requests", 0)
            bytes_received += site_metrics.get("bytes", 0)
            website = apply_website_identity_gate(profile, record)["website"]
            verified = website.get("status") == "available" and bool(((website.get("value") or {}).get("identity_assessment") or {}).get("publishable"))
            attempts.append({"strategy": "registry_site_v2", "url": site_url, "status": website.get("status"), "verified": verified})
        if not verified and discovery and time.monotonic() - started < budget * 0.8:
            found, attempt = discover_website(profile, budget_seconds=remaining() * 0.9)
            requests += attempt.get("requests", 0)
            bytes_received += attempt.get("bytes", 0)
            attempts.append({k: v for k, v in attempt.items() if k != "latencies_ms"})
            if found:
                website = found
            elif website is None:
                website = no_site_found_evidence({k: v for k, v in attempt.items() if k != "latencies_ms"})
        if website is None:
            from norway_company_agent.evidence import evidence as make_evidence
            website = make_evidence("website", "not_found", "registry_linked_company_website",
                                    "https://data.brreg.no/enhetsregisteret/api/enheter", note="No registry website and discovery disabled")
        profile["evidence"]["website"] = website
    profile["attempts"] = attempts
    profile["run_metrics"] = {"requests": requests, "bytes": bytes_received}
    profile["runtime_ms"] = int((time.monotonic() - started) * 1000)
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Signalpost company research batch")
    parser.add_argument("--organisations", required=True, help="JSON list, JSONL or text file of organisation numbers")
    parser.add_argument("--bulk", help="Brreg entity snapshot (CSV or CSV.gz). Missing companies fall back to the live registry API")
    parser.add_argument("--output", required=True, help="Envelope JSONL output")
    parser.add_argument("--report", required=True, help="Run report JSON")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--previous", help="Previous envelope JSONL for refresh diffs (read only)")
    parser.add_argument("--html", help="Optional HTML viewer output")
    parser.add_argument("--profiles-output", help="Optional raw internal profiles JSONL (debugging)")
    parser.add_argument("--expected-count", type=int, help="Defaults to the number of unique inputs")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("SIGNALPOST_WORKERS", "24")))
    parser.add_argument("--deadline-seconds", type=float, default=float(os.environ.get("SIGNALPOST_DEADLINE_SECONDS", "3000")),
                        help="Stop starting work and write all envelopes after this many seconds")
    parser.add_argument("--company-budget-seconds", type=float, default=float(os.environ.get("SIGNALPOST_COMPANY_BUDGET_SECONDS", "75")))
    parser.add_argument("--no-discovery", action="store_true", help="Disable website discovery by domain guessing")
    parser.add_argument("--modules", default=DEFAULT_MODULES)
    args = parser.parse_args()

    run_started = time.monotonic()
    started_at = utc_now()
    modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    rows, input_issues = read_inputs_tolerant(args.organisations)
    order = [row["organisation_number"] for row in rows]
    valid = [row["organisation_number"] for row in rows if row["valid"]]
    bulk, registry_meta = load_bulk_profiles(args.bulk, valid)
    previous = load_previous(args.previous)

    results: dict[str, dict] = {}
    profiles: dict[str, dict] = {}
    runtimes: list[int] = []
    deadline = run_started + args.deadline_seconds

    def finish_time() -> str:
        return utc_now()

    for row in rows:
        if not row["valid"]:
            results[row["organisation_number"]] = failed_envelope(row["organisation_number"], run_id=args.run_id, started_at=started_at,
                                                                  completed_at=finish_time(), stage="input", message="Not a 9-digit organisation number")

    pool = ThreadPoolExecutor(max_workers=max(1, args.workers))
    futures = {
        pool.submit(research_company, org, bulk.get(org), modules, budget=args.company_budget_seconds, discovery=not args.no_discovery): org
        for org in valid
    }
    pending = set(futures)
    while pending:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            break
        done, pending = wait(pending, timeout=min(timeout, 30), return_when=FIRST_COMPLETED)
        for future in done:
            org = futures[future]
            try:
                profile = future.result()
                profiles[org] = profile
                runtimes.append(profile.get("runtime_ms") or 0)
                results[org] = build_envelope(profile, run_id=args.run_id, started_at=started_at, completed_at=finish_time(),
                                              runtime_ms=profile.get("runtime_ms"))
            except Exception as exc:  # one company must never sink the batch
                results[org] = failed_envelope(org, run_id=args.run_id, started_at=started_at, completed_at=finish_time(),
                                               stage="research", message=f"{type(exc).__name__}: {exc} | {traceback.format_exc(limit=2)[-300:]}")
            print(f"[{len(results)}/{len(order)}] {org} {results[org]['status']}", file=sys.stderr, flush=True)
    timed_out = [futures[f] for f in pending]
    for org in timed_out:
        results[org] = failed_envelope(org, run_id=args.run_id, started_at=started_at, completed_at=finish_time(),
                                       stage="deadline", message="Global run deadline reached before this company finished")
    pool.shutdown(wait=False, cancel_futures=True)

    completed_at = utc_now()
    envelopes = []
    for org in order:
        envelope = results.get(org) or failed_envelope(org, run_id=args.run_id, started_at=started_at, completed_at=completed_at,
                                                       stage="runner", message="No result produced")
        envelope["run"]["completed_at"] = envelope["run"].get("completed_at") or completed_at
        envelope["run"]["agent_version"] = AGENT_VERSION
        try:
            envelope = apply_refresh(envelope, previous.get(org))
            if envelope["status"] != "failed":
                envelope["summary"], envelope["unknowns"] = summarize(envelope)
        except Exception as exc:
            envelope.setdefault("errors", []).append({"stage": "refresh", "message": f"{type(exc).__name__}: {exc}"[:300]})
        envelopes.append(envelope)

    validation = validate_contract(envelopes, order)
    if args.expected_count is not None and args.expected_count != len(order):
        validation["checks"]["expected_count_matches_input"] = False
        validation["passed"] = False
    write_jsonl(Path(args.output), envelopes)
    if args.profiles_output:
        write_jsonl(Path(args.profiles_output), [profiles[org] for org in order if org in profiles])
    if args.html:
        from norway_company_agent.html_report import write_html
        write_html(Path(args.html), envelopes, run_id=args.run_id)

    sections = ("website", "company_profiles", "hiring", "activity", "annual_accounts", "leadership", "workplaces")
    coverage = {name: sum(1 for e in envelopes if (e.get("sections", {}).get(name) or {}).get("state") == "available") for name in sections}
    claim_counts: dict[str, int] = {}
    for envelope in envelopes:
        for claim in envelope.get("claims") or []:
            claim_counts[claim["field"]] = claim_counts.get(claim["field"], 0) + 1
    runtimes.sort()
    report = {
        "run_id": args.run_id,
        "agent_version": AGENT_VERSION,
        "started_at": started_at,
        "completed_at": completed_at,
        "wall_seconds": round(time.monotonic() - run_started, 1),
        "inputs": {"unique": len(order), "valid": len(valid), **input_issues},
        "emitted_envelopes": len(envelopes),
        "status_counts": {s: sum(1 for e in envelopes if e["status"] == s) for s in sorted({e["status"] for e in envelopes})},
        "timed_out": timed_out,
        "companies_with_section_available": coverage,
        "claims_by_field": dict(sorted(claim_counts.items())),
        "websites_found_by_domain_guess": sum(1 for e in envelopes if (e["sections"].get("website") or {}).get("found_by") == "domain_guess"),
        "changes": sum(len(e.get("changes") or []) for e in envelopes),
        "registry": registry_meta,
        "operations": {
            "requests": sum((e.get("operations") or {}).get("requests") or 0 for e in envelopes),
            "p50_company_ms": runtimes[len(runtimes) // 2] if runtimes else None,
            "p95_company_ms": runtimes[min(len(runtimes) - 1, int(len(runtimes) * 0.95))] if runtimes else None,
            "third_party_cost_usd": 0,
        },
        "validation": validation,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("run_id", "emitted_envelopes", "status_counts", "companies_with_section_available", "validation")}, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    sys.stderr.flush()
    # Leave immediately: worker threads stuck on slow sites must not delay the exit past the deadline.
    os._exit(0 if validation["passed"] else 1)


if __name__ == "__main__":
    main()
