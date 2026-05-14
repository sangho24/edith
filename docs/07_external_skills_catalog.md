# 07 · 외부 스킬·API 카탈로그 + Edith 부착 ROI 분석

> 2026-05-14 v0.1 · 조사 노트
> 출처: [PlayMCP (Kakao 공식 MCP)](https://playmcp.kakao.com) · [NomaDamas/k-skill](https://github.com/NomaDamas/k-skill)
> 목적: 한국 환경 외부 스킬/API를 정리하고, **실사용 ROI 높은 것**만 골라 Edith 부착 방안 ideation.

---

## 0. 두 소스의 성격 차이 (먼저 구분)

| | **PlayMCP** | **k-skill** |
|---|---|---|
| 형태 | MCP 서버 — 툴이 `mcp__..._PlayMCP__*`로 노출 | skill 모음집 — Claude Code/Codex용 skill 파일 |
| 제공 | 카카오 공식 (호스팅된 MCP) | NomaDamas 커뮤니티 (MIT, 4.9k★) |
| 범위 | Naver Search · YouTube Data · KakaoTalk MemoChat 3계열 | 50+ 한국 생활/행정/금융/쇼핑 skill |
| 인증 | 대부분 불필요 (카카오가 키 관리) | skill별 상이 (공개 API는 무인증, 예약/금융은 로그인) |
| Edith 부착 경로 | runtime이 MCP를 말하거나, adapter로 감쌈 | `harness/integrations/` + `harness/skills/`로 재구현·래핑 |

> **핵심**: 둘 다 그대로는 못 쓴다. Edith는 자체 런타임 하네스를 가지므로,
> 부착하려면 `harness/skills/<name>.py` manifest + integration adapter가 필요하다.
> PlayMCP는 MCP라 adapter가 얇고(툴 1:1 매핑), k-skill은 로직 재구현이 필요.

---

## 1. PlayMCP 카탈로그 (카카오 공식)

### 1.1 KakaoTalk
| 툴 | 기능 |
|---|---|
| `KakaotalkChat-MemoChat` | "나에게 보내기" 메모챗 송수신 |

### 1.2 Naver Search
| 툴 | 기능 |
|---|---|
| `NaverSearch-search_news` | 뉴스 검색 |
| `NaverSearch-search_blog` | 블로그 검색 |
| `NaverSearch-search_academic` | 학술 자료 검색 |
| `NaverSearch-search_encyc` | 백과사전 |
| `NaverSearch-search_book` | 도서 |
| `NaverSearch-search_kin` | 지식iN |
| `NaverSearch-search_cafearticle` | 카페 글 |
| `NaverSearch-search_local` | 지역(장소) |
| `NaverSearch-search_image` | 이미지 |
| `NaverSearch-search_shop` / `search_webkr` | 쇼핑 / 웹문서 |
| `NaverSearch-datalab_search` | 검색어 트렌드 |
| `NaverSearch-datalab_shopping_*` | 쇼핑 트렌드 (연령·성별·기기·카테고리·키워드별) |
| `NaverSearch-find_category` / `get_current_korean_time` | 카테고리 조회 / 한국 시각 |

### 1.3 YouTube Data
| 툴 | 기능 |
|---|---|
| `YouTubeData-get_transcripts` | 영상 자막/대본 추출 |
| `YouTubeData-list_available_captions` | 자막 트랙 목록 |
| `YouTubeData-search_videos` / `search_playlists` / `search_live_videos` | 검색 |
| `YouTubeData-get_video_details` / `get_video_comments` / `get_video_categories` | 영상 상세·댓글·카테고리 |
| `YouTubeData-get_channel_details` / `get_channel_statistics` / `get_channel_top_videos` | 채널 정보·통계·인기영상 |
| `YouTubeData-get_playlist_details` / `get_playlist_items` | 재생목록 |
| `YouTubeData-get_related_videos` / `get_trending_videos` | 연관·인기 영상 |

---

## 2. k-skill 카탈로그 (50+ skill, 카테고리별)

| 카테고리 | 대표 skill |
|---|---|
| 교통·예약 | srt-booking, ktx-booking, express-bus-booking, korean-transit-route |
| 숙박·여가 | foresttrip-vacancy, catchtable-sniper, myrealtrip-search |
| 통신·정보 | **kakaotalk-mac**, seoul-subway-arrival, subway-lost-property |
| 뉴스·콘텐츠 | **geeknews-search**, naver-news-search, naver-blog-research |
| 날씨·환경 | korea-weather, fine-dust-location, han-river-water-level |
| 법률·행정 | korean-law-search, iros-registry-automation, korean-privacy-terms |
| 비즈니스·회계 | korean-jangbu-for, **k-dart** (DART 14 endpoint) |
| 부동산 | real-estate-search, gongsijiga-search, lh-notice-search, court-auction-notice-search |
| 교육·장학 | **korean-scholarship-search**, k-schoollunch-menu, library-book-search |
| 보건·안전 | mfds-drug-safety, mfds-food-safety |
| 금융·투자 | korean-stock-search, toss-securities, lotto-results |
| 지식재산 | korean-patent-search |
| 통계 | kosis-stats |
| 역사·문화 | joseon-sillok-search |
| 스포츠 | kbo-results, kbl-results, kleague-results, lck-analytics |
| 쇼핑 | coupang/naver-shopping/danawa/bunjang/daiso/kurly/oliveyoung-search, delivery-tracking |
| 문서 | **hwp**, rhwp-edit, rhwp-advanced |
| 텍스트 | **korean-spell-check**, korean-character-count, korean-slang-writing |
| 유틸 | zipcode-search, k-skill-setup, k-skill-cleaner |

(전체 표는 `docs/` 외부 — 위는 ROI 분석에 필요한 것 위주 발췌)

---

## 3. ROI 분석 — Edith에 부착할 가치

평가 기준: **상호님 8개 task 도메인**(회사·학업·취업·개발·메일캘린더·논문리서치·회고·생활)에
얼마나 직접 닿는가 × 부착 비용 × 사용 빈도.

### 🟢 1순위 — 즉시 부착 가치 (높은 빈도 × 핵심 도메인)

#### R1. KakaoTalk MemoChat (PlayMCP) → **F1 Quick Capture의 실제 채널**
- **왜 최고 ROI인가**: `docs/01_strategy.md` §3.2가 "manual quick capture가 가장 중요한 채널"이라고 못박았다. 지금 Edith의 capture는 CLI(`harness cap`)와 Telegram뿐. **MemoChat = 카톡 나에게 보내기**가 그대로 capture 채널이 되면, 상호님이 이미 매일 쓰는 습관에 0-friction으로 올라탄다.
- **부착**: F13 `Channel` 인터페이스에 `KakaoMemoChannel` 어댑터 추가. inbound = MemoChat 폴링/웹훅 → `IncomingMessage` → `capture_text` tool. scope 휴리스틱으로 1차 분류.
- **비용**: 낮음 — `Channel` Protocol 이미 있음. MCP 툴 1개 래핑.
- **주의**: 카톡 메시지는 mixed scope. capture 시 보수적으로 `personal`, 사용자 확인.

#### R2. YouTube `get_transcripts` + `search_videos` (PlayMCP) → **ds-digest 시너지 + 논문/리서치**
- **왜**: ds-digest가 이미 YouTube를 소스로 쓴다(F14). Edith가 transcript를 직접 뽑으면 — (a) digest 항목의 영상을 요약·wiki 컴파일, (b) 리서치 도메인에서 "이 강연 핵심 정리" 가능. AI Scientist에게 컨퍼런스 토크 transcript는 논문만큼 가치.
- **부착**: `harness/skills/youtube.py` 신규 — `youtube_transcript` tool. ds-digest skill과 연계.
- **비용**: 낮음 — MCP 툴 래핑.

#### R3. Naver `search_news` + `search_blog` + `search_academic` (PlayMCP) → **현재 인식 + 한국어 리서치**
- **왜**: arxiv triage(F8)는 영어 논문 중심. 한국어 학술·뉴스·블로그는 사각지대. 삼일PwC AX 업무·취업 시장 동향·국내 연구는 Naver가 1차 소스.
- **부착**: `harness/skills/naver.py` — `naver_news`/`naver_academic` tool. morning brief·recall에 편입 가능.
- **비용**: 낮음.

### 🟡 2순위 — 도메인 특화 (빈도는 낮지만 도메인 깊이)

#### R4. hwp (k-skill) → **회사 도메인 문서 처리**
- **왜**: 삼일PwC·국내 클라이언트 문서는 HWP가 표준. `.hwp ↔ markdown` 변환이 되면 회사 자료를 raw로 캡처·요약 가능. 지금은 HWP가 통째로 블라인드.
- **부착**: `harness/integrations/hwp.py` — kordoc(read-only) 호출. **scope=work 고정** + 외부 LLM 전송 전 PII 체크(R4 정책).
- **비용**: 중간 — k-skill 로직 재구현 또는 kordoc 직접 호출.
- **주의**: 회사 데이터 → 외부 LLM 금지 룰(identity.md)과 충돌 가능. 로컬 변환만, 요약은 사내 endpoint.

#### R5. geeknews-search + naver-news-search (k-skill) → **ds-digest 소스 확장**
- **왜**: ds-digest 큐레이션 소스를 GeekNews·Naver뉴스로 넓힘. 단 이건 ds-digest repo 쪽 작업이지 Edith 쪽이 아닐 수 있음.
- **부착**: ds-digest repo에 소스 추가가 더 적합 — Edith는 결과만 read(F14). **Edith 직부착 우선순위 낮음.**

#### R6. korean-scholarship-search + library-book-search (k-skill) → **학업 도메인**
- **왜**: 학생 도메인. 장학금 마감 추적·도서 검색은 캘린더/recall과 연계 가능.
- **부착**: 중간 비용, 사용 빈도 낮음 — 3순위 가까움.

### 🔴 부착 보류 — ROI 낮거나 위험

| skill/API | 보류 이유 |
|---|---|
| k-dart, toss-securities, korean-stock-search | 금융 데이터 — 흥미롭지만 상호님 task 도메인에 직접 안 닿음. 투자 비서가 아님. |
| srt/ktx/bus booking, catchtable-sniper | 예약 자동화 = 비가역 외부 행동. identity.md "비가역 외부 발송 금지"와 정면 충돌. |
| kakaotalk-mac (k-skill) | MemoChat(R1)과 기능 겹침 + 친구 대화 읽기는 프라이버시·정책 리스크. R1으로 충분. |
| Naver datalab_shopping_* | 쇼핑 트렌드 — Edith 도메인 아님. |
| 쇼핑 검색 전반 (coupang/danawa/...) | 생활 편의지만 Knowledge Twin 핵심 아님. |
| korea-weather, fine-dust | morning brief 양념으로 가능하나 ROI 낮음 — 나중에. |

---

## 4. 권고 — 부착 순서

```
1차 PR  R1 KakaoMemoChannel   — F13 Channel에 어댑터. 가장 높은 ROI (capture 습관).
2차 PR  R2 youtube skill       — get_transcripts. ds-digest 시너지.
3차 PR  R3 naver skill         — search_news/academic. 한국어 리서치 사각 메움.
4차 PR  R4 hwp integration     — 회사 도메인. scope=work 정책 주의.
보류    R5/R6 및 나머지         — 도메인 안 닿거나 위험.
```

각 PR은 CLAUDE.md "eval 먼저" 룰대로 golden YAML 동봉. `harness/skills/<name>.py` manifest의
`eval_globs`로 연결. R1은 `channels` 필드도 채움 (`["kakao"]`).

### 아키텍처 결정 필요 (Phase B 토론거리)
- **PlayMCP를 어떻게 부착하나**: (a) Edith runtime이 MCP client가 되어 `mcp__PlayMCP__*`를 직접 호출 vs (b) MCP 툴을 `harness/tools/`로 1:1 래핑. (b)가 trace·policy 일관성에 유리하지만 래퍼 코드가 늘어남. (a)는 얇지만 trace 누락 위험.
- 이건 `docs/06_design_backlog.md`에 신규 항목으로 올릴지 사용자 결정 필요.

---

## 변경 이력

- 2026-05-14 v0.1 — PlayMCP·k-skill 조사 후 ROI 분석 초안. 부착 우선순위 R1-R6.
