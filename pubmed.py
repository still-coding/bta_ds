"""A simple PubMed search pipeline built on NCBI E-utilities.

Two-step workflow (see https://www.ncbi.nlm.nih.gov/books/NBK25500/):
    1. ESearch  -> turn a query into a list of PMIDs
    2. EFetch   -> turn PMIDs into full article records (title, authors, abstract)

Uses only the Python standard library.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# NCBI asks every client to identify itself. Override TOOL/EMAIL for your app.
TOOL = "pubmed-search"
EMAIL = "ivandevitsynpa@gmail.com"

# Politeness: 3 req/sec without an API key, 10/sec with one.
_REQUEST_INTERVAL = 0.34


@dataclass
class Article:
    pmid: str
    title: str
    abstract: str
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: str = ""

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


def _get(endpoint: str, params: dict[str, str]) -> bytes:
    """Call an E-utility endpoint and return the raw response body."""
    params = {**params, "tool": TOOL, "email": EMAIL}
    url = BASE_URL + endpoint + "?" + urllib.parse.urlencode(params)
    time.sleep(_REQUEST_INTERVAL)
    req = urllib.request.Request(url, headers={"User-Agent": TOOL})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def search(query: str, retmax: int = 20) -> list[str]:
    """ESearch: return a list of PMIDs matching the query."""
    body = _get(
        "esearch.fcgi",
        {"db": "pubmed", "term": query, "retmax": str(retmax), "retmode": "xml"},
    )
    root = ET.fromstring(body)
    return [id_el.text for id_el in root.findall(".//IdList/Id") if id_el.text]


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def fetch(pmids: list[str]) -> list[Article]:
    """EFetch: return full Article records for the given PMIDs."""
    if not pmids:
        return []
    body = _get(
        "efetch.fcgi",
        {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
    )
    root = ET.fromstring(body)
    articles: list[Article] = []
    for art in root.findall(".//PubmedArticle"):
        medline = art.find(".//MedlineCitation")
        if medline is None:
            continue
        pmid = _text(medline.find("PMID"))
        article_el = medline.find("Article")

        title = _text(article_el.find("ArticleTitle")) if article_el is not None else ""

        # An abstract can be split into labelled sections.
        abstract = " ".join(
            _text(part) for part in art.findall(".//Abstract/AbstractText")
        ).strip()

        authors = []
        for author in art.findall(".//AuthorList/Author"):
            last = _text(author.find("LastName"))
            initials = _text(author.find("Initials"))
            name = " ".join(p for p in (last, initials) if p)
            if name:
                authors.append(name)

        journal = _text(art.find(".//Journal/Title"))
        year = _text(art.find(".//Journal/JournalIssue/PubDate/Year"))

        articles.append(
            Article(
                pmid=pmid,
                title=title,
                abstract=abstract,
                authors=authors,
                journal=journal,
                year=year,
            )
        )
    return articles


def search_articles(query: str, retmax: int = 20) -> list[Article]:
    """Full pipeline: query -> PMIDs -> Article records."""
    return fetch(search(query, retmax=retmax))
