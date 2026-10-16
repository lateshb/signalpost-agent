from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.batch import read_inputs_tolerant  # noqa: E402
from norway_company_agent.contract import build_envelope, failed_envelope, validate_contract  # noqa: E402
from norway_company_agent.domain_guess import candidate_domains, discover_website  # noqa: E402
from norway_company_agent.evidence import evidence  # noqa: E402
from norway_company_agent.identity import assess_website_identity  # noqa: E402
from norway_company_agent.refresh_contract import apply_refresh  # noqa: E402
from norway_company_agent.site_items import extract_items, org_numbers_in_text, parse_date  # noqa: E402

ORG = "923609016"

CAREERS_HTML = """<html><head><title>Karriere | Fjordbygg</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","title":"Prosjektleder bygg",
"datePosted":"2026-09-20","validThrough":"2026-10-30","hiringOrganization":{"@type":"Organization","name":"Fjordbygg AS"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Bergen"}}}</script></head><body>
<h1>Ledige stillinger</h1>
<ul><li><a href="https://candidate.webcruiter.com/nb-no/fjordbygg/12345">Tømrer med fagbrev</a> Søknadsfrist: 01.11.2026</li>
<li><a href="/karriere/ledige-stillinger/anleggsleder">Anleggsleder Vestland</a></li>
<li><a href="/karriere">Se alle stillinger</a></li></ul></body></html>"""

NEWS_HTML = """<html><head><title>Nyheter</title></head><body>
<article><time datetime="2026-09-02">2. september 2026</time><a href="/nyheter/ny-kontrakt-med-bergen-kommune">Ny kontrakt med Bergen kommune signert</a></article>
<article><span>14. mars 2026</span><a href="/nyheter/vi-flytter-til-nye-lokaler">Vi flytter til nye lokaler på Kokstad</a></article>
<article><a href="/nyheter/udatert">En sak uten dato i det hele tatt her</a></article>
</body></html>"""


def site_profile(*, pages: list[dict], org_numbers: list[str] | None = None, title: str = "Fjordbygg AS - byggmester i Bergen",
                 status: str = "available", publishable: bool | None = None) -> dict:
    value = {
        "final_url": "https://fjordbygg.no/",
        "registered_domain": "fjordbygg.no",
        "title": title,
        "description": "Fjordbygg bygger boliger og næringsbygg på Vestlandet.",
        "main_text_excerpt": "Fjordbygg AS er en byggmesterbedrift med 40 ansatte. " * 3,
        "identity_text_excerpt": "Fjordbygg AS, Kokstadvegen 1, 5257 Kokstad",
        "org_numbers_seen": org_numbers or [],
        "social_links": [{"platform": "facebook", "url": "https://facebook.com/fjordbygg"}],
        "structured_organisations": [{"@type": "Organization", "name": "Fjordbygg"}],
        "content_sha256": "b" * 64,
        "pages": pages,
    }
    return {
        "organisation_number": ORG,
        "name": "Fjordbygg AS",
        "legal_form": "AS",
        "municipality": "BERGEN",
        "employees": 40,
        "industry_code": "41.200",
        "industry_label": "Oppføring av bygninger",
        "evidence": {
            "registry": evidence("registry", "available", "official_registry_bulk", "https://data.brreg.no/x", content_sha256="a" * 64,
                                 value={"forretningsadresse.adresse": "Kokstadvegen 1", "forretningsadresse.postnummer": "5257",
                                        "forretningsadresse.poststed": "KOKSTAD"}),
            "financials": evidence("financials", "available", "official_annual_accounts", "https://data.brreg.no/regnskap", content_sha256="c" * 64,
                                   value={"records": [{"period": {"fraDato": "2025-01-01", "tilDato": "2025-12-31"}, "currency": "NOK",
                                                       "revenue": 52000000, "annual_result": 3100000, "assets": None, "account_type": "SELSKAP"}]}),
            "roles": evidence("roles", "available", "official_roles", "https://data.brreg.no/roller", content_sha256="d" * 64,
                              value={"roles": [{"name": "Kari Nordmann", "role": "Daglig leder", "role_code": "DAGL", "inactive": False},
                                               {"name": "Old Person", "role": "Styremedlem", "role_code": "MEDL", "inactive": True}]}),
            "locations": evidence("locations", "not_found", "official_subunits", "https://data.brreg.no/under"),
            "website": evidence("website", status, "registry_linked_company_website", "https://fjordbygg.no/", value=value, content_sha256="b" * 64),
        },
    }


class SiteItemTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(parse_date("12.03.2025"), "2025-03-12")
        self.assertEqual(parse_date("2. september 2026"), "2026-09-02")
        self.assertEqual(parse_date("March 4, 2025"), "2025-03-04")
        self.assertIsNone(parse_date("ingen dato"))
        self.assertIsNone(parse_date("01.01.1990"))

    def test_jobs_from_jsonld_ats_and_careers_links(self):
        import extruct
        structured = extruct.extract(CAREERS_HTML, base_url="https://fjordbygg.no/karriere", syntaxes=["json-ld"])
        items = extract_items(CAREERS_HTML, "https://fjordbygg.no/karriere", structured=structured)
        self.assertEqual(items["page_kind"], "hiring")
        titles = {job["title"] for job in items["jobs"]}
        self.assertIn("Prosjektleder bygg", titles)
        self.assertIn("Tømrer med fagbrev", titles)
        self.assertIn("Anleggsleder Vestland", titles)
        self.assertNotIn("Se alle stillinger", titles)
        ats = next(job for job in items["jobs"] if job["title"] == "Tømrer med fagbrev")
        self.assertEqual(ats["closing_date"], "2026-11-01")
        jsonld = next(job for job in items["jobs"] if job["title"] == "Prosjektleder bygg")
        self.assertEqual((jsonld["location"], jsonld["date_posted"]), ("Bergen", "2026-09-20"))

    def test_news_requires_date(self):
        items = extract_items(NEWS_HTML, "https://fjordbygg.no/nyheter")
        self.assertEqual([n["published"] for n in items["news"]], ["2026-09-02", "2026-03-14"])
        self.assertFalse(any("uten dato" in n["title"] for n in items["news"]))

    def test_seo_article_markup_on_static_pages_is_not_news(self):
        html = """<html><head><title>Kontakt old</title><script type="application/ld+json">
        {"@type": "Article", "headline": "Kontakt old", "datePublished": "2015-05-28"}</script></head><body></body></html>"""
        structured = {"json-ld": [{"@type": "Article", "headline": "Kontakt old", "datePublished": "2015-05-28"}]}
        self.assertEqual(extract_items(html, "https://brandmaker.no/kontakt/", structured=structured)["news"], [])
        post = {"json-ld": [{"@type": "Article", "headline": "Nytt verksted", "datePublished": "2026-09-01"}]}
        news = extract_items(html.replace("Kontakt old", "Nytt verksted"), "https://fjordbygg.no/nyheter/nytt-verksted", structured=post)["news"]
        self.assertEqual([n["title"] for n in news], ["Nytt verksted"])

    def test_news_list_dates_come_from_each_item(self):
        html = """<html><head><title>Blog</title></head><body><div class="list">
          <a href="/blog/automated-optical-inspection">07 October 2026 Automated Optical Inspection: Catching Defects Early</a>
          <a href="/blog/automated-ic-programming">23 September 2026 Automated IC Programming: Preventing Errors</a>
          <a href="/blog/healthcare-together">Building Healthcare Solutions Together with partners</a>
          <a href="/investors">All announcements</a></div></body></html>"""
        news = {n["url"].rsplit("/", 1)[1]: n["published"] for n in extract_items(html, "https://www.kitron.com/blog")["news"]}
        self.assertEqual(news, {"automated-optical-inspection": "2026-10-07", "automated-ic-programming": "2026-09-23"})

    def test_event_dates_and_future_dates_are_not_publication_dates(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=5)).strftime("%d.%m.%Y")
        html = f"""<html><head><title>Nyheter</title></head><body>
          <li><a href="/nyheter/kundetur-2026">Opplev Andalucía på kundetur {future}</a></li>
          <li><a href="/nyheter/informasjonsmote">Invitasjon til informasjonsmøte 1. desember 2025 i Haugesund sentrum</a></li>
          <li><a href="/nyheter/nytt-kontor">Nytt kontor i Bergen åpnet 02.09.2026</a></li></body></html>"""
        news = {n["url"].rsplit("/", 1)[1]: n["published"] for n in extract_items(html, "https://bank.no/nyheter")["news"]}
        self.assertEqual(news, {"nytt-kontor": "2026-09-02"})

    def test_date_before_category_label_is_publication_date(self):
        html = """<html><head><title>Presse</title></head><body>
          <li><a href="/presse/artikler/2026/takmontering">Takmontering med millimeterpresisjon 25.09.2026 - Bygg</a></li></body></html>"""
        self.assertEqual([n["published"] for n in extract_items(html, "https://www.afgruppen.no/presse/")["news"]], ["2026-09-25"])

    def test_job_listing_pages_are_crawled_before_general_career_pages(self):
        from bs4 import BeautifulSoup
        from norway_company_agent.website import _priority_links

        soup = BeautifulSoup("""<a href="/karriere/mangfold/">Mangfold</a><a href="/karriere/studenter/">Studenter</a>
            <a href="/karriere/ledige-stillinger/">Ledige stillinger</a><a href="/presse/">Presse</a>""", "lxml")
        links = _priority_links("https://www.afgruppen.no/", soup, limit=2)
        self.assertEqual(links[0], "https://www.afgruppen.no/karriere/ledige-stillinger/")

    def test_career_info_pages_files_and_logins_are_not_jobs(self):
        html = """<html><head><title>Karriere</title></head><body>
          <a href="/karriere/studenter/">Student og nyutdannet</a>
          <a href="/karriere/mangfold/">Mangfold i AF</a>
          <a href="/-/media/fellesfiler/forsikring.pdf">Kort beskrivelse av reiseforsikringen</a>
          <a href="https://web103.reachmee.com/ext/I017/1104/profile?site=14">Logg inn for å se dine søknader</a>
          <a href="/om-entra/jobb-hos-entra">Jobb hos Entra</a>
          <a href="/karriere/ledige-stillinger/2026/08/af-anlegg-larling-2027">AF Anlegg - Lærling 2027</a>
          <a href="https://web103.reachmee.com/ext/I017/1104/job?site=14&job_id=1234">Prosjektleder eiendom</a>
        </body></html>"""
        titles = [j["title"] for j in extract_items(html, "https://www.afgruppen.no/karriere/")["jobs"]]
        self.assertEqual(sorted(titles), ["AF Anlegg - Lærling 2027", "Prosjektleder eiendom"])

    def test_article_meta_only_for_pages_under_a_news_section(self):
        page = """<html><head><title>{t}</title><meta property="og:type" content="article">
          <meta property="article:published_time" content="2026-01-26T10:00:00Z"><meta property="og:title" content="{t}"></head><body></body></html>"""
        self.assertEqual(extract_items(page.format(t="Ombygging og prosjektledelse"), "https://www.entra.no/produkter-og-tjenester/ombygging")["news"], [])
        self.assertEqual(extract_items(page.format(t="Nyheter fra Entra"), "https://www.entra.no/om-entra/nyheter-presse")["news"], [])
        news = extract_items(page.format(t="Multiconsult samler Oslo-kontorene"), "https://www.entra.no/om-entra/nyheter-presse/multiconsult-samler")["news"]
        self.assertEqual([n["title"] for n in news], ["Multiconsult samler Oslo-kontorene"])

    def test_org_numbers_need_a_cue(self):
        self.assertEqual(org_numbers_in_text("Fjordbygg AS · Org.nr. 923 609 016 · Tlf 55 55 55 55"), [ORG])
        self.assertEqual(org_numbers_in_text("NO 923609016 MVA"), [ORG])
        self.assertEqual(org_numbers_in_text("Pris 923 609 016 kroner"), [])


