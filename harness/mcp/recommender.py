"""F29a — MCP 추천기 (pull-only, deterministic).

PRD docs/08 §4.1 ① mcp-ecosystem v1의 추천 슬라이스. 실제 MCP 호출·연결은
하지 않는다 (F18 bridge spike 미완·F23 정책 하드닝 미완). 순수 추천만:
쿼리 키워드 × roi_tier(docs/07 ROI 분석 R1~R6)로 deterministic 점수를 매겨
연결 후보 MCP를 랭킹한다.

trace 빈도 가중치(w3)는 데이터가 쌓인 뒤(v2). v1은 키워드매칭(w1)·roi_tier(w2)만.

⚠️ 추천은 L1(suggest) 상한 — "이거 연결할까요?" 까지. 실제 연결은 사용자가
`harness mcp enable <id>`(무인증 read) 또는 mcp_connect approval(외부write·oauth)로
별도 수행한다 (PRD §8 D3). 이 모듈은 그 결정을 위한 근거만 제공한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Recommendation:
    """단일 MCP 추천 결과 — 비영속(non-persistent).

    score는 deterministic(키워드매칭 + roi_tier). reason_text는 docs/07 ROI
    근거를 인용한다("docs/07 R2" 식). requires_auth/scope/caution은 사용자가
    연결 결정 시 봐야 할 메타.
    """

    mcp_id: str
    score: float
    reason_text: str
    requires_auth: bool
    scope: str  # personal | school | work | any
    caution: str = ""


@dataclass(frozen=True)
class _CatalogEntry:
    """MCP_CATALOG 항목 — 알려진 MCP 하나의 정적 메타데이터."""

    mcp_id: str
    roi_tier: int  # docs/07 ROI 순위: R1=6 .. R6=1 (높을수록 부착 가치↑)
    roi_ref: str  # docs/07 근거 라벨 (예: "docs/07 R2")
    requires_auth: bool
    scope: str
    keywords: list[str]
    summary: str  # reason_text 합성에 쓰는 한 줄 설명
    caution: str = ""


# docs/07 §3 ROI 분석 → roi_tier 매핑.
# R1(KakaoTalk MemoChat)=6, R2(YouTube)=5, R3(Naver)=4, R4(hwp 등 work)는
# 여기 카탈로그에선 google/notion(R4~R6대 oauth 후순위)으로 대체 표현.
# roi_tier 높을수록 docs/07에서 "즉시 부착 가치(1순위)"에 가깝다.
MCP_CATALOG: list[_CatalogEntry] = [
    _CatalogEntry(
        mcp_id="kakao",
        roi_tier=6,
        roi_ref="docs/07 R1",
        requires_auth=False,
        scope="personal",
        keywords=["카톡", "카카오", "메모", "메모챗", "나에게", "kakao", "capture", "캡처"],
        summary="KakaoTalk MemoChat — '나에게 보내기' 캡처 채널 (read-only 무인증)",
        caution="카톡 메시지는 mixed scope — 캡처 시 보수적으로 personal, 사용자 확인.",
    ),
    _CatalogEntry(
        mcp_id="youtube",
        roi_tier=5,
        roi_ref="docs/07 R2",
        requires_auth=False,
        scope="any",
        keywords=[
            "유튜브",
            "youtube",
            "영상",
            "자막",
            "대본",
            "transcript",
            "강연",
            "동영상",
            "subtitle",
        ],
        summary="YouTube Data MCP — 자막·검색 (read-only 무인증)",
    ),
    _CatalogEntry(
        mcp_id="naver",
        roi_tier=4,
        roi_ref="docs/07 R3",
        requires_auth=False,
        scope="any",
        keywords=[
            "네이버",
            "naver",
            "뉴스",
            "블로그",
            "한국어",
            "국내",
            "검색",
            "news",
            "blog",
            "학술",
        ],
        summary="Naver Search MCP — 뉴스·블로그·학술 (read-only 무인증)",
    ),
    _CatalogEntry(
        mcp_id="google",
        roi_tier=3,
        roi_ref="docs/07 R5 / docs/08 D2",
        requires_auth=True,
        scope="any",
        keywords=["구글", "google", "캘린더", "calendar", "드라이브", "drive", "지메일", "gmail"],
        summary="Google MCP — Calendar·Drive·Gmail (OAuth 필요)",
        caution="OAuth 인증 + credential store 필요 — mcp_connect approval 경유.",
    ),
    _CatalogEntry(
        mcp_id="notion",
        roi_tier=2,
        roi_ref="docs/07 R4 / docs/08 D2",
        requires_auth=True,
        scope="any",
        keywords=["노션", "notion", "문서", "초안", "draft", "페이지", "워크스페이스", "page"],
        summary="Notion MCP — 페이지·DB 초안 (OAuth 필요)",
        caution="OAuth 인증 + 외부write는 F23 정책·approval 라우팅 선행.",
    ),
]

# 점수 가중치. w1=키워드매칭(매치 1건당), w2=roi_tier(정규화). w3(trace 빈도)는 v2.
_W1_KEYWORD = 1.0
_W2_ROI = 0.5
_MAX_ROI_TIER = 6


def _keyword_hits(query: str, keywords: list[str]) -> int:
    """query(소문자) 안에 등장하는 keyword 개수. 부분일치(substring)."""
    q = query.lower()
    return sum(1 for kw in keywords if kw.lower() in q)


def _score(query: str, entry: _CatalogEntry) -> float:
    """deterministic 점수 = w1·키워드매칭수 + w2·(roi_tier/최대tier)."""
    kw = _keyword_hits(query, entry.keywords)
    roi_norm = entry.roi_tier / _MAX_ROI_TIER
    return _W1_KEYWORD * kw + _W2_ROI * roi_norm


def _reason(entry: _CatalogEntry, hits: int) -> str:
    """reason_text 합성 — docs/07 근거 인용 + 매칭 신호."""
    auth = "OAuth 필요" if entry.requires_auth else "read-only 무인증"
    base = f"{entry.summary} — {auth} ({entry.roi_ref})"
    if hits:
        return f"{base} · 쿼리 키워드 {hits}건 매칭"
    return base


def recommend(query: str, top_k: int = 3) -> list[Recommendation]:
    """query에 가장 적합한 MCP를 deterministic 점수로 랭킹해 top_k 반환.

    점수 = w1·키워드매칭 + w2·roi_tier (docs/07 ROI). 동점이면 roi_tier 높은 순,
    그 다음 mcp_id 사전순으로 안정 정렬. 실제 MCP 호출·연결은 하지 않는다.
    """
    scored: list[tuple[float, _CatalogEntry, int]] = []
    for entry in MCP_CATALOG:
        hits = _keyword_hits(query, entry.keywords)
        scored.append((_score(query, entry), entry, hits))

    # 점수 desc → roi_tier desc → mcp_id asc (deterministic tie-break).
    scored.sort(key=lambda t: (-t[0], -t[1].roi_tier, t[1].mcp_id))

    out: list[Recommendation] = []
    for score, entry, hits in scored[: max(0, top_k)]:
        out.append(
            Recommendation(
                mcp_id=entry.mcp_id,
                score=round(score, 4),
                reason_text=_reason(entry, hits),
                requires_auth=entry.requires_auth,
                scope=entry.scope,
                caution=entry.caution,
            )
        )
    return out


__all__ = ["MCP_CATALOG", "Recommendation", "recommend"]
