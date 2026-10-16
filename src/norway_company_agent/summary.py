"""Short plain summary built only from published claims. No model, no guessing."""
from __future__ import annotations

from typing import Any

LEAD_ROLE_ORDER = ("DAGL", "LEDE", "INNH", "DTPR", "DTSO", "KOMP", "BEST")
SECTION_LABELS = {
    "annual_accounts": "filed annual accounts",
    "leadership": "registered leadership",
    "workplaces": "registered workplaces",
    "website": "a verified company website",
    "company_profiles": "company social profiles",
    "hiring": "job postings",
    "activity": "dated news or activity",
}


def _fmt_nok(amount: Any) -> str:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1e9:
        return f"{sign}NOK {value / 1e9:.1f} bn"
    if value >= 1e6:
        return f"{sign}NOK {value / 1e6:.1f} m"
    if value >= 1e3:
        return f"{sign}NOK {value / 1e3:.0f} k"
    return f"{sign}NOK {value:.0f}"


def _claims(envelope: dict[str, Any], field: str) -> list[dict[str, Any]]:
    return [claim for claim in envelope.get("claims") or [] if claim.get("field") == field]


def summarize(envelope: dict[str, Any]) -> tuple[str, list[str]]:
    identity = envelope.get("legal_identity") or {}
    sections = envelope.get("sections") or {}
    name = identity.get("name") or f"Organisation {envelope.get('organisation_number')}"
    sentences: list[str] = []

    # What it does.
    industry = (identity.get("industry") or {}).get("beskrivelse") if isinstance(identity.get("industry"), dict) else None
    description = next((c["value"] for c in _claims(envelope, "company_description")), None)
    form = identity.get("legal_form")
    what = f"{name}{f' ({form})' if form else ''} is registered in Norway"
    if industry:
        what += f" under the industry '{industry}'"
    sentences.append(what + ".")
    if description:
        short = description.strip().split(". ")[0][:220].rstrip(".")
        sentences.append(f"Its own website describes it as: \"{short}\".")
    if identity.get("bankrupt") or identity.get("liquidating"):
        sentences.append("The registry flags it as bankrupt or being wound up.")

    # Where.
    address = identity.get("address") or {}
    city = address.get("poststed") or address.get("kommune")
    workplaces = (sections.get("workplaces") or {}).get("count") or 0
    if city:
        where = f"It is based in {str(city).title()}"
        if workplaces:
            where += f" and has {workplaces} registered workplace{'s' if workplaces != 1 else ''}"
        sentences.append(where + ".")

    # Who leads it.
    roles = [c["value"] for c in _claims(envelope, "leadership.role")]
    roles.sort(key=lambda v: LEAD_ROLE_ORDER.index(v.get("role_code")) if v.get("role_code") in LEAD_ROLE_ORDER else 99)
    people = [r for r in roles if not r.get("is_entity")][:2]
    if people:
        sentences.append("Leadership on record: " + "; ".join(f"{p['name']} ({p.get('role') or 'role'})" for p in people) + ".")

    # Numbers.
    latest_year = (sections.get("annual_accounts") or {}).get("latest_period")
    latest_by_metric: dict[str, Any] = {}
    for claim in envelope.get("claims") or []:
        if claim["field"].startswith("financials.") and (claim["value"] or {}).get("year") == latest_year and isinstance(claim["value"], dict):
            latest_by_metric.setdefault(claim["field"].split(".", 1)[1], claim["value"]["amount"])
    if latest_by_metric:
        parts = []
        if "revenue" in latest_by_metric:
            parts.append(f"revenue {_fmt_nok(latest_by_metric['revenue'])}")
        if "annual_result" in latest_by_metric:
            parts.append(f"annual result {_fmt_nok(latest_by_metric['annual_result'])}")
        if "equity" in latest_by_metric:
            parts.append(f"equity {_fmt_nok(latest_by_metric['equity'])}")
        if parts:
            sentences.append(f"Latest filed accounts ({latest_year}): " + ", ".join(parts) + ".")

    # Hiring and activity.
    jobs = (sections.get("hiring") or {}).get("count") or 0
    news = (sections.get("activity") or {}).get("count") or 0
    if jobs:
        titles = [c["value"]["title"] for c in _claims(envelope, "job_posting")][:2]
        sentences.append(f"It lists {jobs} job posting{'s' if jobs != 1 else ''} on its own channels, e.g. {', '.join(titles)}.")
    if news:
        latest_news = (sections.get("activity") or {}).get("latest")
        sentences.append(f"Its site has {news} dated news item{'s' if news != 1 else ''}, the latest from {latest_news}.")

    # Changes.
    changes = envelope.get("changes") or []
    if changes:
        kinds: dict[str, int] = {}
        for change in changes:
            kinds[change["type"]] = kinds.get(change["type"], 0) + 1
        sentences.append("Since the last run: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(kinds.items())) + ".")

    # Unknowns.
    unknowns = []
    missing_labels = []
    for key, label in SECTION_LABELS.items():
        state = (sections.get(key) or {}).get("state")
        if state in (None, "available", "not_applicable"):
            continue
        reason = {"ambiguous": "could not be tied to this exact company", "blocked": "source blocked access",
                  "failed": "source failed in this run"}.get(state, "none found")
        missing_labels.append(label)
        unknowns.append(f"{label[0].upper()}{label[1:]}: {reason}.")
    if unknowns:
        sentences.append("Not found or not confirmed: " + ", ".join(missing_labels) + ".")
    return " ".join(sentences), unknowns