class IdentityTests(unittest.TestCase):
    def test_strict_rejects_name_only_match(self):
        profile = site_profile(pages=[])
        profile["evidence"]["registry"]["value"] = {"forretningsadresse.postnummer": "0150", "forretningsadresse.poststed": "OSLO"}
        result = assess_website_identity(profile, strict=True)
        self.assertFalse(result["publishable"])

    def test_strict_accepts_name_plus_address(self):
        result = assess_website_identity(site_profile(pages=[]), strict=True)
        self.assertTrue(result["publishable"], result["reasons"])

    def test_org_number_on_any_page_is_exact(self):
        profile = site_profile(pages=[{"url": "https://fjordbygg.no/kontakt", "org_numbers_seen": [ORG]}], title="Velkommen")
        profile["name"] = "Helt Annet Navn AS"
        result = assess_website_identity(profile, strict=True)
        self.assertTrue(result["publishable"])
        self.assertEqual(result["score"], 1.0)

    def test_other_org_number_on_homepage_blocks_publication(self):
        result = assess_website_identity(site_profile(pages=[], org_numbers=["999888777"]))
        self.assertFalse(result["publishable"])


class DomainGuessTests(unittest.TestCase):
    def test_candidates(self):
        self.assertEqual(candidate_domains({"name": "Fjord Bygg AS"}), ["fjordbygg.no", "fjord-bygg.no", "fjordbygg.com"])
        self.assertEqual(candidate_domains({"name": "Bygg AS"}), [])
        self.assertIn("hansenror.no", candidate_domains({"name": "Hansen Rør Holding AS"}))

    def test_discovery_only_accepts_verified_site(self):
        profile = site_profile(pages=[])
        good = site_profile(pages=[{"url": "https://fjordbygg.no/kontakt", "org_numbers_seen": [ORG]}])["evidence"]["website"]

        def fetcher(url, **kwargs):
            return json.loads(json.dumps(good)), {"requests": 3, "bytes": 10, "latencies_ms": [5]}

        found, attempt = discover_website(profile, resolver=lambda host: host == "fjordbygg.no", fetcher=fetcher)
        self.assertIsNotNone(found)
        self.assertEqual(found["discovery"]["guessed_domain"], "fjordbygg.no")
        self.assertEqual(attempt["candidates"][0]["result"], "accepted")

        def wrong_fetcher(url, **kwargs):
            other = json.loads(json.dumps(good))
            other["value"].update({"title": "Something else entirely", "org_numbers_seen": ["999888777"], "pages": [],
                                   "identity_text_excerpt": "", "main_text_excerpt": "Unrelated content " * 10,
                                   "structured_organisations": [], "description": ""})
            return other, {"requests": 3, "bytes": 10, "latencies_ms": [5]}

        found, attempt = discover_website(profile, resolver=lambda host: True, fetcher=wrong_fetcher)
        self.assertIsNone(found)


