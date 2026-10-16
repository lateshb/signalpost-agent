"""Job postings from NAV's job vacancy feed (arbeidsplassen.nav.no), matched by organisation number.

One pass over the official feed (pam-stilling-feed.nav.no) per run collects the currently active ads. A company's
name only selects candidate ads; a posting is published only when NAV's own feed entry for the ad names the employer
by an organisation number that is the company itself or one of its registered subunits.

Access: NAV's official feed API with the public token NAV publishes at /api/publicToken (no personal account).
NAV data is open (NLOD). Ads that NAV marks inactive are never published.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any, Callable

from .identity import _tokens

STRATEGY = "nav_feed_orgnr_v1"
FEED_ROOT = "https://pam-stilling-feed.nav.no"
FEED_URL = FEED_ROOT + "/api/v1/feed"
TOKEN_URL = FEED_ROOT + "/api/publicToken"
ENTRY_URL = FEED_ROOT + "/api/v1/feedentry/{uuid}"
AD_PAGE_URL = "https://arbeidsplassen.nav.no/stillinger/stilling/{uuid}"
USER_AGENT = "signalpost-agent/1.0 (company research; +https://builderr.ai/challenges/signalpost)"
MAX_CANDIDATES_PER_COMPANY = 10

Getter = Callable[..., tuple[int, bytes]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b""


def public_token(getter: Getter = _get) -> str | None:
    status, body = getter(TOKEN_URL)
    if status != 200:
        return None
    lines = [line.strip() for line in body.decode("utf-8", "replace").splitlines() if line.strip()]
    return next((line for line in lines if line.count(".") == 2 and " " not in line), None)


def _date(value: Any) -> str | None:
    text = str(value or "")[:10]
    return text if len(text) == 10 and text[4] == "-" else None


def _location(work_locations: Any) -> str | None:
    for item in work_locations or []:
        if isinstance(item, dict):
            place = item.get("city") or item.get("municipal") or item.get("county")
            if place:
                return str(place).title()
    return None


class NavJobs:
    """Loads active ads in a background thread; verifies candidates by organisation number."""

    def __init__(self, *, window_days: int = 45, time_cap_seconds: float = 900.0, getter: Getter = _get) -> None:
        self.window_days = window_days
        self.time_cap = time_cap_seconds
        self.getter = getter
        self.token: str | None = None
        self.ads: dict[str, dict[str, Any]] = {}
        self.index: dict[str, list[str]] = {}
        self.meta: dict[str, Any] = {"strategy": STRATEGY, "status": "not_started", "pages": 0, "requests": 0}
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    # -- loading -------------------------------------------------------------------------------------------
    def start(self) -> "NavJobs":
        self._thread = threading.Thread(target=self._load, name="nav-feed", daemon=True)
        self._thread.start()
        return self

    def wait(self, timeout: float) -> bool:
        return self._done.wait(max(0.0, timeout))

    def _load(self) -> None:
        started = time.monotonic()
        try:
            self.token = os.environ.get("NAV_FEED_TOKEN", "").strip() or None
            self.meta["token"] = "private (NAV_FEED_TOKEN)" if self.token else "public"
            if not self.token:
                self.token = public_token(self.getter)
                self.meta["requests"] += 1
            if not self.token:
                self.meta.update(status="source_error", note="NAV public feed token unavailable")
                return
            since = format_datetime(datetime.now(timezone.utc) - timedelta(days=self.window_days), usegmt=True)
            headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json", "If-Modified-Since": since}
            url: str | None = FEED_URL
            latest: dict[str, dict[str, Any]] = {}
            complete = False
            while url:
                if time.monotonic() - started > self.time_cap:
                    break
                status, body = self.getter(url, headers)
                self.meta["requests"] += 1
                headers.pop("If-Modified-Since", None)
                if status != 200:
                    self.meta["note"] = f"feed page failed (HTTP {status or 'no response'})"
                    break
                page = json.loads(body)
                self.meta["pages"] += 1
                for item in page.get("items") or []:
                    entry = item.get("_feed_entry") or {}
                    if entry.get("uuid"):
                        latest[entry["uuid"]] = entry
                next_url = page.get("next_url")
                if not next_url:
                    complete = True
                url = FEED_ROOT + next_url if next_url else None
            for uuid, entry in latest.items():
                if str(entry.get("status") or "").upper() != "ACTIVE":
                    continue
                self.ads[uuid] = entry
                for token in set(_tokens(entry.get("businessName"))):
                    self.index.setdefault(token, []).append(uuid)
            self.meta.update(status="available" if complete else "partial", active_ads=len(self.ads),
                             window_days=self.window_days, load_seconds=round(time.monotonic() - started, 1))
        except Exception as exc:  # the feed is optional; never break the run
            self.meta.update(status="source_error", note=f"{type(exc).__name__}: {exc}"[:200])
        finally:
            self._done.set()

    # -- matching -------------------------------------------------------------------------------------------
    def candidates(self, name: str) -> list[str]:
        tokens = _tokens(name)
        if not tokens or not self.ads:
            return []
        rarest = min(tokens, key=lambda token: len(self.index.get(token, [])))
        wanted = set(tokens)
        out = [uuid for uuid in self.index.get(rarest, []) if wanted <= set(_tokens(self.ads[uuid].get("businessName")))]
        return out[:MAX_CANDIDATES_PER_COMPANY]

    def verify(self, uuid: str, allowed_orgs: set[str]) -> dict[str, Any] | None:
        entry_url = ENTRY_URL.format(uuid=uuid)
        status, raw = self.getter(entry_url, {"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        if status != 200:
            return None
        try:
            entry = json.loads(raw)
        except ValueError:
            return None
        ad = entry.get("ad_content") or {}
        employer = ad.get("employer") or {}
        employer_org = "".join(ch for ch in str(employer.get("orgnr") or "") if ch.isdigit())
        title = str(ad.get("title") or "").strip()
        if employer_org not in allowed_orgs or str(entry.get("status") or "").upper() != "ACTIVE" or not title:
            return None
        return {
            "title": title[:200],
            "url": ad.get("link") or AD_PAGE_URL.format(uuid=uuid),
            "location": _location(ad.get("workLocations")),
            "date_posted": _date(ad.get("published")),
            "closing_date": _date(ad.get("applicationDue")) or _date(ad.get("expires")),
            "employer_name": employer.get("name"),
            "employer_orgnr": employer_org,
            "nav_uuid": uuid,
            "api_url": entry_url,
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "retrieved_at": _utc_now(),
        }

    def jobs_for(self, companies: dict[str, tuple[str, set[str]]], *, budget_seconds: float, workers: int = 8) -> dict[str, dict[str, Any]]:
        """companies: org -> (legal name, subunit org numbers). Returns org -> nav_jobs evidence record."""
        started = time.monotonic()
        if self.meta.get("status") not in {"available", "partial"} or not self.token:
            return {}
        work = [(org, uuid, {org} | subunits) for org, (name, subunits) in companies.items() for uuid in self.candidates(name)]
        self.meta["candidates_checked"] = len(work)
        found: dict[str, list[dict[str, Any]]] = {}

        def check(item: tuple[str, str, set[str]]) -> tuple[str, dict[str, Any] | None]:
            org, uuid, allowed = item
            if time.monotonic() - started > budget_seconds:
                return org, None
            return org, self.verify(uuid, allowed)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for org, job in pool.map(check, work):
                self.meta["requests"] += 1
                if job:
                    found.setdefault(org, []).append(job)
        self.meta["companies_with_jobs"] = len(found)
        return {org: {"field": "nav_jobs", "status": "available", "source_type": "public_job_board_feed", "strategy": STRATEGY,
                      "value": {"jobs": jobs}} for org, jobs in found.items()}
