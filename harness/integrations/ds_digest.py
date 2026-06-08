"""ds-digest 통합.

사용자 private repo `sangho24/ds-digest` — 매일 07:10 KST에 YouTube/RSS/ArXiv/HN을
Gemini 필터링한 DS 큐레이션. 출력: Telegram + Email + GitHub Pages archive.

Edith는 가장 최근 digest를 morning brief에 포함시킴. read-only.

소스:
- LocalDigestSource: 로컬 클론된 repo의 archive 파일 (JSON or markdown) 직접 읽기
- GitHubPagesDigestSource: https://sangho24.github.io/ds-digest/latest.json fetch (F14)

GitHubPagesDigestSource는 fetch 함수를 inject 받는다 (telegram.py / vps.relay 패턴과 동일).
이유: 테스트에서 실제 네트워크를 부르지 않고, httpx를 하드 의존성으로 만들지 않기 위해.
"""

from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_PAGES_URL = "https://sangho24.github.io/ds-digest/latest.json"


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


class LocalDigestSource(DigestSource):
    """로컬 파일에서 digest 읽기 (JSON 또는 markdown).

    JSON 형식: {"date": "2026-04-28", "items": [{"title": ..., "source": ...}, ...]}
    Markdown 형식: bullet list 추출 (간단 파서)
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def latest(self) -> dict:
        if not self.path.exists():
            return {"date": None, "items": [], "n": 0}

        if self.path.suffix == ".json":
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"date": None, "items": [], "n": 0}
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
        headers={"Accept": "application/json"},
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
            return {"date": None, "items": [], "n": 0}

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return {"date": None, "items": [], "n": 0}
        if not isinstance(data, dict):
            return {"date": None, "items": [], "n": 0}

        items = data.get("items", [])
        if not isinstance(items, list):
            return {"date": None, "items": [], "n": 0}
        return {"date": data.get("date"), "items": items, "n": len(items)}


def get_digest_source(edith_home: Path) -> DigestSource:
    """환경에 맞는 digest source 반환.

    - EDITH_DS_DIGEST_URL 설정 → GitHubPagesDigestSource
    - 그 외 → LocalDigestSource (raw/digest/latest.json)

    EDITH_DS_DIGEST_LATEST(명시적 로컬 경로)는 tool 레이어에서 우선 처리됨.
    """
    url = os.environ.get("EDITH_DS_DIGEST_URL")
    if url:
        return GitHubPagesDigestSource(url)
    return LocalDigestSource(edith_home / "raw" / "digest" / "latest.json")