class EmailDomainTests(unittest.TestCase):
    def test_email_domain_first_and_generic_skipped(self):
        from norway_company_agent.domain_guess import email_domains

        profile = site_profile(pages=[])
        profile["evidence"]["registry"]["value"]["epostadresse"] = "post@Fjordbygg.no"
        self.assertEqual(email_domains(profile), ["fjordbygg.no"])
        profile["evidence"]["registry"]["value"]["epostadresse"] = "fjordbygg@gmail.com"
        self.assertEqual(email_domains(profile), [])
        profile["evidence"]["registry"]["value"]["epostadresse"] = "styret@styrerommet.no"
        self.assertEqual(email_domains(profile), [])

    def test_email_domain_site_still_needs_strict_gate(self):
        profile = site_profile(pages=[])
        profile["name"] = "Helt Annet AS"
        profile["evidence"]["registry"]["value"]["epostadresse"] = "post@fjordbygg.no"
        good = site_profile(pages=[])["evidence"]["website"]
        tried = []

        def fetcher(url, **kwargs):
            tried.append(url)
            return json.loads(json.dumps(good)), {"requests": 1, "bytes": 1, "latencies_ms": [1]}

        found, attempt = discover_website(profile, resolver=lambda host: True, fetcher=fetcher)
        self.assertEqual(tried[0], "https://fjordbygg.no/")
        self.assertIsNone(found)  # name and org number do not match this company
        self.assertEqual(attempt["candidates"][0]["strategy"], "email_domain_v1")

    def test_email_domain_found_by_label(self):
        profile = site_profile(pages=[], org_numbers=[ORG])
        profile["evidence"]["registry"]["value"]["epostadresse"] = "post@fjordbygg.no"
        good = site_profile(pages=[], org_numbers=[ORG])["evidence"]["website"]
        found, _ = discover_website(profile, resolver=lambda host: True,
                                    fetcher=lambda url, **kw: (json.loads(json.dumps(good)), {"requests": 1, "bytes": 1, "latencies_ms": []}))
        profile["evidence"]["website"] = found
        env = build_envelope(profile, run_id="t", started_at="a", completed_at="b")
        self.assertEqual(env["sections"]["website"]["found_by"], "email_domain")


