"""ds-digest 통합.

사용자 private repo `sangho24/ds-digest` — 매일 07:10 KST에 YouTube/RSS/ArXiv/HN을
Gemini 필터링한 DS 큐레이션. 출력: Telegram + Email + GitHub Pages archive.

Edith는 가장 최근 digest를 morning brief에 포함시킴. read-only.

소스:
- LocalDigestSource: 로컬 클론된 repo의 archive 파일 (JSON or markdown) 직접 읽기
- GitHubPagesDigestSource: https://sangho24.github.io/ds-digest/latest.json fetch (F14)
- HtmlArchiveDigestSource: https://sangho24.github.io/ds-digest/ HTML archive fetch (D3)

GitHubPagesDigestSource는 fetch 함수를 inject 받는다 (telegram.py / vps.relay 패턴과 동일).
이유: 테스트에서 실제 네트워크를 부르지 않고, httpx를 하드 의존성으로 만들지 않기 위해.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_PAGES_URL = "https://sangho24.github.io/ds-digest/latest.json"
_DATE_HTML_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})\.html$")
_SCORE_RE = re.compile(r"관련도\s*(?P<score>\d+(?:\.\d+)?)")


@dataclass
class DigestItem:
    title: str
    source: str  # arxiv | hn | youtube | rss | unknown
    url: str = ""
    summary: str = ""
    score: float = 0.0


class DigestSource(ABC):
    @abstractmethod
    def latest(self) -> dict:
        """{date: ISO, items: [DigestItem dict, ...], n: int}."""


def _empty_digest() -> dict:
    return {"date": None, "items": [], "n": 0}


class LocalDigestSource(DigestSource):
    """로컬 파일에서 digest 읽기 (JSON 또는 markdown).

    JSON 형식: {"date": "2026-04-28", "items": [{"title": ..., "source": ...}, ...]}
    Markdown 형식: bullet list 추출 (간단 파서)
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def latest(self) -> dict:
        if not self.path.exists():
            return _empty_digest()

        if self.path.suffix == ".json":
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return _empty_digest()
            items = data.get("items", [])
            return {
                "date": data.get("date"),
                "items": items,
                "n": len(items),
            }

        # markdown — bullet list 추출
        text = self.path.read_text(encoding="utf-8")
        items: list[dict] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                title = stripped[2:].strip()
                if title and not title.startswith("#"):
                    items.append(
                        {
                            "title": title[:200],
                            "source": "unknown",
                            "url": "",
                            "summary": "",
                            "score": 0.0,
                        }
                    )
        return {
            "date": datetime.now().date().isoformat(),
            "items": items,
            "n": len(items),
        }


