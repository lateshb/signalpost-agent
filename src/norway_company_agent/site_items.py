"""Extract dated job postings and news items from company-owned pages.

Rules:
- Structured data (JSON-LD JobPosting / Article) first, then page meta, then link heuristics.
- A news item is only kept when it has a parseable date. Undated text is never "activity".
- Job links are only taken from hiring pages, or from known applicant-tracking hosts.
- Nothing here decides company identity; the caller only publishes items from a verified site.
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup, Tag

EXTRACTOR_VERSION = "site_items_v2"

HIRING_TERMS = (
    "karriere", "career", "ledige-stillinger", "ledige stillinger", "stilling", "jobb", "jobs", "job",
    "vacanc", "rekrutter", "recruit", "work-with-us", "jobbe-hos", "jobbe hos", "bli-en-av-oss",
)
NEWS_TERMS = ("nyheter", "nyhet", "news", "aktuelt", "presse", "press", "blogg", "blog", "artikler", "articles")
# Static pages that SEO plugins often mark up as Article; never published as news.
STATIC_PAGE_TERMS = ("kontakt", "contact", "om-oss", "om oss", "about", "personvern", "privacy", "cookie",
                     "vilkar", "vilkår", "terms", "ansatte", "our-team")

ATS_HOSTS = (
    "webcruiter.no", "webcruiter.com", "jobbnorge.no", "teamtailor.com", "recman.no", "recman.page",
    "easycruit.com", "hrmanager.no", "jobylon.com", "varbi.com", "myworkdayjobs.com", "smartrecruiters.com",
    "lever.co", "greenhouse.io", "reachmee.com", "talentech.com", "cvpartner.com", "simployer.com",
    "arbeidsplassen.nav.no", "finn.no",
)
GENERIC_LINK_TEXT = {
    "ledige stillinger", "se alle stillinger", "alle stillinger", "se alle", "les mer", "les mer her", "mer",
    "apply", "apply now", "søk", "søk her", "søk nå", "søk stilling", "jobs", "job", "jobb", "karriere",
    "careers", "career", "read more", "see all", "view all", "open positions", "vacancies", "stillinger",
    "jobbe hos oss", "bli en av oss", "nyheter", "news", "aktuelt", "presse", "blogg", "blog", "her",
    "neste", "forrige", "next", "previous", "tilbake", "back", "meny", "menu", "hjem", "home",
    "all announcements", "all news", "alle nyheter", "flere nyheter", "more news", "see all news", "alle artikler",
    "investor relations", "investors", "press releases", "pressemeldinger",
}
# A job link must point at one posting: a posting segment followed by the posting's own path.
POSTING_SEGMENTS = {"ledige-stillinger", "stillinger", "stilling", "stillingsannonse", "jobs", "job", "jobb", "jobber",
                    "vacancies", "vacancy", "positions", "position", "openings", "job-openings", "utlysninger"}
NOT_A_POSTING_TEXT = ("logg inn", "login", "log in", "sign in", "dine søknader", "your applications", "jobb hos", "jobbe hos",
                      "jobb i ", "ledige stillinger", "open positions", "registrer", "register", "abonner", "subscribe")
NOT_A_POSTING_PATH = ("login", "logon", "signin", "profile", "register", "signup", "subscribe", "/-/media/", "/media/", "/files/")
FILE_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".zip")

NORWEGIAN_MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "mars": 3, "mar": 3, "april": 4, "apr": 4, "mai": 5,
    "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "november": 11, "nov": 11, "desember": 12, "des": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7, "october": 10, "oct": 10,
    "december": 12, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(NORWEGIAN_MONTHS, key=len, reverse=True))
DATE_PATTERNS = (
    re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b"),                       # 2025-03-12
    re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b"),                     # 12.03.2025
    re.compile(r"\b(\d{1,2})\.?\s+(" + _MONTH_ALT + r")\.?\s+(20\d{2})\b", re.I),  # 12. mars 2025
    re.compile(r"\b(" + _MONTH_ALT + r")\.?\s+(\d{1,2}),?\s+(20\d{2})\b", re.I),   # March 12, 2025
)
CLOSING_HINTS = ("søknadsfrist", "frist", "deadline", "closing", "apply by", "sist søknad")


def _clean(text: Any, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _valid(day: date | None) -> date | None:
    if day is None:
        return None
    if day.year < 2000 or day > _today() + timedelta(days=400):
        return None
    return day


def parse_date(value: Any) -> str | None:
    """Return an ISO date (YYYY-MM-DD) from common Norwegian/English formats, else None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        iso = datetime.fromisoformat(text.replace("Z", "+00:00"))
        day = _valid(iso.date())
        return day.isoformat() if day else None
    except ValueError:
        pass
    for index, pattern in enumerate(DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        try:
            if index == 0:
                year, month, day_num = int(match.group(1)), int(match.group(2)), int(match.group(3))
            elif index == 1:
                day_num, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            elif index == 2:
                day_num, month, year = int(match.group(1)), NORWEGIAN_MONTHS[match.group(2).casefold()], int(match.group(3))
            else:
                month, day_num, year = NORWEGIAN_MONTHS[match.group(1).casefold()], int(match.group(2)), int(match.group(3))
            day = _valid(date(year, month, day_num))
        except (ValueError, KeyError):
            continue
        if day:
            return day.isoformat()
    return None


def _static_page(url: str, title: str = "") -> bool:
    path = urllib.parse.urlparse(url).path.casefold().strip("/")
    haystack = path.split("/")[-1] + " " + title.casefold()
    return not path or any(term in haystack for term in STATIC_PAGE_TERMS)


def _segments(url: str) -> list[str]:
    return [segment for segment in urllib.parse.urlparse(url).path.casefold().split("/") if segment]


def _news_item_url(url: str) -> bool:
    """A page under a news/press/blog section, with its own path segment (not the section index)."""
    segments = _segments(url)
    return any(any(term in segment for term in NEWS_TERMS) for segment in segments[:-1]) and not _static_page(url)


def _posting_url(url: str, is_ats: bool) -> bool:
    lowered = url.casefold()
    path = urllib.parse.urlparse(lowered).path
    if path.endswith(FILE_SUFFIXES) or any(marker in lowered for marker in NOT_A_POSTING_PATH):
        return False
    if is_ats:
        return True
    segments = _segments(url)
    return any(segment in POSTING_SEGMENTS or segment.startswith("stilling") for segment in segments[:-1]) or \
        any(segment.startswith(("stilling-", "job-", "jobb-")) for segment in segments[-1:])


def _edge_date(text: str) -> str | None:
    """A date written at the start or end of a link text ("07 October 2026 Title", "Title 25.09.2026").

    A date in the middle of a title is usually an event date, not the publication date.
    """
    text = text or ""
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            tail = text[match.end():].strip()
            if match.start() <= 3 or len(tail) <= 3 or (tail[:1] in "-–|·" and len(tail) <= 40):
                parsed = parse_date(match.group(0))
                if parsed:
                    return parsed
    return None


def _not_future(date: str | None) -> str | None:
    today = datetime.now(timezone.utc).date().isoformat()
    return date if date and date <= today else None


def _dates_in(text: str) -> list[str]:
    found: list[str] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text or ""):
            parsed = parse_date(match.group(0))
            if parsed and parsed not in found:
                found.append(parsed)
    return found


