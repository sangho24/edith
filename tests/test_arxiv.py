"""Phase 3 F8 — arxiv integration tests (no real network)."""

from __future__ import annotations

from harness.integrations.arxiv import fetch_arxiv_metadata, parse_arxiv_id

# ── parse_arxiv_id ──


def test_parse_url() -> None:
    assert parse_arxiv_id("https://arxiv.org/abs/2412.12345") == "2412.12345"


def test_parse_url_with_version() -> None:
    assert parse_arxiv_id("https://arxiv.org/abs/2412.12345v2") == "2412.12345"


def test_parse_id_only() -> None:
    assert parse_arxiv_id("2412.12345") == "2412.12345"


def test_parse_arxiv_prefix() -> None:
    assert parse_arxiv_id("arxiv:2412.12345") == "2412.12345"


def test_parse_5_digit() -> None:
    assert parse_arxiv_id("2412.123456") == "2412.12345"  # 첫 5 digit만


def test_parse_invalid() -> None:
    assert parse_arxiv_id("not an arxiv id") is None
    assert parse_arxiv_id("") is None


# ── fetch_arxiv_metadata (mock) ──


SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2412.12345v1</id>
    <title>
      Attention Sinks: A New Look at Transformer Activation Patterns
    </title>
    <summary>
      We study attention sinks, a phenomenon where attention heads place
      disproportionate weight on the first token. This paper introduces
      mechanistic explanations and shows mitigation strategies.
    </summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
    <category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.LG"/>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom" term="cs.LG"/>
  </entry>
</feed>
"""


def test_fetch_with_mock() -> None:
    def mock_get(url: str) -> str:
        assert "2412.12345" in url
        return SAMPLE_ATOM

    meta = fetch_arxiv_metadata("2412.12345", http_get=mock_get)
    assert meta["id"] == "2412.12345"
    assert "Attention Sinks" in meta["title"]
    assert "attention" in meta["abstract"].lower()
    assert "Jane Doe" in meta["authors"]
    assert "John Smith" in meta["authors"]
    assert meta["primary_category"] == "cs.LG"


def test_fetch_normalizes_whitespace() -> None:
    def mock_get(url: str) -> str:
        return SAMPLE_ATOM

    meta = fetch_arxiv_metadata("2412.12345", http_get=mock_get)
    # title은 newline·다중 공백 정리됨
    assert "\n" not in meta["title"]
    assert "  " not in meta["title"]


def test_fetch_no_entry_returns_empty() -> None:
    empty_atom = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    meta = fetch_arxiv_metadata("9999.99999", http_get=lambda _: empty_atom)
    assert meta == {}


def test_fetch_invalid_xml_returns_empty() -> None:
    meta = fetch_arxiv_metadata("x", http_get=lambda _: "not xml")
    assert meta == {}


# ── paper_triage tool integration ──


def test_paper_triage_tool(tmp_path) -> None:
    from harness.state import Context, Trace
    from harness.tools.paper import _paper_triage

    ctx = Context(edith_home=tmp_path, scope="personal", trace=Trace.start("test"))

    # mock 사용 못하므로 parse_arxiv_id 단계만 검증
    result = _paper_triage({"arxiv": "not-arxiv"}, ctx)
    assert not result["ok"]
    assert "parse" in result["error"]
