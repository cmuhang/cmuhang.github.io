#!/usr/bin/env python3
"""Update per-paper citation counts from a public Google Scholar profile."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "_data" / "citations.json"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


class ScholarProfileParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None
        self.in_title = False
        self.in_citation_cell = False
        self.title_parts: list[str] = []
        self.citation_parts: list[str] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        attr_map = dict(attrs)
        if tag == "tr" and "gsc_a_tr" in classes:
            self.current = {"detail_url": ""}
            self.title_parts = []
            self.citation_parts = []
        elif self.current is not None and tag == "a" and "gsc_a_at" in classes:
            self.in_title = True
            self.current["detail_url"] = attr_map.get("href") or ""
        elif self.current is not None and tag == "td" and "gsc_a_c" in classes:
            self.in_citation_cell = True
        elif self.current is not None and tag == "a" and self.in_citation_cell:
            self.current["cited_by_url"] = attr_map.get("href") or ""

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_citation_cell:
            self.citation_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.in_title:
            self.in_title = False
        elif tag == "td" and self.in_citation_cell:
            self.in_citation_cell = False
        elif tag == "tr" and self.current is not None:
            title = "".join(self.title_parts).strip()
            citation_text = "".join(self.citation_parts).strip()
            if title:
                self.current["title"] = title
                self.current["count"] = int(citation_text) if citation_text.isdigit() else 0
                self.rows.append(self.current)
            self.current = None


def fetch_profile(url: str) -> tuple[list[dict[str, object]], str]:
    separator = "&" if "?" in url else "?"
    request_url = f"{url}{separator}pagesize=100"
    request = Request(request_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()

    if 'id="gsc_a_b"' not in html:
        raise RuntimeError("Google Scholar did not return a public profile page")

    parser = ScholarProfileParser()
    parser.feed(html)
    if not parser.rows:
        raise RuntimeError("No publication rows were found in the Scholar profile")
    return parser.rows, final_url


def main() -> int:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rows, final_url = fetch_profile(data["source"])
    by_title = {normalize_title(str(row["title"])): row for row in rows}
    by_scholar_id: dict[str, dict[str, object]] = {}
    for row in rows:
        detail_url = urljoin(final_url, str(row["detail_url"]))
        scholar_ids = parse_qs(urlparse(detail_url).query).get("citation_for_view", [])
        if scholar_ids:
            row["scholar_id"] = scholar_ids[0]
            by_scholar_id[scholar_ids[0]] = row
    changed = False

    for key, paper in data["papers"].items():
        row = by_scholar_id.get(paper.get("scholar_id"))
        if row is None:
            row = by_title.get(normalize_title(paper["title"]))
        if row is None:
            print(f"{key}: not currently indexed; keeping stored value {paper['count']}")
            continue

        detail_url = urljoin(final_url, str(row["detail_url"]))
        cited_by_url = urljoin(final_url, str(row.get("cited_by_url") or ""))
        new_values = {
            "count": int(row["count"]),
            "indexed": True,
            "scholar_id": row.get("scholar_id"),
            "url": cited_by_url if row.get("cited_by_url") else detail_url,
        }
        if any(paper.get(field) != value for field, value in new_values.items()):
            paper.update(new_values)
            changed = True
        print(f"{key}: {new_values['count']}")

    if changed:
        data["last_updated"] = date.today().isoformat()
        DATA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Updated {DATA_FILE.relative_to(ROOT)}")
    else:
        print("Citation counts are already current")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Citation update skipped: {exc}", file=sys.stderr)
        raise SystemExit(1)