class NavJobsTests(unittest.TestCase):
    def getter(self, url, headers=None, timeout=30):
        from norway_company_agent import nav_jobs as nj

        if url == nj.TOKEN_URL:
            return 200, "Current public token:\naaa.bbb.ccc\n".encode()
        if url == nj.FEED_URL:
            self.assertIn("If-Modified-Since", headers)
            items = [{"_feed_entry": {"uuid": u, "status": st, "businessName": bn, "title": "Jobb"}} for u, st, bn in
                     (("u1", "ACTIVE", "Fjordbygg AS avd Bergen"), ("u2", "ACTIVE", "Fjordbygg AS"), ("u3", "INACTIVE", "Fjordbygg AS"),
                      ("u4", "ACTIVE", "Helt Annet AS"))]
            return 200, json.dumps({"items": items, "next_url": "/api/v1/feed/p2"}).encode()
        if url.endswith("/api/v1/feed/p2"):
            self.assertNotIn("If-Modified-Since", headers)
            return 200, json.dumps({"items": [], "next_url": None}).encode()
        uuid = url.rsplit("/", 1)[1]
        orgnr = {"u1": "973000001", "u2": "999888777"}[uuid]  # u1: our subunit; u2: same name, other company
        body = {"status": "ACTIVE", "ad_content": {"title": "Tømrer " + uuid, "link": f"https://arbeidsplassen.nav.no/stillinger/stilling/{uuid}",
                "published": "2026-10-01T00:00:00+02:00", "applicationDue": "2026-10-30T00:00:00",
                "employer": {"name": "FJORDBYGG AS AVD BERGEN", "orgnr": orgnr}, "workLocations": [{"city": "BERGEN"}]}}
        return 200, json.dumps(body).encode()

    def test_only_org_number_matches_are_published(self):
        from norway_company_agent.nav_jobs import NavJobs

        nav = NavJobs(getter=self.getter).start()
        self.assertTrue(nav.wait(5))
        self.assertEqual(nav.meta["status"], "available")
        self.assertEqual(sorted(nav.ads), ["u1", "u2", "u4"])  # inactive ads dropped
        found = nav.jobs_for({ORG: ("Fjordbygg AS", {"973000001"})}, budget_seconds=10)
        jobs = found[ORG]["value"]["jobs"]
        self.assertEqual([j["nav_uuid"] for j in jobs], ["u1"])
        self.assertEqual((jobs[0]["location"], jobs[0]["date_posted"], jobs[0]["closing_date"]), ("Bergen", "2026-10-01", "2026-10-30"))
        profile = site_profile(pages=[])
        profile["evidence"]["nav_jobs"] = found[ORG]
        env = build_envelope(profile, run_id="t", started_at="a", completed_at="b")
        self.assertEqual(env["sections"]["hiring"]["state"], "available")
        nav_claim = next(c for c in env["claims"] if c["field"] == "job_posting" and c["value"].get("source") == "arbeidsplassen.nav.no")
        ev = next(e for e in env["evidence"] if e["id"] == nav_claim["evidence_ids"][0])
        self.assertEqual(ev["source_class"], "public_job_board")
        self.assertIn("973000001", ev["claim_span"])
        self.assertTrue(validate_contract([env], [ORG])["passed"])

    def test_nav_outage_on_refresh_keeps_last_jobs(self):
        from norway_company_agent.nav_jobs import NavJobs

        nav = NavJobs(getter=self.getter).start()
        nav.wait(5)
        profile = site_profile(pages=[])
        profile["evidence"]["nav_jobs"] = nav.jobs_for({ORG: ("Fjordbygg AS", {"973000001"})}, budget_seconds=10)[ORG]
        first = apply_refresh(build_envelope(profile, run_id="r1", started_at="a", completed_at="b"), None)
        del profile["evidence"]["nav_jobs"]
        second = build_envelope(profile, run_id="r2", started_at="a", completed_at="c")
        second["sections"]["hiring"]["nav_feed"] = "unavailable"
        second = apply_refresh(second, json.loads(json.dumps(first)))
        self.assertEqual([c["type"] for c in second["changes"] if c["type"] == "closed_job"], [])
        self.assertTrue(any(c.get("carried_forward") and c["value"].get("source") == "arbeidsplassen.nav.no" for c in second["claims"]))
        # when NAV answered and the ad is gone, it is reported closed
        third = apply_refresh(build_envelope(profile, run_id="r3", started_at="a", completed_at="d"), json.loads(json.dumps(first)))
        self.assertIn("closed_job", [c["type"] for c in third["changes"]])
        closed = next(c for c in third["changes"] if c["type"] == "closed_job")
        third_evidence = {e["id"] for e in third["evidence"]}
        self.assertTrue(set(closed["evidence_before"]) <= third_evidence)  # old side of the change stays verifiable

    def test_feed_unavailable_is_not_fatal(self):
        from norway_company_agent.nav_jobs import NavJobs

        nav = NavJobs(getter=lambda url, headers=None, timeout=30: (503, b"")).start()
        self.assertTrue(nav.wait(5))
        self.assertEqual(nav.meta["status"], "source_error")
        self.assertEqual(nav.jobs_for({ORG: ("Fjordbygg AS", set())}, budget_seconds=5), {})


