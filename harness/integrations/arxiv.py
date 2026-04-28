"""arxiv API 통합 (no key required).

GET https://export.arxiv.org/api/query?id_list=ID
returns Atom XML — title, abstract, authors 추출.

http_get 인자로 mock 가능 (테스트용).
"""

from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable
from xml.etree import ElementTree as ET

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
ARXIV_QUERY_URL = "https://export.arxiv.org/api/query?id_list={id}"


def parse_arxiv_id(s: str) -> str | None:
    """arxiv URL 또는 ID → 표준 ID.

    Examples:
        https://arxiv.org/abs/2412.12345 → 2412.12345
        arxiv:2412.12345v2 → 2412.12345
        2412.12345 → 2412.12345
    """
    s = s.strip()
    m = re.search(r"(\d{4}\.\d{4,5})", s)
    return m.group(1) if m else None


def fetch_arxiv_metadata(
    arxiv_id: str,
    http_get: Callable[[str], str] | None = None,
    timeout: float = 10.0,
) -> dict:
    """arxiv API → metadata dict.

    Returns:
        {id, title, abstract, authors, primary_category} or {} on parse fail.
    """
    url = ARXIV_QUERY_URL.format(id=arxiv_id)

    if http_get is None:

        def _default_get(u: str) -> str:
            with urllib.request.urlopen(u, timeout=timeout) as resp:
                return resp.read().decode("utf-8")

        http_get = _default_get

    xml_text = http_get(url)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    entry = root.find("a:entry", ATOM_NS)
    if entry is None:
        return {}

    title = (entry.findtext("a:title", "", ATOM_NS) or "").strip()
    title = re.sub(r"\s+", " ", title)
    abstract = (entry.findtext("a:summary", "", ATOM_NS) or "").strip()
    abstract = re.sub(r"\s+", " ", abstract)

    authors = []
    for a in entry.findall("a:author", ATOM_NS):
        name = a.findtext("a:name", "", ATOM_NS) or ""
        if name:
            authors.append(name.strip())

    primary_category = ""
    pc = entry.find("{http://arxiv.org/schemas/atom}primary_category")
    if pc is not None:
        primary_category = pc.get("term", "")

    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "primary_category": primary_category,
    }
