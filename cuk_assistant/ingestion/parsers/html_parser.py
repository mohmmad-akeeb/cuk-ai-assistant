"""Offline HTML parser for raw HTML assets.

Converts pristine raw HTML into GitHub-flavored Markdown text and tables (BS4/lxml),
scrubs scripts/styles/data-URIs, and extracts hyperlinks with type classification.
"""

from __future__ import annotations

import re
import urllib.parse
import warnings
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

from cuk_assistant.ingestion.parsers.base import BaseParser, LinkOut, ParsedHTML

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

_INTERNAL_ROUTE_RE = re.compile(r"^(?:https?://(?:www\.)?cukashmir\.ac\.in)?#/")
_PDF_RE = re.compile(r"\.pdf(\?[^\"'>]*)?$", re.IGNORECASE)
_MAILTO_RE = re.compile(r"^mailto:", re.IGNORECASE)
_EXTERNAL_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
_CUK_HOST_RE = re.compile(r"cukashmir\.ac\.in|cukapi\.disgenweb\.in", re.IGNORECASE)
_DEPT_LIST_LINK_RE = re.compile(r"#/departmentList", re.IGNORECASE)

_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _normalize_href(href: str) -> str:
    href = href.strip()
    if not href or href.startswith(("data:", "javascript:", "#")):
        return href

    for proto in ("https://", "http://"):
        idx = href.find(proto)
        if idx > 0:
            href = href[idx:]
            break

    if href.startswith(("http://", "https://")):
        try:
            parsed = urllib.parse.urlparse(href)
            safe_path = urllib.parse.quote(parsed.path, safe="/%")
            href = urllib.parse.urlunparse(parsed._replace(path=safe_path))
        except Exception:
            pass
    return href


def _classify_href(href: str) -> str:
    if _MAILTO_RE.match(href):
        return "mailto"
    if _INTERNAL_ROUTE_RE.match(href):
        return "internal_route"
    if _PDF_RE.search(href):
        return "pdf"
    if _EXTERNAL_HTTP_RE.match(href):
        if _CUK_HOST_RE.search(href):
            return "file"
        return "external"
    return "file"


def _table_to_markdown(table: Any) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row_text = []
        for cell in cells:
            a_tag = cell.find("a")
            if a_tag and a_tag.get("href"):
                link_text = a_tag.get_text(strip=True) or cell.get_text(strip=True)
                href = _normalize_href(a_tag["href"])
                if link_text and href:
                    cell_text = f"[{link_text}]({href})"
                else:
                    cell_text = cell.get_text(separator=" ", strip=True)
            else:
                cell_text = cell.get_text(separator=" ", strip=True)
            row_text.append(cell_text.replace("|", "\\|").replace("\n", " "))
        rows.append(row_text)

    if not rows:
        return ""

    num_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < num_cols:
            r.append("")

    header = rows[0]
    sep = ["---"] * num_cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")

    return "\n".join(lines)


def _remove_inner_nav(soup: BeautifulSoup) -> None:
    for container in soup.find_all(["ul", "div", "nav"]):
        dept_links = [
            a for a in container.find_all("a", href=True) if _DEPT_LIST_LINK_RE.search(a["href"])
        ]
        if len(dept_links) >= 4:
            container.decompose()


def parse_html(html_str: str) -> ParsedHTML:
    """Parse raw HTML string into clean markdown and links."""
    if not html_str or not html_str.strip():
        return ParsedHTML(text="", links_out=[], char_count=0, tables_extracted=0)

    try:
        soup = BeautifulSoup(html_str, "lxml")
    except Exception:
        soup = BeautifulSoup(html_str, "html.parser")

    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    for tag in soup.find_all(True):
        for attr in ("src", "href", "data-src"):
            val = tag.get(attr, "")
            if isinstance(val, str) and val.startswith("data:"):
                del tag[attr]

    _remove_inner_nav(soup)

    links_out: list[LinkOut] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("data:"):
            continue
        norm_href = _normalize_href(href)
        text = a.get_text(separator=" ", strip=True)
        link_type = _classify_href(norm_href)
        links_out.append(LinkOut(text=text, href=norm_href, type=link_type))

    table_count = 0
    for table in soup.find_all("table"):
        table_count += 1
        md = _table_to_markdown(table)
        table.replace_with(f"\n\n{md}\n\n" if md else "")

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(heading.name[1])
        prefix = "#" * level
        heading_text = heading.get_text(separator=" ", strip=True)
        if heading_text:
            heading.replace_with(f"\n\n{prefix} {heading_text}\n\n")

    for li in soup.find_all("li"):
        li_text = li.get_text(separator=" ", strip=True)
        if li_text:
            li.replace_with(f"\n- {li_text}")

    raw_text = soup.get_text(separator="\n")
    cleaned_lines = []
    for line in raw_text.splitlines():
        line = _WS_RE.sub(" ", line).strip()
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = _MULTI_NL_RE.sub("\n\n", text).strip()

    return ParsedHTML(
        text=text,
        links_out=links_out,
        char_count=len(text),
        tables_extracted=table_count,
    )


class OfflineHtmlParser(BaseParser):
    """Offline HTML parser conforming to BaseParser protocol."""

    def parse_file(self, file_path: Path, **kwargs: Any) -> ParsedHTML:
        if not file_path.exists():
            return ParsedHTML(text="", links_out=[], char_count=0, tables_extracted=0)
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return parse_html(content)

    def parse_string(self, html_content: str) -> ParsedHTML:
        return parse_html(html_content)


__all__ = [
    "LinkOut",
    "OfflineHtmlParser",
    "ParsedHTML",
    "parse_html",
]
