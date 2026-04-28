"""ds-digest 통합.

사용자 private repo `sangho24/ds-digest` — 매일 07:10 KST에 YouTube/RSS/ArXiv/HN을
Gemini 필터링한 DS 큐레이션. 출력: Telegram + Email + GitHub Pages archive.

Edith는 가장 최근 digest를 morning brief에 포함시킴. read-only.

소스:
- LocalDigestSource: 로컬 클론된 repo의 archive 파일 (JSON or markdown) 직접 읽기
- (future) GitHubPagesDigestSource: https://sangho24.github.io/ds-digest/latest.json fetch
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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