class ContractTests(unittest.TestCase):
    def envelope(self, profile=None):
        from norway_company_agent.identity import apply_website_identity_gate
        profile = profile or site_profile(pages=[
            {"url": "https://fjordbygg.no/karriere", "page_kind": "hiring", "content_sha256": "e" * 64, "retrieved_at": "2026-10-16T00:00:00Z",
             "jobs": [{"title": "Tømrer", "url": "https://fjordbygg.no/karriere/tomrer", "method": "hiring_page_link", "claim_span": "Tømrer"},
                      {"title": "Sjåfør", "url": "https://x.no/j", "hiring_organization": "Totally Other Firm", "method": "json_ld_jobposting"}],
             "news": []},
            {"url": "https://fjordbygg.no/nyheter", "page_kind": "news", "content_sha256": "f" * 64,
             "news": [{"title": "Ny kontrakt signert", "url": "https://fjordbygg.no/nyheter/a", "published": "2026-09-02", "method": "x"}], "jobs": []},
        ], org_numbers=[ORG])
        profile["evidence"]["website"] = apply_website_identity_gate(profile, profile["evidence"]["website"])["website"]
        return build_envelope(profile, run_id="t1", started_at="2026-10-16T00:00:00Z", completed_at="2026-10-16T00:01:00Z")

    def test_envelope_sections_claims_and_validation(self):
        env = self.envelope()
        s = env["sections"]
        self.assertEqual(s["website"]["state"], "available")
        self.assertEqual(s["hiring"], {"state": "available", "count": 1})
        self.assertEqual(s["activity"]["state"], "available")
        self.assertEqual(s["workplaces"]["state"], "not_available")
        fields = [c["field"] for c in env["claims"]]
        self.assertIn("financials.revenue", fields)
        self.assertNotIn("financials.assets", fields)  # None is never published as a value
        self.assertEqual(fields.count("leadership.role"), 1)  # inactive role dropped
        self.assertTrue(validate_contract([env], [ORG])["passed"], validate_contract([env], [ORG]))
        self.assertIn("Kari Nordmann", env["summary"])
        self.assertIn("NOK 52.0 m", env["summary"])

    def test_subsidiary_jobs_on_group_site_are_not_published(self):
        profile = site_profile(pages=[{"url": "https://fjordbygg.no/karriere", "page_kind": "hiring", "content_sha256": "e" * 64,
                                       "jobs": [{"title": "Tømrer Bergen, Fjordbygg AS", "url": "https://fjordbygg.no/ledige-stillinger/a", "method": "hiring_page_link"},
                                                {"title": "Ingeniør Stavanger, Aeron AS", "url": "https://fjordbygg.no/ledige-stillinger/b", "method": "hiring_page_link"}],
                                       "news": []}], org_numbers=[ORG])
        env = self.envelope(profile)
        self.assertEqual([c["value"]["title"] for c in env["claims"] if c["field"] == "job_posting"], ["Tømrer Bergen, Fjordbygg AS"])

    def test_latest_accounts_year_when_api_lists_oldest_first(self):
        profile = site_profile(pages=[], org_numbers=[ORG])
        profile["evidence"]["financials"]["value"]["records"] = [
            {"period": {"fraDato": f"{y}-01-01", "tilDato": f"{y}-12-31"}, "currency": "NOK", "revenue": r}
            for y, r in ((2023, 243000), (2024, 230000), (2025, 212000))]
        env = self.envelope(profile)
        self.assertEqual(env["sections"]["annual_accounts"]["latest_period"], "2025")
        self.assertIn("Latest filed accounts (2025): revenue NOK 212 k", env["summary"])

    def test_unverified_site_publishes_nothing_from_it(self):
        profile = site_profile(pages=[], title="Something else", org_numbers=["999888777"])
        profile["name"] = "Helt Annet AS"
        env = self.envelope(profile)
        self.assertEqual(env["sections"]["website"]["state"], "ambiguous")
        self.assertFalse(any(c["section"] in {"website", "hiring", "activity", "company_profiles"} for c in env["claims"]))

    def test_failed_envelope_is_valid(self):
        env = failed_envelope(ORG, run_id="t", started_at="a", completed_at="b", stage="x", message="boom")
        self.assertTrue(validate_contract([env], [ORG])["passed"])

    def test_refresh_idempotent_and_carry_forward(self):
        first = apply_refresh(self.envelope(), None)
        second = apply_refresh(self.envelope(), json.loads(json.dumps(first)))
        self.assertEqual(second["changes"], [])
        failed_site = self.envelope()
        failed_site["claims"] = [c for c in failed_site["claims"] if c["section"] not in {"hiring", "activity", "website", "company_profiles"}]
        failed_site["sections"]["hiring"] = {"state": "failed"}
        third = apply_refresh(failed_site, json.loads(json.dumps(first)))
        self.assertTrue(any(c.get("carried_forward") and c["field"] == "job_posting" for c in third["claims"]))
        self.assertFalse(any(ch["type"] == "closed_job" for ch in third["changes"]))
        no_jobs = self.envelope()
        no_jobs["claims"] = [c for c in no_jobs["claims"] if c["field"] != "job_posting"]
        no_jobs["sections"]["hiring"] = {"state": "not_available"}
        fourth = apply_refresh(no_jobs, json.loads(json.dumps(first)))
        self.assertEqual([ch["type"] for ch in fourth["changes"]], ["closed_job"])


class InputTests(unittest.TestCase):
    def test_tolerant_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "in.txt"
            path.write_text("organisation_number\n923609016\n923 609 016\n12345\n\n987654321\n", encoding="utf-8")
            rows, issues = read_inputs_tolerant(path)
            self.assertEqual([r["organisation_number"] for r in rows], [ORG, "12345", "987654321"])
            self.assertEqual(issues["duplicates"], [ORG])
            self.assertFalse(rows[1]["valid"])
            jl = Path(directory) / "in.jsonl"
            jl.write_text('{"orgnr": "923609016"}\n{"organisation_number": 987654321}\n', encoding="utf-8")
            self.assertEqual([r["organisation_number"] for r in read_inputs_tolerant(jl)[0]], [ORG, "987654321"])

    def test_american_spelling_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            jl = Path(directory) / "in.jsonl"
            jl.write_text('{"organization_number": "923609016"}\n{"organizationNumber": 987654321}\n', encoding="utf-8")
            rows, issues = read_inputs_tolerant(jl)
            self.assertEqual([r["organisation_number"] for r in rows], [ORG, "987654321"])
            self.assertEqual(issues["invalid"], [])

    def test_unreadable_snapshot_is_not_fatal(self):
        from norway_company_agent.batch import load_bulk_profiles

        with tempfile.TemporaryDirectory() as directory:
            bulk = Path(directory) / "snapshot.jsonl"
            bulk.write_text('{"organisation_number": "923609016"}\n', encoding="utf-8")
            found, metadata = load_bulk_profiles(bulk, [ORG])
            self.assertEqual(found, {})
            self.assertEqual(metadata["missing"], [ORG])
            self.assertIn("snapshot_error", metadata)