def classify_page(url: str, title: str = "") -> str:
    haystack = (urllib.parse.urlparse(url).path + " " + title).casefold()
    if any(term in haystack for term in HIRING_TERMS):
        return "hiring"
    if any(term in haystack for term in NEWS_TERMS):
        return "news"
    return "other"


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _types(node: dict[str, Any]) -> set[str]:
    kind = node.get("@type")
    return {str(item) for item in (kind if isinstance(kind, list) else [kind]) if item}


def _location(value: Any) -> str | None:
    for node in _walk(value):
        address = node.get("address") if isinstance(node.get("address"), dict) else node
        locality = address.get("addressLocality") if isinstance(address, dict) else None
        if locality:
            return _clean(locality, 120)
    if isinstance(value, str):
        return _clean(value, 120)
    return None


def _host_is_ats(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host.endswith("finn.no"):
        return urllib.parse.urlparse(url).path.startswith("/job")
    return any(host == item or host.endswith("." + item) for item in ATS_HOSTS)


def _block_text(anchor: Tag) -> tuple[str, Tag | None]:
    block = anchor
    for _ in range(4):
        parent = block.parent
        if not isinstance(parent, Tag) or parent.name in {"body", "html", "main", "ul", "ol", "section"}:
            break
        block = parent
        if parent.name in {"article", "li", "tr"}:
            break
    text = _clean(block.get_text(" ", strip=True), 600)
    return text, block


def _block_date(block: Tag | None, text: str) -> str | None:
    if block is not None:
        for tag in block.select("time[datetime]"):
            parsed = parse_date(tag.get("datetime"))
            if parsed:
                return parsed
    return parse_date(text)


def _closing_date(text: str) -> str | None:
    lower = text.casefold()
    for hint in CLOSING_HINTS:
        position = lower.find(hint)
        if position >= 0:
            parsed = parse_date(text[position: position + 60])
            if parsed:
                return parsed
    return None


def extract_items(html: str, page_url: str, *, structured: dict[str, Any] | None = None, soup: BeautifulSoup | None = None) -> dict[str, Any]:
    soup = soup or BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    kind = classify_page(page_url, title)
    page_host = (urllib.parse.urlparse(page_url).hostname or "").lower()
    jobs: dict[str, dict[str, Any]] = {}
    news: dict[str, dict[str, Any]] = {}
    ats_links: set[str] = set()

    # 1. Structured data.
    for node in _walk((structured or {}).get("json-ld", [])) if structured else []:
        types = _types(node)
        if "JobPosting" in types:
            job_title = _clean(node.get("title") or node.get("name"), 200)
            if not job_title:
                continue
            url = urllib.parse.urljoin(page_url, str(node.get("url") or page_url))
            hiring_org = node.get("hiringOrganization")
            jobs[url + "#" + job_title] = {
                "title": job_title,
                "url": url,
                "location": _location(node.get("jobLocation")),
                "date_posted": parse_date(node.get("datePosted")),
                "closing_date": parse_date(node.get("validThrough")),
                "hiring_organization": _clean(hiring_org.get("name") if isinstance(hiring_org, dict) else hiring_org, 200) or None,
                "claim_span": job_title,
                "method": "json_ld_jobposting",
            }
        if types & {"NewsArticle", "BlogPosting", "Article", "PressRelease", "Report"}:
            headline = _clean(node.get("headline") or node.get("name"), 300)
            published = _not_future(parse_date(node.get("datePublished") or node.get("dateCreated")))
            url = urllib.parse.urljoin(page_url, str(node.get("url") or page_url))
            strong_type = bool(types & {"NewsArticle", "BlogPosting", "PressRelease"})
            if headline and published and not _static_page(url, headline) and (strong_type or _news_item_url(url)):
                news[url] = {"title": headline, "url": url, "published": published, "claim_span": headline, "method": "json_ld_article"}

    # 2. Article page meta (this page itself is a dated article).
    meta_time = soup.select_one('meta[property="article:published_time"], meta[name="article:published_time"], meta[itemprop="datePublished"]')
    og_type = soup.select_one('meta[property="og:type"]')
    if meta_time and _news_item_url(page_url) and (kind == "news" or (og_type and "article" in str(og_type.get("content") or "").casefold())):
        published = _not_future(parse_date(meta_time.get("content")))
        og_title = soup.select_one('meta[property="og:title"]')
        headline = _clean((og_title.get("content") if og_title else "") or title, 300)
        if published and headline and page_url not in news and not _static_page(page_url, headline):
            news[page_url] = {"title": headline, "url": page_url, "published": published, "claim_span": headline, "method": "article_meta"}

    # 3. Link heuristics.
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urllib.parse.urljoin(page_url, href).split("#", 1)[0]
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        text = _clean(anchor.get_text(" ", strip=True), 200)
        generic = text.casefold().strip(" »›>→") in GENERIC_LINK_TEXT
        same_site = (parsed.hostname or "").lower() == page_host
        is_ats = _host_is_ats(url)
        if is_ats:
            ats_links.add(url)
        if kind == "hiring" or is_ats:
            looks_like_posting = (is_ats or same_site) and _posting_url(url, is_ats) and \
                parsed.path.rstrip("/") != urllib.parse.urlparse(page_url).path.rstrip("/")
            not_posting_text = any(marker in text.casefold() for marker in NOT_A_POSTING_TEXT)
            if looks_like_posting and not generic and not not_posting_text and 6 <= len(text) <= 140:
                block_text, block = _block_text(anchor)
                key = url + "#" + text
                if key not in jobs:
                    jobs[key] = {
                        "title": text,
                        "url": url,
                        "location": None,
                        "date_posted": None,
                        "closing_date": _closing_date(block_text),
                        "hiring_organization": None,
                        "claim_span": text,
                        "method": "ats_link" if is_ats else "hiring_page_link",
                    }
        if kind == "news" and same_site and not generic and 15 <= len(text) <= 200:
            if parsed.path.rstrip("/") == urllib.parse.urlparse(page_url).path.rstrip("/"):
                continue
            segments = _segments(url)
            if _static_page(url, text) or not (len(segments) >= 2 or (segments and "-" in segments[-1])):
                continue
            published = _edge_date(text)
            if not published:
                block_text, block = _block_text(anchor)
                stamps = [parse_date(tag.get("datetime")) for tag in (block.select("time[datetime]") if block is not None else [])]
                # The link's own text was already checked; a date in the middle of it is an event date, not a publication date.
                candidates = list(dict.fromkeys([d for d in stamps if d] + _dates_in(block_text.replace(text, " "))))
                published = candidates[0] if len(candidates) == 1 else None
            published = _not_future(published)
            if published and url not in news:
                news[url] = {"title": text, "url": url, "published": published, "claim_span": text, "method": "news_page_link_with_date"}

    news_items = sorted(news.values(), key=lambda item: item["published"], reverse=True)[:20]
    job_items = list(jobs.values())[:40]
    return {
        "page_kind": kind,
        "jobs": job_items,
        "news": news_items,
        "ats_links": sorted(ats_links)[:10],
        "extractor_version": EXTRACTOR_VERSION,
    }


ORG_NUMBER_PATTERN = re.compile(r"(?<!\d)(\d{3})[\s. ]?(\d{3})[\s. ]?(\d{3})(?!\d)")


def org_numbers_in_text(text: str) -> list[str]:
    """Nine-digit numbers shown on a page, incl. '923 609 016' and 'NO 923609016 MVA'.

    Only numbers near an org-number cue are returned, so phone numbers and prices are not mistaken
    for organisation numbers.
    """
    found: list[str] = []
    lower = text.casefold()
    for match in ORG_NUMBER_PATTERN.finditer(text):
        window = lower[max(0, match.start() - 40): match.start()] + lower[match.end(): match.end() + 6]
        if any(cue in window for cue in ("org", "foretak", "mva", "no ", "vat", "enhetsreg", "reg.nr", "regnr")):
            number = "".join(match.groups())
            if number not in found:
                found.append(number)
    return found[:10]
