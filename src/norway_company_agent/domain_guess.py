"""Find a company website without a search API by testing a few domains built from the legal name.

A guessed domain is only a candidate. It is published only when the strict identity gate passes:
the exact org number is shown on the site, or the full legal name and the registered address both
appear and no other org number is shown on the homepage.
"""
from __future__ import annotations

import socket
import time
from typing import Any, Callable

from .evidence import evidence
from .identity import _tokens, apply_website_identity_gate
from .website import fetch_website

STRATEGY = "domain_guess_v1"
# Words that are too generic to build a domain from on their own.
GENERIC_SINGLE = {
    "bygg", "service", "eiendom", "holding", "invest", "consult", "consulting", "transport", "drift", "utvikling",
    "handel", "regnskap", "media", "data", "design", "norge", "norway", "nordic", "group", "gruppen", "partner",
    "partners", "solutions", "systems", "tech", "energi", "maskin", "elektro", "rør", "ror", "maling", "eiendommer",
}
MAX_LABEL = 40


def candidate_domains(profile: dict[str, Any]) -> list[str]:
    tokens = _tokens(profile.get("name"))
    if not tokens:
        return []
    if len(tokens) == 1 and tokens[0] in GENERIC_SINGLE:
        return []
    joined = "".join(tokens)
    hyphen = "-".join(tokens)
    out: list[str] = []
    for label in (joined, hyphen if len(tokens) > 1 else None):
        if label and 3 <= len(label) <= MAX_LABEL:
            out.append(f"{label}.no")
    if 3 <= len(joined) <= MAX_LABEL:
        out.append(f"{joined}.com")
    # Drop "holding"/"eiendom"-style suffixes: "Hansen Bygg Holding AS" -> hansenbygg.no
    trimmed = [token for token in tokens if token not in {"holding", "invest", "eiendom", "eiendommer"}]
    if trimmed and trimmed != tokens and len(trimmed) >= 1 and not (len(trimmed) == 1 and trimmed[0] in GENERIC_SINGLE):
        label = "".join(trimmed)
        if 3 <= len(label) <= MAX_LABEL:
            out.append(f"{label}.no")
    seen: list[str] = []
    for domain in out:
        if domain not in seen:
            seen.append(domain)
    return seen[:4]


def _resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except (socket.gaierror, UnicodeError, OSError):
        return False


def discover_website(
    profile: dict[str, Any],
    *,
    budget_seconds: float = 30.0,
    resolver: Callable[[str], bool] = _resolves,
    fetcher: Callable[..., tuple[dict[str, Any], dict[str, Any]]] = fetch_website,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (gated website evidence or None, attempt log)."""
    started = time.monotonic()
    attempt: dict[str, Any] = {"strategy": STRATEGY, "candidates": [], "requests": 0, "bytes": 0, "latencies_ms": []}
    for domain in candidate_domains(profile):
        if time.monotonic() - started > budget_seconds:
            attempt["candidates"].append({"domain": domain, "result": "budget_exhausted"})
            break
        if not resolver(domain):
            attempt["candidates"].append({"domain": domain, "result": "no_dns"})
            continue
        remaining = max(8.0, budget_seconds - (time.monotonic() - started))
        record, metrics = fetcher(
            f"https://{domain}/",
            timeout=10.0,
            page_limit=8,
            budget_seconds=remaining,
            source_type="discovered_company_website",
        )
        attempt["requests"] += metrics.get("requests", 0)
        attempt["bytes"] += metrics.get("bytes", 0)
        attempt["latencies_ms"].extend(metrics.get("latencies_ms", []))
        if record.get("status") != "available":
            attempt["candidates"].append({"domain": domain, "result": record.get("status"), "note": record.get("note")})
            continue
        gated = apply_website_identity_gate(profile, record, strict=True)
        assessment = gated["assessment"] or {}
        attempt["candidates"].append({
            "domain": domain,
            "result": "accepted" if assessment.get("publishable") else "rejected",
            "score": assessment.get("score"),
            "reasons": assessment.get("reasons"),
        })
        if assessment.get("publishable"):
            website = gated["website"]
            website["discovery"] = {"strategy": STRATEGY, "guessed_domain": domain}
            return website, attempt
    return None, attempt


def no_site_found_evidence(attempt: dict[str, Any]) -> dict[str, Any]:
    tried = ", ".join(item["domain"] for item in attempt.get("candidates", [])) or "none (name too generic)"
    return evidence(
        "website",
        "not_found",
        "discovered_company_website",
        "https://data.brreg.no/enhetsregisteret/api/enheter",
        note=f"No registry website; guessed domains did not verify ({tried})",
        value={"discovery_attempt": attempt},
    )
