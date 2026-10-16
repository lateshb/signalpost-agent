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


def _keys(claims: list[dict[str, Any]]) -> list[str]:
    return [c["claim_key"] for c in claims if c.get("claim_key")]


def _sentences(envelope: dict[str, Any]) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """Summary sentences, each with the claim keys that support it, plus the list of unknowns."""
    identity = envelope.get("legal_identity") or {}
    sections = envelope.get("sections") or {}
    name = identity.get("name") or f"Organisation {envelope.get('organisation_number')}"
    sentences: list[tuple[str, list[str]]] = []

    # What it does.
    industry = (identity.get("industry") or {}).get("beskrivelse") if isinstance(identity.get("industry"), dict) else None
    description_claims = _claims(envelope, "company_description")
    form = identity.get("legal_form")
    what = f"{name}{f' ({form})' if form else ''} is registered in Norway"
    if industry:
        what += f" under the industry '{industry}'"
    sentences.append((what + ".", _keys(_claims(envelope, "legal_name") + _claims(envelope, "industry"))))
    if description_claims:
        short = str(description_claims[0]["value"]).strip().split(". ")[0][:220].rstrip(".")
        sentences.append((f"Its own website describes it as: \"{short}\".", _keys(description_claims[:1])))
    if identity.get("bankrupt") or identity.get("liquidating"):
        sentences.append(("The registry flags it as bankrupt or being wound up.", _keys(_claims(envelope, "legal_name"))))

    # Where.
    address = identity.get("address") or {}
    city = address.get("poststed") or address.get("kommune")
    workplaces = (sections.get("workplaces") or {}).get("count") or 0
    if city:
        where = f"It is based in {str(city).title()}"
        if workplaces:
            where += f" and has {workplaces} registered workplace{'s' if workplaces != 1 else ''}"
        sentences.append((where + ".", _keys(_claims(envelope, "business_address") + _claims(envelope, "workplace")[:3])))

    # Who leads it.
    role_claims = [c for c in _claims(envelope, "leadership.role") if not (c.get("value") or {}).get("is_entity")]
    role_claims.sort(key=lambda c: LEAD_ROLE_ORDER.index(c["value"].get("role_code")) if c["value"].get("role_code") in LEAD_ROLE_ORDER else 99)
    people = role_claims[:2]
    if people:
        sentences.append(("Leadership on record: " + "; ".join(f"{c['value']['name']} ({c['value'].get('role') or 'role'})" for c in people) + ".",
                          _keys(people)))

    # Numbers.
    latest_year = (sections.get("annual_accounts") or {}).get("latest_period")
    latest_by_metric: dict[str, dict[str, Any]] = {}
    for claim in envelope.get("claims") or []:
        if claim["field"].startswith("financials.") and isinstance(claim["value"], dict) and claim["value"].get("year") == latest_year:
            latest_by_metric.setdefault(claim["field"].split(".", 1)[1], claim)
    parts, used = [], []
    for metric, label in (("revenue", "revenue"), ("annual_result", "annual result"), ("equity", "equity")):
        if metric in latest_by_metric:
            parts.append(f"{label} {_fmt_nok(latest_by_metric[metric]['value']['amount'])}")
            used.append(latest_by_metric[metric])
    if parts:
        sentences.append((f"Latest filed accounts ({latest_year}): " + ", ".join(parts) + ".", _keys(used)))

    # Hiring and activity.
    jobs = (sections.get("hiring") or {}).get("count") or 0
    news = (sections.get("activity") or {}).get("count") or 0
    if jobs:
        job_claims = _claims(envelope, "job_posting")
        sources = (sections.get("hiring") or {}).get("sources") or ["its own website"]
        titles = [c["value"]["title"] for c in job_claims][:2]
        sentences.append((f"It has {jobs} open job posting{'s' if jobs != 1 else ''} ({' and '.join(sources)}), e.g. {', '.join(titles)}.",
                          _keys(job_claims[:3])))
    if news:
        latest_news = (sections.get("activity") or {}).get("latest")
        news_claims = sorted(_claims(envelope, "news_item"), key=lambda c: str((c.get("value") or {}).get("published")), reverse=True)
        sentences.append((f"Its site has {news} dated news item{'s' if news != 1 else ''}, the latest from {latest_news}.", _keys(news_claims[:1])))

    # Changes.
    changes = envelope.get("changes") or []
    if changes:
        kinds: dict[str, int] = {}
        for change in changes:
            kinds[change["type"]] = kinds.get(change["type"], 0) + 1
        sentences.append(("Since the last run: " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(kinds.items())) + ".",
                          [c["claim_key"] for c in changes if c.get("claim_key")][:5]))

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
        sentences.append(("Not found or not confirmed: " + ", ".join(missing_labels) + ".", []))
    return sentences, unknowns


def summarize(envelope: dict[str, Any]) -> tuple[str, list[str]]:
    sentences, unknowns = _sentences(envelope)
    return " ".join(text for text, _ in sentences), unknowns


def summary_citations(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Each summary sentence with the claims and evidence that support it."""
    sentences, _ = _sentences(envelope)
    by_key = {c.get("claim_key"): c for c in envelope.get("claims") or []}
    out = []
    for text, keys in sentences:
        evidence_ids: list[str] = []
        for key in keys:
            for ev in (by_key.get(key) or {}).get("evidence_ids") or []:
                if ev not in evidence_ids:
                    evidence_ids.append(ev)
        out.append({"sentence": text, "claim_keys": [k for k in keys if k in by_key], "evidence_ids": evidence_ids})
    return out
