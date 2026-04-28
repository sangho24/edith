"""Phase 3 F1 — Quick Capture tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.capture import capture_to_raw
from harness.compile import infer_scope
from harness.llm import LLMResponse, MockLLM


@pytest.fixture
def edith_home(tmp_path: Path) -> Path:
    (tmp_path / "raw" / "captures").mkdir(parents=True)
    (tmp_path / "wiki").mkdir(parents=True)
    (tmp_path / "harness" / "traces").mkdir(parents=True)
    (tmp_path / "identity.md").write_text("# Edith\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    return tmp_path


# ── F1 머지 기준: scope 자동 분류 ≥9/10 ──

SCOPE_GOLDEN: list[tuple[str, str]] = [
    ("오늘 김교수님과 미팅, ICLR review 얘기", "school"),
    ("삼일PwC AX 클라이언트 미팅 메모", "work"),
    ("이번 주말 친구랑 영화 볼 예정", "personal"),
    ("강의 syllabus 확인 필요", "school"),
    ("내 GitHub repo에 새 commit 푸시함", "personal"),
    ("이번 학기 과제 마감 다음주", "school"),
    ("회사 데이터 분석 프로젝트 시작", "work"),
    ("오늘 점심 메뉴 뭐 먹지", "personal"),
    ("수업 끝나고 카페", "school"),
    ("사내 기술 세미나 발표 준비", "work"),
]


def test_scope_classification_accuracy() -> None:
    """F1 머지 기준 — 10개 sample text 중 ≥9개 정확."""
    correct = 0
    misses: list[tuple[str, str, str]] = []
    for text, expected in SCOPE_GOLDEN:
        actual = infer_scope("raw/captures/x.md", text)
        if actual == expected:
            correct += 1
        else:
            misses.append((text, expected, actual))
    assert correct >= 9, f"scope accuracy {correct}/10. misses: {misses}"


# ── direct path ──


def test_direct_capture_creates_file(edith_home: Path) -> None:
    result = capture_to_raw("hello world", edith_home=edith_home)
    assert result.ok
    assert result.path is not None
    assert result.path.startswith("raw/captures/")
    assert (edith_home / result.path).exists()


def test_direct_capture_writes_frontmatter(edith_home: Path) -> None:
    result = capture_to_raw("text", edith_home=edith_home, source="kakao")
    assert result.path is not None
    written = (edith_home / result.path).read_text(encoding="utf-8")
    assert written.startswith("---\n")
    assert "source: kakao" in written
    assert "scope: personal" in written
    assert "captured_at:" in written
    assert "text" in written


def test_direct_capture_auto_scope_school(edith_home: Path) -> None:
    result = capture_to_raw("오늘 김교수님과 강의 끝나고 미팅", edith_home=edith_home)
    assert result.scope == "school"


def test_direct_capture_auto_scope_work(edith_home: Path) -> None:
    result = capture_to_raw("삼일PwC 클라이언트 회의록", edith_home=edith_home)
    assert result.scope == "work"


def test_direct_capture_explicit_scope_overrides(edith_home: Path) -> None:
    """--scope work 명시하면 자동분류 무시."""
    result = capture_to_raw("그냥 점심 메뉴 메모", edith_home=edith_home, scope="work")
    assert result.scope == "work"


def test_empty_text_rejected(edith_home: Path) -> None:
    result = capture_to_raw("", edith_home=edith_home)
    assert not result.ok
    assert result.error == "empty text"


def test_whitespace_only_rejected(edith_home: Path) -> None:
    result = capture_to_raw("   \n\t  ", edith_home=edith_home)
    assert not result.ok


def test_safe_source_strips_special_chars(edith_home: Path) -> None:
    """source에 특수문자 있어도 파일명 안전하게."""
    result = capture_to_raw("x", edith_home=edith_home, source="kakao/memo:test")
    assert result.ok
    assert result.path is not None
    # 파일명에 / 나 : 가 들어가면 안 됨
    fname = Path(result.path).name
    assert "/" not in fname
    assert ":" not in fname


# ── via_llm path ──


def test_via_llm_path_invokes_runtime(edith_home: Path) -> None:
    mock = MockLLM(
        [
            LLMResponse(
                stop_reason="tool_use",
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "capture_text",
                        "input": {
                            "text": "via llm test",
                            "scope": "personal",
                            "source": "test",
                        },
                    }
                ],
            ),
            LLMResponse(stop_reason="end_turn", text="캡처 완료"),
        ]
    )
    result = capture_to_raw("via llm test", edith_home=edith_home, via_llm=True, llm=mock)
    assert result.ok
    assert result.via_llm
    assert result.trace_id is not None
    assert result.path is not None
    assert (edith_home / result.path).exists()


def test_via_llm_failure_recorded(edith_home: Path) -> None:
    """LLM이 budget 초과로 끊기면 ok=False."""
    inf = LLMResponse(
        stop_reason="tool_use",
        content_blocks=[
            {
                "type": "tool_use",
                "id": "tu_x",
                "name": "emit_log",
                "input": {"msg": "loop"},
            }
        ],
    )
    mock = MockLLM([inf] * 50)
    result = capture_to_raw("x", edith_home=edith_home, via_llm=True, llm=mock)
    assert not result.ok
    assert "budget" in (result.error or "")