RUNNER_HARNESS = textwrap.dedent('''
    import json, runpy, sys, time
    sys.path.insert(0, "{root}/src")
    import norway_company_agent.official as official
    import norway_company_agent.website as website
    import norway_company_agent.domain_guess as dg
    from norway_company_agent.evidence import evidence
    from norway_company_agent.http import FetchResult

    def fake_official(org, modules, fetcher=None):
        if org == "111111111":
            raise RuntimeError("simulated crash")
        if org == "222222222":
            time.sleep(30)
        recs = {{}}
        for m in modules:
            if m == "registry_live":
                recs[m] = evidence(m, "available", "official_registry_live", "https://data.brreg.no/e/" + org, content_sha256="1"*64,
                    value={{"name": "Fjordbygg AS" if org == "923609016" else "Live Only AS", "legal_form": "AS", "website": None, "business_address": {{"postnummer": "0150", "poststed": "OSLO", "adresse": ["Gate 1"]}}}})
            elif m == "financials":
                recs[m] = evidence(m, "available", "official_annual_accounts", "https://data.brreg.no/r/" + org, content_sha256="2"*64,
                    value={{"records": [{{"period": {{"fraDato": "2025-01-01", "tilDato": "2025-12-31"}}, "currency": "NOK", "revenue": 1000, "annual_result": None}}]}})
            elif m == "group":
                recs[m] = evidence(m, "not_found", "official_group_structure", "https://data.brreg.no/k/" + org)
            else:
                recs[m] = evidence(m, "source_error", "x", "https://data.brreg.no/x/" + org, note="HTTP 503")
        return recs, [FetchResult("u", 200, 5, 10)]

    def fake_site(url, **kw):
        val = {{"final_url": "https://fjordbygg.no/", "registered_domain": "fjordbygg.no", "title": "Fjordbygg AS", "description": "Bygg",
               "main_text_excerpt": "Fjordbygg AS bygger. " * 10, "org_numbers_seen": ["923609016"], "social_links": [], "structured_organisations": [],
               "content_sha256": "3"*64, "pages": [{{"url": "https://fjordbygg.no/karriere", "page_kind": "hiring", "content_sha256": "4"*64,
               "jobs": [{{"title": "Tømrer", "url": "https://fjordbygg.no/karriere/tomrer", "method": "hiring_page_link"}}], "news": []}}]}}
        return evidence("website", "available", kw.get("source_type", "registry_linked_company_website"), val["final_url"], value=val, content_sha256="3"*64), {{"requests": 4, "bytes": 1, "latencies_ms": [1]}}

    official.fetch_official_modules = fake_official
    website.fetch_website = fake_site
    dg.discover_website = lambda profile, **kw: (None, {{"strategy": "domain_guess_v1", "candidates": [], "requests": 0, "bytes": 0}})
    import norway_company_agent.nav_jobs as nav_jobs

    class FakeNav:
        def __init__(self, **kw): self.meta = {{"status": "available"}}
        def start(self): return self
        def wait(self, timeout): return True
        def jobs_for(self, companies, **kw):
            assert "923609016" in companies
            job = {{"title": "Anleggsleder", "url": "https://arbeidsplassen.nav.no/stillinger/stilling/u1", "location": "Bergen",
                   "date_posted": "2026-10-01", "closing_date": "2026-10-30", "employer_name": "FJORDBYGG AS", "employer_orgnr": "923609016",
                   "nav_uuid": "u1", "content_sha256": "5"*64, "retrieved_at": "2026-10-16T00:00:00Z"}}
            return {{"923609016": {{"field": "nav_jobs", "status": "available", "value": {{"jobs": [job]}}}}}}

    nav_jobs.NavJobs = FakeNav
    sys.argv = ["run"] + sys.argv[1:]
    runpy.run_path("{root}/scripts/run_competition_batch.py", run_name="__main__")
''')


