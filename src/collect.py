"""
Phase 1 step 1: pull the 3 knowledge sources (EN + AR) and save them as
structured JSON, one record per self-contained topic (scholarship type,
fund section, or policy page). No cleaning/chunking yet -- that's collect
-> clean -> chunk, and this script is just "collect".
"""
import json
from pathlib import Path

import fitz
import requests
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (AU Scholarship Chatbot ingestion)"}


def fetch(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def collect_scholarships_page(lang: str, url: str) -> list[dict]:
    """The OSFA page renders each of the 22 scholarship/discount types as a
    Bootstrap accordion item: a title (the accordion button) and a body
    (the accordion body) that's hidden until clicked -- but present in the
    raw HTML either way, so a plain GET sees everything."""
    soup = fetch(url)
    records = []
    for item in soup.find_all("div", class_="accordion-item"):
        title_el = item.find(class_=lambda c: c and ("accordion-button" in c or "accordion-header" in c))
        body_el = item.find(class_="accordion-body")
        if not title_el or not body_el:
            continue
        records.append({
            "source": "osfa_scholarships",
            "lang": lang,
            "type": "scholarship",
            "title": title_el.get_text(strip=True),
            "body": body_el.get_text(separator="\n", strip=True),
        })
    return records


def collect_thamer_page(lang: str, url: str) -> list[dict]:
    """The Thamer Fund page is a flat h1 -> intro paragraphs -> h2 sections
    (Resources, Eligibility, Contributions, ...). Split on h2 boundaries."""
    soup = fetch(url)
    body_root = soup.find("body")
    records = []
    current_title = "Overview"
    current_parts: list[str] = []

    def flush():
        text = "\n".join(p for p in current_parts if p.strip())
        if text.strip():
            records.append({
                "source": "thamer_fund",
                "lang": lang,
                "type": "fund_section",
                "title": current_title,
                "body": text,
            })

    for el in body_root.find_all(["h1", "h2", "p", "ul", "ol"]):
        if el.name == "h2":
            flush()
            current_title = el.get_text(strip=True)
            current_parts = []
        elif el.name == "h1":
            continue
        else:
            current_parts.append(el.get_text(separator="\n", strip=True))
    flush()
    return records


def collect_policy_pdf(url: str, start_page: int, end_page: int) -> dict:
    """Pages are 0-indexed and inclusive. start_page/end_page (616-625) were
       found by manually locating the "Scholarships and Discounts Policy" section
       once, not by searching the PDF at runtime -- there is no automatic
       re-detection. The source material's "~p.615" reference is the number
       printed on the page, not the same as PyMuPDF's 0-indexed page count, since
       earlier front-matter pages (cover, table of contents) shift the offset.
       Known limitation: if this section ever moves in a future edition of the
       manual, this hardcoded range will silently extract the wrong pages."""
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    pdf_path = RAW_DIR / "policy_manual.pdf"
    pdf_path.write_bytes(r.content)

    doc = fitz.open(pdf_path)
    text = "\n".join(doc[i].get_text() for i in range(start_page, end_page + 1))
    return {
        "source": "policy_manual",
        "lang": "en",
        "type": "policy_section",
        "title": "Scholarships and Discounts Policy",
        "body": text,
    }


def main():
    all_records = []

    all_records += collect_scholarships_page(
        "en", "https://www.ajman.ac.ae/en/outreach/office-of-scholarship-financial-aid.html"
    )
    all_records += collect_scholarships_page(
        "ar", "https://www.ajman.ac.ae/ar/admissions/office-of-scholarship-financial-aid.html"
    )
    all_records += collect_thamer_page(
        "en", "https://www.ajman.ac.ae/en/thamer-fund-1"
    )
    all_records += collect_thamer_page(
        "ar", "https://www.ajman.ac.ae/ar/thamer-fund-1"
    )
    all_records.append(collect_policy_pdf(
        "https://www.ajman.ac.ae/upload/docs/Policies_and_Procedures_Manual_2025-2026.pdf",
        start_page=616, end_page=625,
    ))

    out_path = RAW_DIR / "collected.json"
    out_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Collected {len(all_records)} records -> {out_path}")
    by_source = {}
    for rec in all_records:
        key = (rec["source"], rec["lang"])
        by_source[key] = by_source.get(key, 0) + 1
    for (source, lang), count in sorted(by_source.items()):
        print(f"  {source} [{lang}]: {count} records")


if __name__ == "__main__":
    main()
