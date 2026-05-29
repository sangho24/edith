"""F29a — MCP 추천기 단위 테스트.

recommend()의 deterministic 랭킹·docs/07 근거 인용·scope/requires_auth 메타,
그리고 recommend_mcp tool의 dict 직렬화를 검증한다. 실제 MCP 호출은 없음.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.mcp.recommender import MCP_CATALOG, Recommendation, recommend
from harness.state import Context, Trace
from harness.tools import mcp as mcp_tool


def _ctx(tmp_path: Path) -> Context:
    return Context(edith_home=tmp_path, scope="personal", trace=Trace.start("t"))


def test_youtube_query_ranks_youtube_first() -> None:
    recs = recommend("이 유튜브 강연 자막 정리해줘", top_k=3)
    assert recs, "추천 결과가 비면 안 됨"
    assert recs[0].mcp_id == "youtube"


def test_youtube_reason_cites_docs07() -> None:
    recs = recommend("유튜브 자막 transcript", top_k=1)
    top = recs[0]
    assert "docs/07 R2" in top.reason_text
    # 무인증 read-only 신호가 reason에 명시돼야 함.
    assert "무인증" in top.reason_text


def test_youtube_is_no_auth_and_any_scope() -> None:
    top = recommend("유튜브 영상 요약", top_k=1)[0]
    assert top.requires_auth is False
    assert top.scope == "any"


def test_naver_query_ranks_naver_first() -> None:
    recs = recommend("네이버 뉴스랑 블로그 한국어 검색", top_k=3)
    assert recs[0].mcp_id == "naver"
    assert "docs/07 R3" in recs[0].reason_text


def test_kakao_query_ranks_kakao_first() -> None:
    recs = recommend("카톡 메모챗으로 캡처", top_k=3)
    assert recs[0].mcp_id == "kakao"
    assert recs[0].requires_auth is False
    assert recs[0].caution  # 카톡은 mixed scope 주의 문구 있음


def test_oauth_mcp_flags_requires_auth() -> None:
    notion = recommend("노션 페이지 초안 만들기", top_k=1)[0]
    assert notion.mcp_id == "notion"
    assert notion.requires_auth is True
    assert notion.caution


def test_top_k_limits_results() -> None:
    recs = recommend("유튜브 자막", top_k=2)
    assert len(recs) == 2
    # 전체 카탈로그보다 작은 수만 반환.
    assert len(recs) < len(MCP_CATALOG)


def test_no_match_falls_back_to_roi_tier() -> None:
    """키워드 0매칭이면 roi_tier 높은 순(kakao=R1)으로 deterministic 정렬."""
    recs = recommend("관련 없는 임의 질의 zzz", top_k=5)
    # 모두 점수 동일(키워드 0) → roi_tier desc: kakao(6) > youtube(5) > naver(4) ...
    assert recs[0].mcp_id == "kakao"
    ids = [r.mcp_id for r in recs]
    assert ids == ["kakao", "youtube", "naver", "google", "notion"]


def test_ranking_is_deterministic() -> None:
    a = recommend("유튜브 자막 정리", top_k=3)
    b = recommend("유튜브 자막 정리", top_k=3)
    assert [r.mcp_id for r in a] == [r.mcp_id for r in b]
    assert [r.score for r in a] == [r.score for r in b]


def test_returns_recommendation_dataclass() -> None:
    recs = recommend("유튜브", top_k=1)
    assert isinstance(recs[0], Recommendation)


def test_tool_returns_serializable_dict(tmp_path: Path) -> None:
    result: Any = mcp_tool.RECOMMEND_MCP.fn(
        {"query": "이 유튜브 자막 정리", "top_k": 3}, _ctx(tmp_path)
    )
    assert isinstance(result, dict)
    assert result["query"] == "이 유튜브 자막 정리"
    recs = result["recommendations"]
    assert isinstance(recs, list) and recs
    assert recs[0]["mcp_id"] == "youtube"
    assert "docs/07 R2" in recs[0]["reason_text"]
    assert recs[0]["requires_auth"] is False


def test_tool_default_top_k(tmp_path: Path) -> None:
    result: Any = mcp_tool.RECOMMEND_MCP.fn({"query": "유튜브"}, _ctx(tmp_path))
    assert len(result["recommendations"]) == 3