class RunnerEndToEndTests(unittest.TestCase):
    def test_runner_always_returns_one_envelope_per_input(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / "harness.py").write_text(RUNNER_HARNESS.format(root=ROOT.as_posix()), encoding="utf-8")
            (d / "in.txt").write_text("923609016\n111111111\n222222222\n333333333\nbad-row-123\n923609016\n", encoding="utf-8")
            header = "organisasjonsnummer;navn;organisasjonsform.kode;hjemmeside;forretningsadresse.postnummer;forretningsadresse.poststed;forretningsadresse.adresse\n"
            rows = "923609016;Fjordbygg AS;AS;fjordbygg.no;5257;KOKSTAD;Kokstadvegen 1\n111111111;Crash AS;AS;;0150;OSLO;Gate\n222222222;Slow AS;AS;;0150;OSLO;Gate\n"
            (d / "bulk.csv").write_text(header + rows, encoding="utf-8")
            cmd = [sys.executable, str(d / "harness.py"), "--organisations", str(d / "in.txt"), "--bulk", str(d / "bulk.csv"),
                   "--output", str(d / "out.jsonl"), "--report", str(d / "report.json"), "--run-id", "e2e",
                   "--deadline-seconds", "6", "--html", str(d / "view.html")]
            started = __import__("time").monotonic()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            elapsed = __import__("time").monotonic() - started
            self.assertLess(elapsed, 20, "deadline must stop the run")
            envs = [json.loads(line) for line in (d / "out.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([e["organisation_number"] for e in envs], ["923609016", "111111111", "222222222", "333333333", "123"])
            by = {e["organisation_number"]: e for e in envs}
            self.assertEqual(by["923609016"]["sections"]["website"]["state"], "available")
            self.assertEqual(by["923609016"]["sections"]["hiring"]["state"], "available")
            self.assertEqual(by["923609016"]["sections"]["hiring"]["count"], 2)  # careers page + NAV
            self.assertIn("arbeidsplassen.nav.no", by["923609016"]["sections"]["hiring"]["sources"])
            self.assertEqual(by["923609016"]["sections"]["group"]["state"], "not_applicable")
            self.assertEqual(by["923609016"]["sections"]["leadership"]["state"], "failed")
            self.assertEqual(by["111111111"]["status"], "failed")
            self.assertEqual(by["222222222"]["errors"][0]["stage"], "deadline")
            self.assertEqual(by["333333333"]["legal_identity"]["name"], "Live Only AS")  # missing from snapshot -> live fallback
            self.assertEqual(by["123"]["errors"][0]["stage"], "input")
            report = json.loads((d / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["validation"]["passed"], report["validation"])
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
            self.assertIn("Fjordbygg", (d / "view.html").read_text(encoding="utf-8"))
            # refresh: same snapshot again -> no changes
            cmd2 = cmd[:]
            cmd2[cmd2.index("--output") + 1] = str(d / "out2.jsonl")
            cmd2 += ["--previous", str(d / "out.jsonl")]
            subprocess.run(cmd2, capture_output=True, text=True, timeout=60)
            envs2 = {json.loads(l)["organisation_number"]: json.loads(l) for l in (d / "out2.jsonl").read_text(encoding="utf-8").splitlines()}
            self.assertEqual(envs2["923609016"]["changes"], [])
            self.assertEqual(envs2["923609016"]["refresh"]["mode"], "diff")


class SummaryTests(unittest.TestCase):
    def test_unknowns_read_naturally(self):
        from norway_company_agent.summary import summarize

        envelope = {"organisation_number": ORG, "legal_identity": {"name": "Fjordbygg AS"},
                    "sections": {"website": {"state": "not_available"}, "hiring": {"state": "ambiguous"}}, "claims": []}
        summary, unknowns = summarize(envelope)
        self.assertEqual(unknowns, ["A verified company website: none found.",
                                    "Job postings: could not be tied to this exact company."])
        self.assertIn("Not found or not confirmed: a verified company website, job postings.", summary)


    def test_summary_sentences_cite_evidence(self):
        profile = site_profile(pages=[], org_numbers=[ORG])
        from norway_company_agent.identity import apply_website_identity_gate

        profile["evidence"]["website"] = apply_website_identity_gate(profile, profile["evidence"]["website"])["website"]
        env = build_envelope(profile, run_id="t", started_at="a", completed_at="b")
        citations = env["summary_citations"]
        self.assertEqual(" ".join(c["sentence"] for c in citations), env["summary"])
        evidence_ids = {e["id"] for e in env["evidence"]}
        factual = [c for c in citations if not c["sentence"].startswith("Not found")]
        self.assertTrue(factual)
        for citation in factual:
            self.assertTrue(citation["evidence_ids"], citation["sentence"])
            self.assertTrue(set(citation["evidence_ids"]) <= evidence_ids)


class PortabilityTests(unittest.TestCase):
    def test_operations_imports_without_unix_resource_module(self) -> None:
        import importlib
        from unittest import mock

        import norway_company_agent.operations as operations

        with mock.patch.dict(sys.modules, {"resource": None}):
            operations = importlib.reload(operations)
            self.assertIsNone(operations.peak_rss_bytes())
        importlib.reload(operations)


if __name__ == "__main__":
    unittest.main()
