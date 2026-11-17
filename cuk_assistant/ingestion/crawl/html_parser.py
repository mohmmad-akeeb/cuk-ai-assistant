"""HTML content parser for CUK department pages.

Responsibilities:
- Strip the inner navigation bar boilerplate (block of #/departmentList links)
- Strip <script>, <style>, and any src/href containing data: URIs
- Extract plain text: headings/lists preserved, tables → Markdown tables
- Collect every <a href> into a links_out list with type classification
- Queue internal routes and PDFs for further fetching

Returns a ParsedHTML namedtuple.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

try:
    from bs4 import BeautifulSoup

    _BS4_OK = True
except ImportError:
    _BS4_OK = False

# Angular route pattern: #/something;id=...
_INTERNAL_ROUTE_RE = re.compile(r"^(?:https?://(?:www\.)?cukashmir\.ac\.in)?#/")
# PDF URL pattern
_PDF_RE = re.compile(r"\.pdf(\?[^\"'>]*)?$", re.IGNORECASE)
# mailto pattern
_MAILTO_RE = re.compile(r"^mailto:", re.IGNORECASE)
# External http(s) but NOT cukashmir
_EXTERNAL_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
_CUK_HOST_RE = re.compile(r"cukashmir\.ac\.in|cukapi\.disgenweb\.in", re.IGNORECASE)

# The inner nav bar in department pages is a <ul> or <div> containing many
# #/departmentList;id=... links. We identify it by having ≥ 4 such links.
_DEPT_LIST_LINK_RE = re.compile(r"#/departmentList", re.IGNORECASE)

# Whitespace cleanup
_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


@dataclass
class LinkOut:
    text: str
    href: str
    type: str  # internal_route | pdf | file | external | mailto


@dataclass
class ParsedHTML:
    text: str  # clean Markdown text
    links_out: list[LinkOut] = field(default_factory=list)
    char_count: int = 0


def _normalize_href(href: str) -> str:
    """Clean and normalize an href string.

    1. Strip leading/trailing whitespace.
    2. Remove accidental prefixes before 'http(s)://' (e.g. '1\\thttps://').
    3. URL-encode raw spaces and unsafe characters in HTTP(S) paths (spaces -> '%20').
    """
    href = href.strip()
    if not href or href.startswith(("data:", "javascript:", "#")):
        return href

    # Clean leading garbage if 'http://' or 'https://' appears later in the string
    for proto in ("https://", "http://"):
        idx = href.find(proto)
        if idx > 0:
            href = href[idx:]
            break

    if href.startswith(("http://", "https://")):
        try:
            parsed = urllib.parse.urlparse(href)
            # Encode path safely while preserving existing % and /
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


def _table_to_markdown(
    table: Any,
    links_out: list[LinkOut] | None = None,
    seen_hrefs: set[str] | None = None,
) -> str:
    """Convert a <table> BS4 element to a Markdown table string and collect links."""
    rows = table.find_all("tr")
    if not rows:
        return ""
    md_rows: list[list[str]] = []
    for tr in rows:
        cells = tr.find_all(["th", "td"])
        row_cells: list[str] = []
        for cell in cells:
            # Preserve links in cell as Markdown [text](href)
            for a in cell.find_all("a"):
                raw_href = (a.get("href") or "").strip()
                href = _normalize_href(raw_href)
                link_text = _WS_RE.sub(" ", a.get_text(" ", strip=True)).strip()
                if (
                    href
                    and not href.startswith("data:")
                    and seen_hrefs is not None
                    and href not in seen_hrefs
                ):
                    seen_hrefs.add(href)
                    if links_out is not None:
                        links_out.append(
                            LinkOut(text=link_text, href=href, type=_classify_href(href))
                        )
                if href and link_text:
                    a.replace_with(f"[{link_text}]({href})")
            cleaned = _WS_RE.sub(" ", cell.get_text(" ", strip=True)).replace("|", "\\|")
            row_cells.append(cleaned)
        md_rows.append(row_cells)

    if not md_rows:
        return ""

    # Pad all rows to same width
    width = max(len(r) for r in md_rows)
    for r in md_rows:
        while len(r) < width:
            r.append("")

    lines: list[str] = []
    lines.append("| " + " | ".join(md_rows[0]) + " |")
    lines.append("|" + "|".join(["---"] * width) + "|")
    for row in md_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _remove_inner_nav_bar(soup: Any) -> None:
    """Remove containers that consist mostly of departmentList nav links.

    Strategy: find the smallest enclosing tag that has ≥ 4 departmentList
    links as *direct* children's hrefs (not deeply nested content links).
    """
    for tag in soup.find_all(True):
        # Count direct-child <a> tags pointing to departmentList
        direct_nav_links = []
        for child in tag.children:
            if hasattr(child, "name") and child.name == "a":
                href = child.get("href") or ""
                if _DEPT_LIST_LINK_RE.search(href):
                    direct_nav_links.append(child)
            elif hasattr(child, "find_all"):
                # One level deep (e.g. <li><a>)
                for a in child.find_all("a", href=_DEPT_LIST_LINK_RE, recursive=False):
                    direct_nav_links.append(a)

        if len(direct_nav_links) >= 4 and tag.name not in ("html", "[document]", "body"):
            tag.decompose()
            return


def _extract_text_and_links(soup: Any) -> tuple[str, list[LinkOut]]:
    """Walk the soup tree, build Markdown text and collect links."""
    links_out: list[LinkOut] = []
    seen_hrefs: set[str] = set()
    parts: list[str] = []

    def _walk(node: Any) -> None:
        # NavigableString (text node) — has no .name or .children
        if not hasattr(node, "name") or node.name is None:
            text = str(node)
            stripped = _WS_RE.sub(" ", text)
            if stripped.strip():
                parts.append(stripped)
            return

        name = node.name.lower()

        # Skip invisible/noise tags entirely
        if name in ("script", "style", "noscript", "head", "meta", "link", "iframe", "svg"):
            return

        # Tables → Markdown
        if name == "table":
            parts.append("\n" + _table_to_markdown(node, links_out, seen_hrefs) + "\n")
            return

        # Headings
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            inner = _WS_RE.sub(" ", node.get_text(" ", strip=True))
            if inner.strip():
                parts.append("\n" + "#" * level + " " + inner.strip() + "\n")
            return

        # List items — recurse into children to extract text and links
        if name == "li":
            parts.append("\n- ")
            for child in node.children:
                _walk(child)
            return

        # ul/ol — recurse into children to pick up li items
        if name in ("ul", "ol"):
            parts.append("\n")
            for child in node.children:
                _walk(child)
            parts.append("\n")
            return

        # Paragraphs / divs / sections → newlines around content
        if name in (
            "p",
            "div",
            "section",
            "article",
            "blockquote",
            "header",
            "footer",
            "main",
            "aside",
        ):
            parts.append("\n")
            for child in node.children:
                _walk(child)
            parts.append("\n")
            return

        # Links → collect href
        if name == "a":
            raw_href = (node.get("href") or "").strip()
            href = _normalize_href(raw_href)
            link_text = _WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()

            # Skip data: URIs in href
            if href and not href.startswith("data:") and href not in seen_hrefs:
                seen_hrefs.add(href)
                link_type = _classify_href(href)
                links_out.append(LinkOut(text=link_text, href=href, type=link_type))

            # Still emit text
            if link_text:
                parts.append(link_text)
            return

        # Images → skip data: src entirely; emit alt text otherwise
        if name == "img":
            src = node.get("src") or ""
            if src.startswith("data:"):
                return  # strip base64 images completely
            alt = (node.get("alt") or "").strip()
            if alt:
                parts.append(f"[image: {alt}]")
            return

        # Line breaks
        if name == "br":
            parts.append("\n")
            return

        # Horizontal rules
        if name == "hr":
            parts.append("\n---\n")
            return

        # Inline formatting — just recurse
        if name in (
            "b",
            "strong",
            "em",
            "i",
            "span",
            "small",
            "sup",
            "sub",
            "u",
            "font",
            "tt",
            "code",
            "kbd",
            "samp",
            "mark",
            "del",
            "ins",
        ):
            for child in node.children:
                _walk(child)
            return

        # td / th — recurse (table handler extracts via get_text, but just in case)
        if name in ("td", "th"):
            for child in node.children:
                _walk(child)
            return

        # Everything else — recurse
        for child in node.children:
            _walk(child)

    _walk(soup)

    # Join and clean up whitespace
    raw = "".join(parts)
    raw = _MULTI_NL_RE.sub("\n\n", raw)
    raw = raw.strip()
    return raw, links_out


def parse_html(html: str) -> ParsedHTML:
    """Parse HTML content from a department page.

    Args:
        html: Raw HTML string from DepartmentDescription field.

    Returns:
        ParsedHTML with clean Markdown text, links_out list, and char_count.
    """
    if not _BS4_OK:
        raise ImportError("beautifulsoup4 is required for HTML parsing")

    if not html or not html.strip():
        return ParsedHTML(text="", char_count=0)

    soup = BeautifulSoup(html, "lxml")

    # 1. Remove <script>, <style>
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    # 2. Remove tags with data: URI src/href
    for tag in soup.find_all(True):
        for attr in ("src", "href"):
            val = tag.get(attr, "")
            if isinstance(val, str) and val.startswith("data:"):
                tag[attr] = ""

    # 3. Remove inner nav bar (block of departmentList links)
    _remove_inner_nav_bar(soup)

    # 4. Extract text and links
    text, links_out = _extract_text_and_links(soup)

    return ParsedHTML(
        text=text,
        links_out=links_out,
        char_count=len(text),
    )
