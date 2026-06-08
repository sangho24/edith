"""Phase 3 F4 / Phase 4 F14 — ds_digest source tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.integrations.ds_digest import (
    GitHubPagesDigestSource,
    LocalDigestSource,
    _httpx_fetch,
    get_digest_source,
)


class _FakeHTTPResponse:
    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body
        self.status = status

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def test_empty_when_no_file(tmp_path: Path) -> None:
    src = LocalDigestSource(tmp_path / "missing.json")
    result = src.latest()
    assert result["n"] == 0
    assert result["items"] == []


def test_json_format(tmp_path: Path) -> None:
    p = tmp_path / "latest.json"
    p.write_text(
        json.dumps(
            {
                "date": "2026-04-28",
                "items": [
                    {
                        "title": "Attention is All You Need 후속 연구",
                        "source": "arxiv",
                        "url": "https://arxiv.org/abs/x",
                        "score": 9.2,
                    },
                    {
                        "title": "Karpathy LLM Wiki pattern",
                        "source": "hn",
                        "score": 8.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    result = LocalDigestSource(p).latest()
    assert result["date"] == "2026-04-28"
    assert result["n"] == 2
    assert result["items"][0]["title"].startswith("Attention")
    assert result["items"][0]["source"] == "arxiv"


def test_corrupt_json(tmp_path: Path) -> None:
    p = tmp_path / "latest.json"
    p.write_text("{not valid", encoding="utf-8")
    result = LocalDigestSource(p).latest()
    assert result["n"] == 0


def test_markdown_bullet_extraction(tmp_path: Path) -> None:
    p = tmp_path / "latest.md"
    p.write_text(
        """# DS Digest 2026-04-28

## ArXiv
- Transformer interpretability via SAE
- Mixture of experts scaling

## HackerNews
* Local LLM benchmarks
""",
        encoding="utf-8",
    )
    result = LocalDigestSource(p).latest()
    assert result["n"] == 3
    titles = [item["title"] for item in result["items"]]
    assert any("Transformer" in t for t in titles)
    assert any("Local LLM" in t for t in titles)


def test_markdown_skips_headers(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("# Title\n## Section\n- item\n", encoding="utf-8")
    result = LocalDigestSource(p).latest()
    assert result["n"] == 1
    assert result["items"][0]["title"] == "item"


# ── F14 GitHubPagesDigestSource ──────────────────────────────────────────


def test_github_pages_parses_json() -> None:
    body = json.dumps(
        {
            "date": "2026-05-14",
            "items": [
                {"title": "SAE circuit", "source": "arxiv", "score": 9.1},
                {"title": "Local LLM bench", "source": "hn", "score": 8.3},
            ],
        }
    )
    src = GitHubPagesDigestSource(url="https://x/latest.json", fetch_fn=lambda _: body)
    result = src.latest()
    assert result["date"] == "2026-05-14"
    assert result["n"] == 2
    assert result["items"][0]["title"] == "SAE circuit"


def test_github_pages_network_failure_is_graceful() -> None:
    def boom(_: str) -> str:
        raise ConnectionError("network down")

    result = GitHubPagesDigestSource(url="https://x/latest.json", fetch_fn=boom).latest()
    assert result == {"date": None, "items": [], "n": 0}


def test_github_pages_corrupt_json_is_graceful() -> None:
    src = GitHubPagesDigestSource(url="https://x/latest.json", fetch_fn=lambda _: "{nope")
    assert src.latest()["n"] == 0


def test_github_pages_wrong_shape_json_is_graceful() -> None:
    src = GitHubPagesDigestSource(url="https://x/latest.json", fetch_fn=lambda _: '["not", "dict"]')
    assert src.latest() == {"date": None, "items": [], "n": 0}


def test_github_pages_passes_configured_url() -> None:
    seen: list[str] = []

    def spy(url: str) -> str:
        seen.append(url)
        return '{"items": []}'

    GitHubPagesDigestSource(url="https://custom/path.json", fetch_fn=spy).latest()
    assert seen == ["https://custom/path.json"]


def test_get_digest_source_defaults_to_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("EDITH_DS_DIGEST_URL", raising=False)
    src = get_digest_source(tmp_path)
    assert isinstance(src, LocalDigestSource)


def test_get_digest_source_uses_pages_when_url_set(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EDITH_DS_DIGEST_URL", "https://sangho24.github.io/ds-digest/latest.json")
    src = get_digest_source(tmp_path)
    assert isinstance(src, GitHubPagesDigestSource)
    assert src.url == "https://sangho24.github.io/ds-digest/latest.json"


def test_default_fetch_uses_urllib_timeout(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_urlopen(req: Any, timeout: int) -> _FakeHTTPResponse:
        calls.append((req.full_url, timeout))
        return _FakeHTTPResponse('{"items": []}')

    import harness.integrations.ds_digest as ds_digest

    monkeypatch.setattr(ds_digest.urllib.request, "urlopen", fake_urlopen)

    assert _httpx_fetch("https://x/latest.json") == '{"items": []}'
    assert calls == [("https://x/latest.json", 10)]


def test_github_pages_default_fetch_bad_status_is_graceful(monkeypatch) -> None:
    def fake_urlopen(req: Any, timeout: int) -> _FakeHTTPResponse:
        return _FakeHTTPResponse("server error", status=503)

    import harness.integrations.ds_digest as ds_digest

    monkeypatch.setattr(ds_digest.urllib.request, "urlopen", fake_urlopen)

    result = GitHubPagesDigestSource(url="https://x/latest.json").latest()
    assert result == {"date": None, "items": [], "n": 0}
