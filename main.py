"""CLI for the PubMed search pipeline.

Usage:
    python main.py "crispr gene therapy"
    python main.py "alzheimer biomarkers" --max 5
"""

import argparse
import textwrap

from pubmed import search_articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Search PubMed via NCBI E-utilities.")
    parser.add_argument("query", help="search terms")
    parser.add_argument(
        "-n", "--max", type=int, default=10, help="max results (default: 10)"
    )
    args = parser.parse_args()

    print(f"Searching PubMed for: {args.query!r}\n")
    articles = search_articles(args.query, retmax=args.max)

    if not articles:
        print("No results found.")
        return

    for i, art in enumerate(articles, 1):
        authors = ", ".join(art.authors[:3])
        if len(art.authors) > 3:
            authors += ", et al."
        print(f"{i}. {art.title}")
        print(f"   {authors} — {art.journal} ({art.year})")
        print(f"   {art.url}")
        if art.abstract:
            snippet = textwrap.shorten(art.abstract, width=300, placeholder=" ...")
            print(f"   {snippet}")
        print()


if __name__ == "__main__":
    main()
