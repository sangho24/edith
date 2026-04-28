"""Phase 3 F4 — ds_digest source tests."""

from __future__ import annotations

import json
from pathlib import Path

from harness.integrations.ds_digest import LocalDigestSource


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