def _httpx_fetch(url: str) -> str:
    """기본 fetch — urllib로 GET. 함수명은 기존 inject 계약 보존용."""
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json, text/html;q=0.9, */*;q=0.8"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        status = int(getattr(resp, "status", getattr(resp, "code", 200)))
        if status < 200 or status >= 300:
            raise RuntimeError(f"ds-digest fetch failed: HTTP {status}")
        return resp.read().decode("utf-8")


class GitHubPagesDigestSource(DigestSource):
    """ds-digest GitHub Pages 아카이브의 latest.json fetch (F14).

    ds-digest 파이프라인이 매일 07:10 KST에 GitHub Pages로 publish하는
    latest.json을 읽는다. 로컬 repo 클론이 없어도 동작 — VPS·핸드폰에서 유용.

    네트워크 실패·잘못된 JSON은 빈 결과로 graceful degrade (morning brief가
    digest 때문에 통째로 깨지면 안 되므로).
    """

    def __init__(
        self,
        url: str = DEFAULT_PAGES_URL,
        fetch_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.url = url
        self._fetch = fetch_fn or _httpx_fetch

    def latest(self) -> dict:
        try:
            body = self._fetch(self.url)
        except Exception:
            return _empty_digest()

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return _empty_digest()
        if not isinstance(data, dict):
            return _empty_digest()

        items = data.get("items", [])
        if not isinstance(items, list):
            return _empty_digest()
        return {"date": data.get("date"), "items": items, "n": len(items)}


class _ArchiveLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = _attr(attrs, "href")
        if not href:
            return
        match = _DATE_HTML_RE.search(urllib.parse.urlparse(href).path)
        if match:
            self.links.append((match.group("date"), href))


@dataclass
class _ParsedHtmlItem:
    title_parts: list[str]
    meta_parts: list[str]
    tags_parts: list[str]
    url: str = ""


class _DigestItemParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self._current: _ParsedHtmlItem | None = None
        self._item_depth = 0
        self._field: str | None = None
        self._field_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        classes = _class_tokens(attrs)

        if self._current is None:
            if tag == "div" and "item" in classes:
                self._current = _ParsedHtmlItem([], [], [])
                self._item_depth = 1
            return

        if self._field is not None:
            self._field_depth += 1

        if tag == "div":
            self._item_depth += 1

        if tag == "a" and not self._current.url:
            href = _attr(attrs, "href")
            if href and href.startswith(("http://", "https://")):
                self._current.url = unescape(href.strip())

        if self._field is None:
            if tag == "h2":
                self._start_field("title")
            elif tag == "div" and "item-meta" in classes:
                self._start_field("meta")
            elif tag == "div" and "tags" in classes:
                self._start_field("tags")

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        if self._field is not None:
            self._field_depth -= 1
            if self._field_depth <= 0:
                self._field = None
                self._field_depth = 0

        if tag.lower() == "div":
            self._item_depth -= 1
            if self._item_depth <= 0:
                self._finish_item()

    def handle_data(self, data: str) -> None:
        if self._current is None or self._field is None:
            return
        if self._field == "title":
            self._current.title_parts.append(data)
        elif self._field == "meta":
            self._current.meta_parts.append(data)
        elif self._field == "tags":
            self._current.tags_parts.append(data)

    def _start_field(self, field: str) -> None:
        self._field = field
        self._field_depth = 1

    def _finish_item(self) -> None:
        if self._current is None:
            return
        item = _build_digest_item(self._current)
        if item["title"] or item["url"]:
            self.items.append(item)
        self._current = None
        self._item_depth = 0
        self._field = None
        self._field_depth = 0


def _attr(attrs: list[tuple[str, str | None]], name: str) -> str:
    for key, value in attrs:
        if key.lower() == name and value is not None:
            return value
    return ""


def _class_tokens(attrs: list[tuple[str, str | None]]) -> set[str]:
    return set(_attr(attrs, "class").lower().split())


def _clean_text(parts: list[str]) -> str:
    return " ".join("".join(parts).split()).strip()


def _build_digest_item(parsed: _ParsedHtmlItem) -> dict:
    title = _clean_text(parsed.title_parts)
    meta = _clean_text(parsed.meta_parts)
    tags = _clean_text(parsed.tags_parts)
    source = meta.split("·", 1)[0].strip() if meta else "ds-digest"
    if not source:
        source = "ds-digest"

    score = 0.0
    score_match = _SCORE_RE.search(meta)
    if score_match:
        try:
            score = float(score_match.group("score"))
        except ValueError:
            score = 0.0

    return {
        "title": title,
        "source": source,
        "url": parsed.url,
        "summary": tags,
        "score": score,
    }


def _date_from_html_url(url: str) -> str | None:
    match = _DATE_HTML_RE.search(urllib.parse.urlparse(url).path)
    return match.group("date") if match else None


def _is_archive_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return (
        path.endswith("/")
        or path.endswith("index.html")
        or not path.endswith((".json", ".html"))
    )


def _archive_base_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if path and not path.endswith("/") and not path.lower().endswith((".json", ".html")):
        parsed = parsed._replace(path=f"{path}/")
    return urllib.parse.urlunparse(parsed)


def _latest_html_link(index_html: str, base_url: str) -> tuple[str, str] | None:
    parser = _ArchiveLinkParser()
    parser.feed(index_html)
    parser.close()
    if not parser.links:
        return None
    date, href = max(parser.links, key=lambda item: item[0])
    return date, urllib.parse.urljoin(_archive_base_url(base_url), href)


def _parse_html_digest_page(html: str, date: str | None = None) -> dict:
    parser = _DigestItemParser()
    parser.feed(html)
    parser.close()
    if not parser.items:
        return _empty_digest()
    return {"date": date, "items": parser.items, "n": len(parser.items)}


class HtmlArchiveDigestSource(DigestSource):
    """ds-digest GitHub Pages HTML archive fetch.

    현재 ds-digest public Pages는 latest.json 대신 날짜별 HTML archive를 발행한다.
    루트/index URL이면 아카이브 인덱스에서 최신 YYYY-MM-DD.html을 고른 뒤,
    날짜 HTML 페이지의 div.item 블록을 읽어 DigestItem dict로 변환한다.
    """

    def __init__(
        self,
        url: str,
        fetch_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.url = url
        self._fetch = fetch_fn or _httpx_fetch

    def latest(self) -> dict:
        try:
            page_url = self.url
            date = _date_from_html_url(page_url)

            if _is_archive_url(self.url):
                index_html = self._fetch(self.url)
                latest = _latest_html_link(index_html, self.url)
                if latest is None:
                    return _empty_digest()
                date, page_url = latest

            body = self._fetch(page_url)
            return _parse_html_digest_page(body, date)
        except Exception:
            return _empty_digest()


def get_digest_source(edith_home: Path) -> DigestSource:
    """환경에 맞는 digest source 반환.

    - EDITH_DS_DIGEST_URL=.json → GitHubPagesDigestSource
    - EDITH_DS_DIGEST_URL 루트/.html → HtmlArchiveDigestSource
    - 그 외 → LocalDigestSource (raw/digest/latest.json)

    EDITH_DS_DIGEST_LATEST(명시적 로컬 경로)는 tool 레이어에서 우선 처리됨.
    """
    url = os.environ.get("EDITH_DS_DIGEST_URL")
    if url:
        path = urllib.parse.urlparse(url).path.lower()
        if path.endswith(".json"):
            return GitHubPagesDigestSource(url)
        return HtmlArchiveDigestSource(url)
    return LocalDigestSource(edith_home / "raw" / "digest" / "latest.json")
