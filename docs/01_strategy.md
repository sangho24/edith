# 나만의 AI 비서 프로젝트 기획서 (v2)

> **⚠️ 실행 로드맵은 v3로 분리됨** → [`roadmap_v3_harness_first.md`](./roadmap_v3_harness_first.md) (Karpathy LLM Wiki + harness 패턴 기반). 이 문서의 Section 10·11(12주 phase·Track A)은 v3 로드맵으로 대체. 비전·문제정의·zone 격리·surfaces·deployment 등 전략 섹션은 그대로 유효.
>
> **⚠️ Phase 4 추가됨 (2026-05-14)** → F1-F12 이후 **스킬 플랫폼**으로 확장. 하드코딩 tool registry를 `harness/skills/`의 선언적 skill manifest로 전환(H8), 멀티채널 surface·ds-digest skill·헬스 데이터 skill(F13-F15). 계기는 [OpenClaw](https://github.com/openclaw/openclaw) 비교 — Edith는 깊이는 낫지만 확장성·생태계가 약점. 상세는 `docs/02_roadmap.md` §4.4, 빌드 하네스는 `docs/05_cc_harness.md`.
>
> **사용자**: 상호 (AI Scientist @ 삼일PwC AX Node, 학생 병행)
> **작성일**: 2026-04-28 (v2 — 전략) / 2026-04-28 (v3 — 실행)
> **북극성**: 매일 떠오르는 생각, 매주 나누는 대화, 매달 읽는 논문, 매분기 진행하는 프로젝트가 **하나의 외부 기억**에 모이고, 미래의 내가 검색·연결·재발견할 수 있는 자산이 되는 **Knowledge Twin**을 12주에 구축한다.
> **두 채널**: ① Pull — Cowork/Claude Desktop chat, ② Push — 카톡 메모 / 이메일 다이제스트
> **배포 원칙**: 노트북 → 홈 허브 → VPS relay 의 3-tier 점진적 인프라

> **v2 변경 이력**: v1의 비전·통합 환경·배포 아키텍처가 부족하다는 피드백 + 별도 deep research 보고서 통합. 비전을 Knowledge Twin으로 명확화, simpler-first 기술 스택(FastAPI+SQLite)으로 재정렬, two-channel surface와 3-tier deployment 추가, 8개 task domain (취업 준비 포함), MVP UX trinity (아침 digest / 낮 quick capture / 저녁 review) 도입.

---

## 0. Executive Summary

이 프로젝트는 두 가지 함정을 피하려는 것이다.

첫째, **"AI 자동화 도구가 더 필요해서"가 아니다.** 진짜 문제는 일이 많은 게 아니라 **여러 시스템에 흩어져 있고 매번 맥락을 복원·우선순위를 판단해야 한다**는 점이다. 그래서 첫 버전의 가치는 "대신 행동한다"가 아니라 **"나를 관찰하고, 정리하고, 제안한다"**에 있다. 행동은 그 다음 단계다.

둘째, **"멋진 multi-agent 데모"가 아니다.** 실제로 매일 쓰게 만들려면 화려한 swarm보다 **추적 가능성과 승인 플로우, 그리고 매일의 단순한 UX 세 개**(아침 digest / 낮 quick capture / 저녁 review)가 더 중요하다.

12주 안에 도달하는 모습은 다음과 같다.

- **Week 1**: 1주일 task logger 파일럿 — 비서 만들기 전에 본인을 관찰
- **Week 2-4**: 단일 backend(FastAPI + SQLite) 위에 캡처·다이제스트·승인 큐 MVP
- **Week 5-8**: 도메인별 보조 기능(이메일·캘린더·코드·연구·취업) 추가
- **Week 9-10**: 카톡 메모 push + Cowork chat의 두 채널 통합
- **Week 11-12**: 홈 허브 + VPS relay 인프라로 always-on 전환, 운영 안정화

기술 스택은 **simpler-first**: FastAPI + SQLite(WAL+FTS5) + APScheduler + Claude API + 함수형 orchestrator. 필요해질 때만 Mem0/Zep/LangGraph로 졸업한다. 회사·학교·개인 3개 zone을 물리적으로 분리(`work.db` / `school.db` / `personal.db`)해서 데이터·자격증명·정책을 격리한다.

12주 후 측정 가능한 목표: 매주 2-4시간 절감, 놓친 task 30% 감소, 추천 유용성 4.0/5.0 이상, privacy 사고 0건, 주 5일 이상 사용.

---

## 1. 문제 정의

### 1.1 진짜 문제는 무엇인가

상호님의 일상은 다음 8개 영역이 동시에 돌아간다.

회사(삼일PwC AX) · 학업 · 취업 준비 · 개인 개발 프로젝트 · 이메일·캘린더·메신저 · 논문·리서치 · 회고·감정·생산성 · 생활 루틴.

각 영역은 서로 다른 시스템(Gmail, Naver Mail, Google Calendar, Notion, Obsidian, GitHub, Slack, KakaoTalk, IDE/터미널)에 데이터가 흩어져 있다. 결과적으로 시간을 잡아먹는 진짜 비용은 "task 자체의 실행 시간"이 아니라 **(a) task가 흩어져 있어서 매번 다시 모으는 비용, (b) 우선순위를 매번 다시 판단하는 인지 부하, (c) 한 task에서 다른 task로 이동할 때 컨텍스트를 복원하는 시간**이다.

따라서 비서가 줄여야 할 것은 단순 작업 시간이 아니라 **fragmentation cost**다.

### 1.2 비서의 진짜 가치

> **"대신 행동한다"보다 "나를 관찰하고, 정리하고, 제안한다"**

이 순서가 핵심이다.

```
관찰 (Observe) → 구조화 (Structure) → 제안 (Suggest) → 승인 후 실행 (Approved Act)
```

이 순서를 어기는 비서(관찰 없이 자동화로 직행하는 비서)는 잘못된 task를 자동화하고, 잘못된 데이터를 외부로 보내고, 결국 신뢰를 잃는다.

### 1.3 사용자 맥락의 의미

상호님은 Python·FastAPI·LangGraph·LLM API·OAuth/connector를 직접 구현할 수 있다. 이 말은 다음 두 가지를 의미한다.

1. **연구 프로토타입이 아니라 제품 엔지니어링 과제**로 정의 가능. 멋진 agent보다 안정적인 backend가 우선.
2. **거창한 multi-agent swarm보다 단순한 함수형 orchestrator + typed tools가 빠르고 안전**. agent가 많아질수록 디버깅 난이도·state drift·비용·policy 일관성 저하·승인 전 과감한 행동 경향이 모두 커진다.

---

## 2. 비전 — Knowledge Twin

### 2.1 한 문장

> **"미래의 내가 과거의 나를 검색·연결·재발견할 수 있게 만든다."**

생산성 도구가 아니다. **외부 기억(extended memory)**이다. 시간 절감은 부산물이고, 진짜 가치는 6개월·1년·3년이 지났을 때도 본인의 사고와 결정의 흐름이 보존돼 있고, 새로운 입력을 그 흐름과 연결해 보여주는 데 있다.

### 2.2 성공 시나리오 (vivid)

다음 다섯 장면이 12-18개월 후 실제로 일어나면 성공이다.

1. **6개월 뒤 화요일 오후**, "지난 분기 BERT fine-tuning 실험할 때 LR scheduler 어떻게 셋업했더라?" 한 줄을 chat에 친다. 비서가 당시 daily note + 실험 코드 commit + 디버깅했던 Slack DM + 결과 그래프 캡처를 한 화면에 모아 띄운다.

2. **월요일 오전 8시 카톡 메모**: "이번 주 회의 4건 중 3건이 작년 12월에 다뤘던 'GPT 도입 ROI' 주제와 연결됨. 그때 작성한 내부 문서 v3 + 그때 본인이 남긴 우려사항 3개 요약"

3. **논문 읽다가 "이거 어디서 봤는데?"** — 비서가 자동으로 "3주 전 ICLR 후기 읽으면서 비슷한 셋업을 본인 노트에 메모하셨어요. 노트 링크 + 차이점 3가지" surfacing.

4. **회의 30분 전 push**: "30분 뒤 X님과 미팅. 이전 4번의 회의에서 다음 3가지를 약속하셨음. 본인 메모상 마지막으로 X에게 unanswered 질문 1개 있음."

5. **분기 회고**: "이번 분기 본인이 가장 자주 쓴 단어는 'transformer interpretability'. 가장 자주 만난 동료는 X님. 가장 자주 cancel한 task 종류는 '주말 사이드 프로젝트'. 작년 동분기 대비 변화: ..." — 본인 자신에 대한 mirror.

### 2.3 실패 시나리오 (anti-pattern)

다음 중 하나라도 발생하면 프로젝트는 실패다.

- **흩어짐**: 비서가 modality 별로 흩어져서 한 곳에서 모든 걸 못 본다 (메일은 알지만 노트는 모름)
- **신호 대 잡음 붕괴**: 6개월 뒤 메모리가 noise로 가득. 검색 결과가 신뢰 안 됨. 비서가 "옛날에 그런 말씀하셨어요"라고 하지만 그것이 진짜 본인 생각이었는지 외부 인용이었는지 불명
- **단절**: 모델 버전 바뀌면 비서가 "처음 만나는 사람"처럼 됨 — 데이터·skill·persona가 모델에 종속돼 있어서
- **zone leak**: 회사·학교·개인 데이터가 섞여서 어느 zone에서 답이 나왔는지 모름. 회사 정보가 개인 LLM 호출에 흘러들어감
- **습관 실패**: 만든 지 3개월 만에 안 쓰게 됨 — 매일 쓰는 단순 UX 세 개(아침/낮/저녁)가 안정화되지 않아서

### 2.4 5가지 설계 원칙

1. **Capture First, Automation Later** — 모든 입력을 빠짐없이 캡처해서 외부 기억에 누적하는 것이 최우선. 자동화는 그 다음.
2. **Observability Over Cleverness** — 화려한 추론보다 추적 가능한 간단한 흐름. 모든 의사결정에 근거(support_refs) 첨부.
3. **Approval Before Action** — write action은 항상 승인 큐를 거친다. 자동 실행은 가역·저위험에 한정.
4. **Privacy by Compartmentalization** — 회사·학교·개인 zone을 물리적으로 분리. 한 LLM에 다 보내지 않는다.
5. **Anti-Atrophy Loop** — 매주 일부 task는 의도적으로 수동 수행. AI에게 위탁한 능력을 정기적으로 사용해서 잃지 않게 한다.

### 2.5 명시적 비목표 (Anti-Goals)

- ❌ 모든 것을 자동화 — 카톡 친구 답장처럼 자동화하면 관계가 망가지는 영역이 있다.
- ❌ Level 4 fully autonomous agent — 6개월 내에 시도하지 않는다.
- ❌ 회사 데이터를 외부 LLM에 그대로 입력 — PIPA·삼일 정책 위반 가능.
- ❌ 처음부터 multi-agent — 단일 orchestrator + typed tools로 검증 후에 확장.
- ❌ 카카오톡 친구·동료와의 대화 자동 응답 — 정책상 어렵고 윤리적으로도 부적절.
- ❌ 멋진 dashboard 먼저 — 매일 쓰는 단순 UX 세 개부터.

---

## 3. 일주일 Task Map과 식별 방식

### 3.1 8개 영역 분해

| 영역 | 자주 발생하는 task | AI 개입 좋은 지점 |
|---|---|---|
| 회사 업무 (삼일) | 자료 읽기, 회의 준비, 분석 초안, 아이디어 정리, follow-up | 회의/문서 요약, TODO 추출, 초안 구조화 |
| 학업 | 과제 일정, 수업 자료 읽기, 시험 대비, 발표 준비 | 과제 캘린더화, 읽기 요약, 공부 계획 |
| 취업 준비 | JD 탐색, 자소서/이력서 수정, 포트폴리오 정리, 지원 추적 | JD 요약, resume bullet 제안, 지원 파이프라인 |
| 개인 개발 프로젝트 | repo 작업, 이슈 정리, 기능 설계, 배포·테스트 | commit/PR 요약, backlog 정리, 다음 액션 제안 |
| 이메일·캘린더·메신저 | unread triage, 일정 확인, 링크 저장, 답변 초안 | 중요도 분류, daily digest, reply draft |
| 논문·리서치 | 논문 저장, 읽을거리 backlog, 메모, 비교 | 논문 triage, 핵심 주장 추출, 비교표 |
| 회고·감정·생산성 | 일일 회고, 스트레스 요인, 집중 패턴 | daily reflection, 패턴 요약, 개선 제안 |
| 생활 루틴 | 수면, 이동, 식사, 운동, 장보기, 행정 | reminder, 루틴 리캡, 저위험 자동화, **헬스 데이터 연동** (Apple Health ← 샤오미 Mi Band, scope=personal, Phase 4 F15) |

### 3.2 1주일 파일럿 — passive capture + active confirmation

비서를 만들기 전에 **7일 동안 로그를 쌓는다**. 한 가지 방식만 쓰면 놓치는 영역이 생기므로 다중 소스로:

| 소스 | 무엇 수집 | 구현 | MVP 원칙 |
|---|---|---|---|
| Google Calendar | 일정명, 시간, 참석자, 설명, 링크 | Calendar Readonly API + incremental sync | 읽기 전용 |
| Gmail / Naver Mail | sender, subject, label, unread, snippet, thread id | Gmail API readonly metadata, Naver IMAP | 본문은 필요 시만 |
| Google Drive | 최근 수정 파일 metadata, 유형, 링크 | Drive readonly + changes polling | 내용은 on-demand |
| Notion | 프로젝트 DB, task DB, 페이지 변경 | Notion read API | shared workspace는 보수적으로 |
| GitHub | issue, PR, commit, branch, review 요청 | REST/GraphQL + webhook 또는 polling | 개인 repo부터 |
| IDE/터미널 | 최근 수정 파일, git diff 요약, 실행 명령 | 로컬 watcher | 로컬 전용 |
| **Manual quick add** | 지금 할 일, 방금 생긴 일, 링크/메모 | `/capture` CLI 또는 카톡 메모 → 봇 forward | 가장 중요 |
| **End-of-day check-in** | AI가 놓친 일, 미뤄진 일, 감정·에너지 | 저녁 회고 프롬프트 | 매일 3분 |

> **passive capture가 잡지 못하는 영역**: 짧은 생각, 갑자기 생긴 일, 대화 중 결정, 감정 변수. 이 4가지는 **manual quick capture와 end-of-day check-in**으로만 잡힌다. 그래서 두 가지가 가장 중요한 채널이다.

### 3.3 task 선정 7가지 기준

7일 로그가 쌓이면 각 task에 다음 점수를 매겨서 1차 자동화 대상을 추린다.

- **반복성**: 주당 몇 번 발생하는가
- **지속 시간**: 짧지만 자주 반복되는가
- **인지 부하**: "하기 싫고 귀찮은데 중요"한가
- **맥락 복원 비용**: 다시 열어봐야 할 시스템이 많은가
- **정확도 요구**: 한 번 실수하면 비용이 큰가
- **민감도**: 회사/개인 데이터인지
- **자동화 적합성**: 입력이 구조화되어 있는가

이 기준에 따라 **1차 MVP에 들어갈 가치가 높은 task는 거의 항상**: daily digest, unread triage, calendar prep, meeting/task extraction, 개인 프로젝트·학업 backlog 정리, reflection & next-day plan.

**1차 MVP에서 빠져야 할 task는 거의 항상**: 자동 메일 발송, 자동 일정 변경, 외부 시스템 직접 수정, 회사 문서 자동 변환·공유, 카카오톡 친구·동료 응답.

---

## 4. 자동화 vs 인지적 보조 — 경계 설정

### 4.1 5단계 자율성 모델

| 레벨 | 의미 | 예시 |
|---|---|---|
| **L0** | 기록만 함 (Capture only) | 로그 수집, 메모 저장, 일정·메일 캡처 |
| **L1** | 요약·검색·분류 (Summarize/Classify) | 캘린더 digest, 메일 triage, 문서 요약 |
| **L2** | 제안·초안 (Suggest/Draft) | 답장 초안, 계획표, resume bullet, follow-up draft |
| **L3** | 승인 후 실행 (Approved Action) | 일정 생성, 개인 Notion task 생성, 개인 메일 초안 발송 |
| **L4** | 자동 실행 (Autonomous, low-risk only) | 로컬 read-only sync, 내부 DB 정리, private inbox 정리, 저위험 reminder |

> v1에서는 자동차 SAE 6단계를 차용했지만, 개인 비서에는 5단계가 더 깔끔하다 (L5는 어차피 비추).

### 4.2 task의 3덩어리

자동화와 인지 보조를 분리하면 본인의 업무는 셋으로 나뉜다.

**자동화 친화 (L0-L1, 일부 L3)**: 일정 수집, 메일 정리, GitHub 변경 요약, task dedup, reminder 발행, read-only sync

**인지 보조 친화 (대체로 L2)**: 무엇이 중요한지 판단, 회의 후 다음 액션 고르기, job application 포지셔닝, 연구 주제 비교, 하루 계획 조정

**자동화 금지 (L4 절대 금지)**: 회사 외부 발송, 일정 재조정, 공식 문서 편집, 지원서 제출, 대외 메시지, 관계가 얽힌 메신저 응답

### 4.3 Level 4 자동 실행 허용/금지 매트릭스

| 구분 | 허용 여부 | 예시 |
|---|---|---|
| 로컬 read-only 수집 | ✅ 허용 | 캘린더/메일 metadata sync, 파일 목록 캐시 |
| 내부 DB 정리 | ✅ 허용 | dedup, tagging, memory 업데이트 |
| 개인 private inbox에 요약 저장 | ⚠️ 조건부 | 본인 전용 DB·노트에 digest 저장 |
| 개인 reminder 생성 | ⚠️ 조건부 | 오전 계획 리마인드, 마감 경고 |
| 개인 draft 생성 | ❌ 자동 발송 금지 | 초안 생성은 가능하나 발송은 승인 후 |
| 이메일·메신저 발송 | ❌ 금지 | 회사·개인 모두 초기 금지 |
| 일정 수정·회의 수락 | ❌ 금지 | 반드시 승인 |
| 외부 문서 수정 | ❌ 금지 | Notion/Drive/GitHub write 초기 금지 |
| 회사 데이터 외부 LLM 전달 | ❌ 금지 | 기본 금지, 예외는 explicit redaction 후 |
| 지원서 제출·금전·삭제 | 🚫 절대 금지 | irreversible action 전부 금지 |

### 4.4 task별 권고 레벨 (확장)

| Task | 권고 Level | HITL 패턴 | 1차 MVP |
|---|---|---|---|
| 캘린더 daily digest | L1 | 매일 read-only | ✅ |
| Gmail/Naver triage (스팸·뉴스레터) | L1-L2 | 분류 자동, 발송 X | ✅ |
| 회의/노트에서 TODO 추출 | L1-L2 | task inbox에 쌓고 사람이 채택 | ✅ |
| 회사 문서 요약 (로컬 only) | L1-L2 | 외부 LLM 안 씀 | ✅ 제한적 |
| 회사 문서 초안 구조화 | L2 | 내가 본문 작성 | ⚠️ 제한적 |
| 학업 과제 계획 | L1-L2 | 캘린더 제안 | ✅ |
| 학업 과제 본문 작성 | **L0** | AI 작성 안 함 (윤리) | ❌ |
| 논문·리서치 backlog | L1-L2 | 요약·tag·연결 | ✅ |
| JD 분석 + 지원 초안 | L2 | bullet 제안, 제출 X | ✅ |
| GitHub 개인 프로젝트 요약 | L1-L2 | daily digest | ✅ |
| Daily planning (Top 3) | L2 | 제안만 | ✅ |
| Reflection assistant | L1-L2 | 패턴 추출, 제안만 | ✅ |
| 외부 시스템 write (메일·일정) | L3 일부만 | 승인 큐 필수 | ⚠️ |
| 생활 루틴 reminder | L1-L4 일부 | 저위험만 자동 | ✅ |
| 카카오톡 친구·동료 응답 | **L0** | 자동화 X | ❌ |

### 4.5 Anti-atrophy Loop

매주 1-2개 task는 의도적으로 수동 수행해서 능력을 잃지 않게 한다. 분기마다 rotation:

- 분기 1: 메일 트리아지 자동, 회의록 수동 작성
- 분기 2: 회의록 자동, 메일 트리아지 수동 (감 잡기 위해)
- ...

판단력은 사용해야 유지된다. **"AI 출력에 대한 신뢰도 calibration"**도 매월 한 번 — 본인이 AI 출력을 그냥 믿었는데 사후 틀렸던 사례를 모아 본다.

---

## 5. 데이터 격리 — 3-Zone Model

### 5.1 왜 zone 격리가 핵심인가

상호님 환경에서 가장 중요한 단일 설계 결정이다. 회사(삼일PwC) 클라이언트 데이터, 학교 학업 데이터, 개인 데이터는 **물리적·논리적으로** 분리해야 한다. 단순 태그 분리는 부족하다.

### 5.2 3개 Zone의 운영 정책

```
┌──────────────────────────────────────────────────────────────┐
│ ZONE A — 회사 (삼일PwC AX)                                   │
│ 데이터: 클라이언트, 사내 코드, 내부 문서, 회의 메모          │
│ DB    : work.db (별도 encryption key)                        │
│ LLM   : 사내 정책에 따라 결정 (Bedrock private endpoint /    │
│         로컬 Solar/Llama / 사내 Claude allowlist)            │
│ 자동화: L0-L1 보수적. write action 전부 L3 (승인 후 실행)    │
│ 저장  : 회사 노트북 only. 개인 vault·홈허브에 절대 sync 금지 │
│ 사전  : IT/Compliance 사전 확인 필수                         │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ZONE B — 학교                                                 │
│ 데이터: 강의 자료, 과제, 연구 노트                           │
│ DB    : school.db                                             │
│ LLM   : Claude API (학업 윤리 지침 준수)                     │
│ 자동화: 노트 정리 L1-L2, 과제 본문 작성 L0                   │
│ 저장  : 학교 Drive + 개인 Obsidian vault (school 폴더)       │
│ 사전  : 강의별 syllabus의 AI 정책 확인                       │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ZONE C — 개인                                                 │
│ 데이터: 개인 메일·캘린더·카톡 메모, 사이드 프로젝트          │
│ DB    : personal.db                                           │
│ LLM   : Claude API 자유                                      │
│ 자동화: 가장 공격적 가능 (L3 일부, L4 일부)                  │
│ 저장  : 개인 클라우드 + Obsidian vault (personal 폴더)       │
└──────────────────────────────────────────────────────────────┘
```

각 DB는 **별도 encryption key, 별도 memory namespace, 별도 retrieval index, 별도 export policy**를 가진다. `scope=mixed`가 발생하면 기본 행동은 **외부 전송 금지 + 승인 요청**이다.

### 5.3 외부 LLM에 절대 보내지 않는 항목 (Zone A)

- 클라이언트 명칭이 포함된 문서·이메일·노트
- 회사 내부 회의 메모·회의록
- deliverable 초안, 분석 결과, 보고서 문안
- 재무 수치, 계약, 인사, 조직 관련 정보
- raw code, 내부 repo 내용, 내부 경로
- API key, token, 자격증명
- 참석자 실명이 포함된 캘린더 상세

외부 LLM이 꼭 필요하면: **로컬 추출 → 민감정보 redaction → 축약 요약 → 외부 LLM** 순서가 강제되는 정책 엔진을 거친다.

### 5.4 OAuth scope의 보수적 시작

| 시스템 | 초기 scope |
|---|---|
| Google Calendar | readonly |
| Gmail | metadata 또는 readonly |
| Google Drive | readonly |
| Notion | read content only |
| GitHub | 개인 repo readonly |
| Naver Mail | IMAP read |
| 로컬 파일 | allowlist path만 |
| 터미널 | allowlist 명령만 |

write scope는 기능별로 분리해서 나중에 추가한다 (개인 Notion append, 개인 draft 생성, 개인 calendar event 초안). 추가하더라도 처음에는 모두 L3(승인 후 실행)로 건다.

---

## 6. 시스템 아키텍처

### 6.1 전체 구성도

```text
[Calendar][Gmail][Naver][Drive][Notion][GitHub][IDE/Terminal][Quick Capture]
        \      |       |       |        |          |               /
                  [Collector + Normalizer + Sensitivity Tagger]
                                    |
                                    v
                       [SQLite (work/school/personal) + FTS5 + File Cache]
                                    |
                                    v
                        [Memory / Task / Project Layer]
                                    |
                                    v
                  [Orchestrator: retrieve → classify → plan]
                                    |
                  ----------------------------------------------
                  |                  |                  |
                  v                  v                  v
          [Digest Generator]  [Draft Composer]   [Action Proposer]
                  |                  |                  |
                  v                  v                  v
              ┌───┴───┐         [Draft Inbox]    [Approval Queue]
              v       v                                 |
        [Pull: Cowork] [Push: 카톡 메모/이메일]         v
                                                  [Executor Allowlist]
```

3개의 layer가 핵심이다.

- **Capture Layer**: 모든 입력 → 정규화 → SQLite. Knowledge Twin의 토대.
- **Reasoning Layer**: 단일 orchestrator가 retrieve → classify → plan을 함수형으로 수행. 각 도메인은 별도 agent가 아니라 **typed tool**.
- **Surface Layer**: Pull (Cowork chat) + Push (카톡 메모/이메일) 두 채널. backend는 같다.

### 6.2 Simpler-First 기술 스택 (1단계)

처음부터 화려한 것은 만들지 않는다. 1단계는 다음 정도면 충분하다.

| 계층 | 선택 | 이유 |
|---|---|---|
| API/backend | **FastAPI + Pydantic** | 단순·디버깅 쉬움·타입 안전 |
| DB | **SQLite (WAL 모드) + FTS5** | 1인 비서 규모에 충분, 백업 단순(파일 1개) |
| 스케줄러 | **APScheduler** 또는 cron | 한 프로세스에서 다 돌릴 수 있음 |
| ORM | SQLModel 또는 SQLAlchemy | Pydantic과 잘 어울림 |
| 파일 저장 | 로컬 디렉토리 + content hash | dedup 자연스럽게 |
| LLM | **Claude Sonnet 4.6 API** | 200K context, tool use 안정성, 한국어 자연스러움 |
| 한국 도메인 LLM | Solar Pro3 (선택) | 한국어 법·의·금융 task에서만 |
| Embedding | OpenAI text-embedding-3-large 또는 BGE-M3 (로컬) | zone에 따라 분기 |
| 검색 | SQLite FTS5 우선 + 필요 시 vector | 처음엔 FTS만으로 충분 |
| 워크플로 | **함수형 orchestrator** | 처음엔 LangGraph 안 씀 |
| Skill 저장 | git repo의 markdown 파일 | persona·playbook을 사람이 읽을 수 있게 |
| UI | Cowork chat (Pull) + 단순 dashboard (확인용) | 별도 frontend 안 만듦 |
| OS keychain | macOS Keychain / pass | secret 관리 |

### 6.3 단계적 졸업 — 언제 더 무거운 도구로 갈 것인가

| 트리거 | 졸업할 도구 |
|---|---|
| FTS5 검색 정확도가 떨어진다고 느낄 때 | pgvector 또는 SQLite의 sqlite-vec extension 추가 (PostgreSQL 이주는 마지막 옵션) |
| 함수형 orchestrator의 분기·재시도·long-running이 너무 복잡 | LangGraph 도입 (전체 교체 아님, 일부 워크플로만) |
| 메모리 검색에서 "사용자 선호" 추적이 부정확 | Mem0를 semantic memory 저장소로 추가 |
| 시계열 사건 reasoning("이번 분기 가장 자주 만난 사람")이 약함 | Zep을 episodic memory 저장소로 추가 |
| skill 자동 진화·자가 수정이 필요 | Letta 도입 (단, 자동 수정은 review queue 거쳐서) |
| 비서가 multi-task 동시 실행이 필요 | LangGraph orchestrator-worker 패턴 |

> **원칙**: 매 단계 졸업은 "측정된 한계"가 있을 때만. 미리 도입하지 않는다.

### 6.4 데이터 모델

| 테이블 | 주요 필드 |
|---|---|
| `task` | id, title, domain, scope, status, priority, urgency, importance, due_at, estimated_minutes, recurrence_rule, project_id, source_refs, sensitivity, automation_level_target, risk_level, needs_approval, created_at, updated_at |
| `event` | id, source_type, external_id, event_type, title, raw_text, started_at, ended_at, actor, url_ref, scope, sensitivity, project_guess, imported_at |
| `message` | id, source_type, thread_id, sender, recipients, subject, snippet, received_at, labels, unread, scope, sensitivity, source_url |
| `document` | id, source_type, external_id, title, mime_type, checksum, text_cache_path, summary, entities, source_url, scope, sensitivity, fetched_at |
| `project` | id, name, domain, description, owner, status, deadline, repo_ref, notion_ref, scope, priority, tags |
| `memory` | id, memory_type, content, scope, sensitivity, salience, confidence, support_refs, created_at, last_used_at, expires_at |
| `preference` | id, key, value, scope, confidence, source, updated_at |
| `decision` | id, context_type, context_ref, options_json, chosen_option, rationale, outcome_note, reviewed_at |
| `action_log` | id, action_type, target_system, payload_hash, preview_text, execution_status, executor, approved_by, created_at, executed_at, error_text |
| `approval_request` | id, action_type, target_system, preview_diff, risk_score, reversible, status, requested_at, expires_at |
| `user_feedback` | id, object_type, object_id, rating, accepted, correction_text, reason, created_at |
| `reflection` | id, date, energy_score, stress_score, wins_text, blockers_text, lessons_text, tomorrow_focus, scope |

각 테이블은 work/school/personal 3개 DB에 동일 스키마로 존재. cross-zone join은 정책 엔진을 거쳐서만.

### 6.5 메모리 설계 (3-tier with metadata)

memory는 그냥 긴 메모를 쌓는 것이 아니라 세 층으로:

- **Episodic** ("언제 무엇이 있었는가"): 이번 주 PwC 인턴 업무에서 X 주제 조사, 12월 어떤 회의에서 어떤 결정
- **Semantic** ("나에 대한 안정적 사실"): 본인은 'Top 3' 방식 일일 계획 수용률이 높음, 오후보다 오전이 deep work에 좋음
- **Procedural** ("내가 선호하는 작업 방식"): 답장 초안은 짧은 bullet → 문장화 순서

모든 memory entry는 다음 속성 필수:

- **support_refs**: 어디서 기인한 사실인지(원본 link)
- **scope**: personal/school/work
- **expires_at**: 시한 (예: "이번 분기에만 유효")
- **confidence**: 어느 정도 신뢰

> **개인 비서의 메모리는 "많이 기억"보다 "잘못된 기억을 천천히 줄여 가는" 것이 더 중요하다.**

### 6.6 Agent 설계 — 단일 orchestrator + typed tools

| 컴포넌트 | 필요 | MVP 형태 | 이유 |
|---|---|---|---|
| planner | ✅ | 단일 orchestration 프롬프트 | 오늘/이번 주 계획 생성 핵심 |
| task classifier | ✅ | 소형 모델 또는 라우팅 프롬프트 | domain/scope/sensitivity 분류 |
| memory retriever | ✅ | deterministic retrieval + optional embedding | 개인화 품질의 핵심 |
| calendar/email agent | ❌ 별도 X | tool module | 명시적 규칙 많아 agent화 이점 작음 |
| document summarizer | ❌ 별도 X | reusable summarization skill | 재사용 |
| coding assistant | ✅ 분리 최소 | repo skill/tool | 로컬 컨텍스트 제어 중요 |
| reflection agent | ✅ | nightly prompt/profile | 장기 개선 루프 |
| action executor | ✅ | allowlist executor | side-effect 명시적 제어 |
| **safety reviewer** | 🚫 필수 | deterministic policy + optional second LLM pass | 민감도·권한·승인 보호막 |

처음에는 **planner / retriever / executor가 별도 agent 프로세스가 아니라 함수**여야 한다. agent 분리는 phase 2 이후에.

---

## 7. 캡처 파이프라인 — Knowledge Twin Core

### 7.1 절대 조건

Knowledge Twin이 동작하려면 **모든 input이 빠짐없이, 자동으로, 마찰 없이 통합 저장소로 흘러들어가야** 한다. 캡처가 새면 6개월 뒤 비서는 "본인의 일부만 아는 비서"가 된다.

### 7.2 8개 입력 채널

| 채널 | 캡처 방식 | 빈도 | 비고 |
|---|---|---|---|
| Google Calendar | Calendar API + incremental sync | 5분 | scope: personal/school |
| Gmail | Gmail API readonly metadata | 10분 | 본문은 on-demand |
| Naver Mail | IMAP polling | 10분 | personal zone |
| Google Drive | Changes API + on-demand fetch | 30분 | metadata 위주 |
| GitHub | webhook (push) + 시간당 polling fallback | 실시간 | 개인 repo만 |
| Notion | API polling + diff | 1시간 | 개인 workspace |
| IDE/터미널 | 로컬 daemon (Watchdog + git diff snapshot) | 실시간 | 로컬-only |
| **Quick Capture** | (a) CLI `cap "텍스트"`, (b) **카톡 "나에게 보내기" → 봇이 forward**, (c) Cowork chat의 `/cap` | 즉시 | **가장 중요** |
| **End-of-day check-in** | 매일 22:00 카톡 메모로 3개 질문 push | 1일 | "오늘 놓친 일 / 미뤄진 일 / 내일 꼭 할 일" |

> **Quick Capture가 핵심 채널인 이유**: 짧은 생각·갑자기 생긴 일·대화 중 결정·감정 변수는 자동으로 안 잡힌다. 이걸 30초 안에 캡처할 수 있어야 한다. **카톡 "나에게 보내기"로 텍스트 던지면 자동으로 비서 inbox에 들어가는 구조가 1순위**.

### 7.3 정규화 스키마

모든 입력은 공통 schema로 변환:

```
timestamp / source / actor / project_guess / text / sensitivity / url_ref / scope
```

이 단계에서 **sensitivity tagger**가 work/school/personal로 1차 분류. 모호하면 mixed로 두고 보수적으로 처리.

### 7.4 캡처 → task 후보 추출 파이프라인

```
1. Ingest      : 채널별 connector → event_log
2. Normalize   : 공통 schema 변환 + sensitivity tag
3. Embed       : 로컬 또는 외부 embedding (zone 정책에 따라)
4. Store       : SQLite + 파일 cache + 필요 시 vector index
5. Extract     : event 중 task 후보 추출
                 ("회의 참석"은 event, "회의 전 자료 읽기"는 task 후보)
6. Confirm     : 일일 check-in에서 사용자가 1분 안에 채택/제거
7. Cluster     : 주간 클러스터링 (비슷한 task 묶고 반복성·인지부하 산정)
8. Resurface  : 새 입력이 들어올 때 관련된 과거 노트·결정 surface
```

### 7.5 자동 cross-link & resurfacing

Knowledge Twin의 정수: **"새로 들어온 입력이 과거의 무엇과 연결되는지를 자동으로 surface"**

- 새 회의 메모가 들어오면 → 과거 회의에서 언급된 같은 사람·프로젝트 자동 link
- 새 논문이 들어오면 → 본인 노트에서 비슷한 키워드·인용된 연구 link
- 매주 일요일 22시 → "이번 주 주제·연결·열린 질문" 합성 → 일요일 저녁 이메일로 push

구현은 단순하게 시작: 키워드 + entity matching + 시간 가중치. 나중에 vector similarity 추가.

---

## 8. 통합 환경 — Two-Channel Surface 설계

### 8.1 두 채널이 동일한 backend에 붙는 구조

상호님이 비서를 부르고 싶은 곳은 두 군데였다 — chat (Cowork/Claude Desktop) + 카톡 메모/이메일 알림. 이 둘은 **같은 backend, 같은 메모리, 같은 persona**를 공유하지만 egress 형식만 다르다.

```
                            ┌──────────────────────────────┐
                            │  Backend (FastAPI on Home Hub)│
                            │  - same memory                │
                            │  - same skills/persona        │
                            └──────────┬───────────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                │                      │                      │
                v                      v                      v
        ┌──────────────┐      ┌──────────────┐       ┌────────────────┐
        │ Pull 채널    │      │ Push 채널    │       │ 단순 Dashboard │
        │ (사용자 시작)│      │ (비서 시작)  │       │  (확인·승인)   │
        ├──────────────┤      ├──────────────┤       ├────────────────┤
        │ Cowork chat  │      │ 카톡 메모    │       │ approval queue │
        │ Claude       │      │ 이메일       │       │ daily logs     │
        │  Desktop     │      │  digest      │       │ memory browser │
        │ CLI `assistant│      │ Cowork       │       │ task inbox     │
        │  ask "..."`  │      │  notification │       │                │
        └──────────────┘      └──────────────┘       └────────────────┘
```

### 8.2 Pull 채널 — Cowork / Claude Desktop chat

**언제 쓰는가**: 본인이 능동적으로 비서를 부를 때.

- "지난 분기 transformer interpretability 관련 노트 다 모아줘"
- "오늘 일정 + 관련 사전 자료 한 화면에 정리해줘"
- "이 PR diff 1차 리뷰 코멘트 draft 해줘"
- "이 논문 비슷한 거 나 작년에 읽은 적 있나?"
- "이번 주 일요일 회고 초안"

**구현**: Cowork/Claude Desktop의 chat이 backend의 MCP server에 연결. backend는 `query`, `recall`, `draft`, `summarize`, `link` 같은 typed tool을 expose. Cowork에서 Claude가 이 tool들을 호출.

### 8.3 Push 채널 — 카톡 메모 / 이메일 다이제스트

**언제 쓰는가**: 비서가 먼저 surfacing 해야 할 때.

| Push 시점 | 내용 | 채널 |
|---|---|---|
| 매일 08:00 | Daily briefing (오늘 일정 + 메일 unread + Top 3 제안) | 카톡 메모 |
| 회의 30분 전 | Meeting prep (참석자 정보 + 과거 약속 + 미해결 이슈) | 카톡 메모 + 캘린더 popup |
| 매일 18:00 | Daily digest (오늘 한 일 요약 + 미뤄진 일 알림) | 이메일 |
| 매일 22:00 | End-of-day 3개 질문 (놓친 일/미뤄진 일/내일 꼭 할 일) | 카톡 메모 |
| 매주 일요일 21:00 | Weekly synthesis (이번 주 주제·연결·열린 질문 + 다음 주 계획 draft) | 이메일 (긴 텍스트) |
| 가끔 (월 2-3회) | Surprise resurfacing ("1년 전 오늘 이런 생각하셨네요") | 카톡 메모 |
| 승인 필요 시 | Approval request (preview + diff + 만료시간) | 카톡 메모 + Cowork notification |

### 8.4 Push 정책 — "조용한 비서가 좋은 비서"

- 평일 push 4회 이하 (08·meeting prep·18·22), 주말 1-2회
- "긴급" 카테고리는 별도. 회의 충돌·즉시 답해야 할 메일만.
- Surprise resurfacing은 monthly rate-limit (월 3회 한도). 너무 잦으면 신호가 noise가 됨.
- 사용자가 "조용 모드"를 toggle할 수 있어야 함 (시험 기간·deep work day).

### 8.5 동일 persona

두 채널에서 비서가 다르게 느껴지면 안 된다. **persona file (`identity.md`)**이 source of truth. 모든 surface는 이걸 system prompt로 로드.

```markdown
# identity.md (예시)
- 이름: (본인이 부르고 싶은 이름)
- 어조: 한국어 존댓말, 문장 짧게, 이모지 안 씀
- 우선순위: 정확성 > 친절함 > 간결함
- 거절: 회사 데이터를 외부 LLM에 보내라는 요청 거절
- 좋아하는 것: 근거(support_refs) 명시, 불확실하면 "확실하지 않음" 표시
```

---

## 9. 배포 아키텍처 — Always-on Infrastructure

### 9.1 왜 노트북 하나로는 부족한가

Knowledge Twin은 **항상 캡처**가 핵심이다. 노트북이 닫혀있을 때:
- Calendar webhook 못 받음
- 이메일 신규 못 잡음
- 매일 08·18·22시 push 못 함
- GitHub webhook 못 받음

그래서 **항상 켜져있는 layer**가 필요하다. 다만 처음부터 클라우드 가지 말고, 단계적으로.

### 9.2 추천: 3-Tier Deployment (단계별 도입)

```
┌──────────────────────────────────────────────────────────────┐
│ Tier 1 — Home Hub (always-on, 자택)                          │
│                                                               │
│ 하드웨어: Mac mini M2 (~$600 중고) / Intel NUC /              │
│           안 쓰는 데스크탑 / Raspberry Pi 5                  │
│ 역할:                                                         │
│   - SQLite (3 zones), 파일 cache                              │
│   - 모든 MCP/connector (Gmail, GitHub, Notion 등 OAuth 보관)  │
│   - APScheduler/cron (08·18·22시 routine)                     │
│   - Obsidian vault 정본 (Syncthing으로 노트북에 sync)         │
│   - Backup target (외장 SSD, 매일 pg_dump 같은 sqlite 백업)   │
│ 전력: 10-30W → 전기료 월 ~3,000원                             │
└──────────────────────────────────────────────────────────────┘
                              │
                              │ Tailscale / WireGuard VPN
                              │
┌──────────────────────────────────────────────────────────────┐
│ Tier 2 — VPS Relay (소형, 클라우드)                           │
│                                                               │
│ 추천: AWS Lightsail $5/월 / DigitalOcean / Oracle Free Tier  │
│ 역할 (stateless):                                             │
│   - 카톡 Memo API 호출 (외부 callable IP 필요)                │
│   - OAuth callback 받기                                       │
│   - 외부 webhook 수신 (GitHub, calendar updates)              │
│   - Home hub로 secure tunnel forward                          │
│ 데이터 저장 안 함 — 순수 relay                                │
│ 비용: 월 6,000-15,000원                                       │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│ Tier 3 — Client (노트북·폰)                                   │
│                                                               │
│ - 노트북: Cowork/Claude Desktop (chat surface)                │
│            CLI `assistant` 명령                                │
│            Obsidian (vault sync)                              │
│ - 폰: 카톡 메모로 push 받음, quick capture (텍스트)           │
│        Tailscale 켜놓으면 어디서든 home hub 접근              │
└──────────────────────────────────────────────────────────────┘
```

### 9.3 Why this stack

- **Privacy**: 데이터 정본은 집 안에. VPS는 stateless relay라서 침해돼도 데이터 손실 없음.
- **Always-on**: 노트북 닫혀있어도 capture·schedule 작동.
- **Cost**: 초기 ~$600 (중고 하드웨어) + 월 1.5만원.
- **Resilience**: VPS 죽어도 home hub의 capture/processing은 살아있음. 반대도 마찬가지.
- **Migration path**: home hub 자체가 docker-compose로 서비스 묶여있으면 클라우드 이주는 명령 한 줄.

### 9.4 단계적 도입

| Phase | 인프라 | 가능한 것 / 안 되는 것 |
|---|---|---|
| Week 1-4 | **노트북 only** | ✅ 캡처·digest·draft / ❌ 24시간 push, 노트북 sleep 때 누락 |
| Week 5-8 | **노트북 + 홈허브 도입** | 노트북에서 동작 검증된 것만 홈허브로 이전. 캡처가 24/7 작동. |
| Week 9-10 | **+ VPS relay** | 카톡 memo push 안정화, 외부 webhook 받기 시작. |
| Week 11+ | **steady state** | backup 자동화, monitoring 추가, model 버전 업그레이드 절차 정립. |

> **노트북에서 충분히 검증되지 않은 코드를 홈허브로 옮기지 않는다.** 홈허브로 가는 시점은 "이 task가 매일 정확하게 동작하는지"가 검증된 후.

### 9.5 장기 운영 — 1년 이상 지속 가능성

Knowledge Twin은 6개월 단위가 아니라 **수년 단위로 운영**하기 위해 만든다. 그래서 다음을 처음부터 고려.

**(a) 모델 마이그레이션**

Claude Sonnet 4.6 → 5 → 6, 또는 Solar Pro3 → 4로 바뀌어도 비서가 살아남아야 한다. 보장하려면:

- Skill·persona·playbook은 markdown (모델 무관)
- Vault는 markdown (영구 포맷)
- Embedding은 모델 종속 — 모델 바꿀 때 batch re-embed (비용 미미)
- system prompt rebuild는 `identity.md`에서 매 세션 생성

**(b) 백업 & 복원**

- SQLite 3개 zone은 매일 외장 SSD로 자동 백업
- Obsidian vault는 Syncthing + 사설 git remote (encrypted)
- 자격증명은 OS keychain + 별도 backup vault (1Password 같은)
- 분기에 한 번 **복원 drill** — 새 노트북에 처음부터 셋업해보기

**(c) Skill 진화 vs Decay**

- Skill 변경은 git diff로 추적. 자동 self-edit (Letta-style)은 처음에는 review queue 거쳐서.
- 매 분기: 18개월 이상 access 없는 memory entry는 archive (delete 아님)
- Vault tag 분류 review (1년에 1회) — noise 정리

**(d) 가족·동료와의 경계**

- 비서는 **단독 사용자(상호님)** 전용. 가족·팀 공유 안 함.
- 만약 나중에 팀에 일부 기능 공유한다면 (예: 회사 자동화), 별도 instance로 fork.

### 9.6 Privacy 강제 정책 (Zone A — 회사)

- 회사 노트북에는 **work.db만 존재**. school/personal은 부재.
- 회사 노트북의 비서는 **사내 승인된 LLM endpoint만** 호출 가능 (config로 강제).
- 매주 outbound traffic audit log review.
- 회사 노트북 ↔ 홈허브 sync는 **금지** (다른 zone임).

---

## 10. 12주 로드맵

### Week 0 (이번 주) — 사전 정리
- ✅ 회사 IT/Compliance에 "개인 AI 비서 프로젝트" 안건 1줄 문의 — 회사 데이터 처리 가능 범위 확인
- ✅ Anthropic API key 발급
- ✅ Google OAuth client (Calendar + Gmail readonly)
- ✅ GitHub PAT (repo + read:user)
- ✅ Obsidian vault 만들기 (없다면)

### Week 1 — 1주 task logger 파일럿
- ActivityWatch 설치, baseline 행동 관찰
- 매일 저녁 5분 daily note (Obsidian)
- 주말 30분: 8개 영역 카테고리 클러스터링 + Task Inventory v1
- **산출물**: `task_inventory_v1.md` + 시간 사용 baseline

### Week 2 — Task 우선순위 + 기술 검증
- 7일 로그 → 7가지 기준으로 task 점수
- 1차 자동화 후보 5-7개 선정
- FastAPI + SQLite skeleton 셋업, 첫 collector (Calendar) 동작 확인
- 3-zone schema 셋업 (work.db/school.db/personal.db)
- **산출물**: 후보 task list + 동작하는 calendar collector

### Week 3 — Capture Pipeline 1차
- Gmail/Naver Mail metadata collector
- Google Drive metadata
- GitHub webhook (개인 repo)
- Quick Capture: CLI `cap "텍스트"` + 카톡 "나에게 보내기" → 봇 forward
- 정규화 스키마 적용
- **산출물**: 모든 8채널 이벤트가 SQLite에 누적되는 파이프라인

### Week 4 — MVP UX Trinity (아침 / 낮 / 저녁)
- 매일 08:00 Daily briefing → 카톡 메모
- 매일 18:00 Daily digest → 이메일
- 매일 22:00 End-of-day check-in (3개 질문) → 카톡 메모
- 회의 30분 전 meeting prep
- **산출물**: 매일 쓰는 단순 UX 세 개가 안정 동작

### Week 5 — Approval Queue + Action Layer
- approval_request 테이블 + 승인 큐 UI (Cowork chat 또는 단순 dashboard)
- 첫 L3 task: 개인 calendar event 초안 생성 (사람 승인 후 발송)
- action_log + audit trail
- **산출물**: 승인 후 실행 흐름 검증

### Week 6 — Memory Layer + 개인화
- 3-tier memory (episodic / semantic / procedural) 테이블 + retrieval
- support_refs / confidence / expires_at metadata 필수
- Cowork chat의 MCP tool 연동 — backend의 query·recall·draft 호출
- **산출물**: 비서가 본인 과거 노트·이벤트를 인용해서 답함

### Week 7 — 코드·연구 워크플로
- GitHub MCP / repo skill (commit·issue·PR 요약)
- 논문 triage skill (arxiv 링크 → 핵심 contribution + 본인 노트와 link)
- 개인 프로젝트 daily project summary
- **산출물**: PR 1차 리뷰 draft 시간 50% 감소 측정

### Week 8 — 취업 준비 + 학업 워크플로
- JD analyzer skill (공고 → fit 분석 + bullet 제안)
- 지원 파이프라인 추적 (status 테이블)
- 학업 과제 캘린더화 + syllabus parser
- **산출물**: 지원 초안 패키지 자동 생성 (제출은 본인이)

### Week 9 — 한국 도구 통합 + Push 안정화
- Naver Search MCP 추가 (한국어 리서치)
- 카톡 Memo API push 안정화 (rate-limit 정책 포함)
- Weekly synthesis (일요일 21시 → 이메일)
- Surprise resurfacing 첫 동작
- **산출물**: 한국·글로벌 도구가 비서 안에서 통합

### Week 10 — Home Hub 도입
- Mac mini / NUC / 안 쓰는 PC를 always-on hub로
- Docker compose로 backend·MCP·scheduler 묶어서 이전
- Tailscale로 노트북·폰에서 접근
- 매일 자동 백업 시작
- **산출물**: 노트북 닫혀있어도 비서 동작

### Week 11 — VPS Relay + 측정·튜닝
- VPS (Lightsail $5) 셋업, 카톡 push relay
- 6주간 자동화한 task의 정확도·hallucination audit
- autonomy level 조정 (위 또는 아래)
- Anti-atrophy 점검: 다음 분기 의도적 수동 task 결정
- **산출물**: error rate report + autonomy v2

### Week 12 — 회고 + v2 계획
- 12주 vs Week 1 측정 비교
- Knowledge Twin이 본인을 얼마나 알고 있는지 self-audit ("내가 작년에 어떤 생각했는지 비서가 정말 알고 있나?")
- 다음 분기 확장 계획 (Mem0/Zep 도입? LangGraph로 일부 워크플로 이전? skill evolution loop?)
- **산출물**: `quarterly_review.md` + v2 spec

---

## 11. 트랙 A — PR-by-PR 개발 플로우

### 11.1 왜 트랙 A가 필요한가

Section 10의 12주 로드맵은 **phase view** — 어떤 단계를 거치는지를 보여준다. 하지만 실제 개발은 **매주 작은 PR 1개를 머지하고, 그 PR이 즉시 본인에게 쓸모 있어야** 한다. 그렇지 않으면 "3주차에 인프라만 깔다가 흥미를 잃는" 함정에 빠진다.

트랙 A는 같은 12주를 **PR view**로 다시 본다. 매주 → 1개 vertical slice → 머지 직후 본인이 즉시 사용.

원칙:

- **Vertical slice over horizontal layer** — 매주 end-to-end 동작하는 1개 feature
- **Visible value per week** — 그 주에 머지한 코드를 본인이 즉시 사용 가능
- **Dependency-aware** — 이전 PR 위에 쌓이지만, 단독으로도 의미 있음
- **Bounded scope** — 한 주 안에 못 끝낼 것 같으면 자르거나 미룬다
- **Personal zone first** — 모든 PR은 personal zone에서 먼저 검증. Zone A(회사) 적용은 IT 승인 후 별도

### 11.2 12주 PR 카탈로그

| Week | PR ID | 제목 | 머지 직후 가능해지는 것 (Demo) | 의존 | 위험 |
|------|-------|------|--------------------------------|------|------|
| 0 | A0 | Pre-flight | 회사 IT 답변 + Anthropic/Google/GitHub 자격증명 + ActivityWatch 켜짐 + 빈 SQLite 3 zone schema | — | 없음 |
| 1 | **A1** | **Quick Capture v1** | 카톡 "나에게 보내기"로 던진 텍스트가 SQLite에 자동 카테고리(personal/school/work) + tag 와 함께 저장. CLI `cap "텍스트"`도 동시 동작. | A0 | 카톡 봇 OAuth 처음 세팅 |
| 2 | **A2** | **Calendar Collector + `today` 명령** | `assistant today` 실행 → 오늘 일정 list + 사전 자료 link 한 화면 | A0 | Google OAuth scope 보수적으로 |
| 3 | **A3** | **Gmail Unread Triage** | unread 메일에 자동 priority/category 라벨 부여 (read-only). chat에서 "오늘 답해야 할 메일?" 물으면 답함 | A0 | metadata-only 잘 지키기 |
| 4 | **A4** | **Morning Briefing 통합 UI** | 매일 08시 카톡 메모로 (오늘 일정 + 메일 priority + Top 3 제안) push. A1+A2+A3를 한 화면 텍스트로 합성. | A1+A2+A3 | rate limit, 첫 push 텍스트 길이 적정화 |
| 5 | **A5** | **Approval Queue + 첫 L3** | 개인 calendar event 초안을 비서가 만들고, Cowork chat에서 "승인" 누르면 발송. action_log 기록. | A2 | 비가역 행동, audit 필수 |
| 6 | **A6** | **Memory Recall** | "지난 주 X 관련 뭐 메모했더라?" 쿼리 → support_refs (원본 link) 첨부 답변. 3-tier memory schema 적용. | A1 | hallucination 위험 — 근거 없으면 답 X |
| 7 | **A7** | **Repo Skill (PR 1차 리뷰)** | 개인 repo PR이 올라오면 1차 리뷰 코멘트 draft가 chat으로 와서 사람이 발송. | A0 | code 컨텍스트 |
| 8 | **A8** | **Paper Triage** | arxiv 링크를 던지면 핵심 contribution 요약 + 본인 노트와 자동 link surface | A6 | RAG 정확도 |
| 9 | **A9** | **JD Analyzer (취업 준비)** | JD URL 던지면 fit 분석 + 본인 이력서 기반 bullet 제안. 지원 파이프라인 status 추적. | A6 | 본인 이력서 캡처 |
| 10 | **A10** | **Weekly Synthesis + Resurfacing** | 일요일 21시 이메일로 "이번 주 주제·연결·열린 질문 + 다음 주 plan draft". + 가끔 "1년 전 오늘 이런 생각하셨네요" surprise resurfacing 첫 동작 | A1-A9 | 주간 누적 데이터 충분해야 의미 있음 |
| 11 | **A11** | **Home Hub Deploy** | Mac mini/NUC에 backend 이전 (docker-compose). 24/7 capture·schedule 시작. 노트북 닫혀있어도 비서 동작. | A1-A10 stable | docker-compose 처음, Tailscale |
| 12 | **A12** | **VPS Relay + Steady State** | 카톡 push가 home hub 닫혀있어도 안정적. 매일 백업 자동. monitoring·alert 1개 추가. | A11 | tunneling, 보안 |

각 PR은 **다음 주 PR이 시작되기 전까지 본인이 매일 1번 이상 사용했는가**가 진짜 머지 기준이다. 사용 안 했으면 그 feature는 보류 또는 폐기.

### 11.3 PR 작성 형식 (self-discipline 도구)

각 PR은 다음 6개 요소를 README/PR description에 포함:

1. **What**: 무엇을 만들었는가 (1줄)
2. **Why**: 왜 지금 만드는가 (1줄)
3. **Demo**: 머지 직후 본인이 직접 해볼 수 있는 명령 1개
4. **Out of scope**: 이번 PR에서 일부러 안 한 것 (다음 PR에서 함)
5. **Risk**: 잘못되면 무엇이 망가지나
6. **Rollback**: 어떻게 되돌리나 (`git revert` 1줄로 안 끝나면 PR이 너무 큰 것)

예시 — A1 PR:

> **What**: 카톡 메모로 던진 텍스트를 SQLite `event` 테이블에 sensitivity tag 붙여 저장
> **Why**: Knowledge Twin의 1순위 캡처 채널. 이게 없으면 짧은 생각이 전부 새어나간다.
> **Demo**: 카톡에서 "나에게 보내기"로 "오늘 회의에서 X가 한 말 흥미로움" 보내면, 1분 안에 `personal.db`의 `event`에 source=kakao, scope=personal, tag=[meeting, observation]으로 저장.
> **Out of scope**: 이미지·음성 캡처 (다음 PR), 자동 cross-link (A6), push (A4)
> **Risk**: 카톡 webhook 인증 잘못 setup하면 OAuth 토큰 노출 가능
> **Rollback**: 봇 토큰 폐기 + DB 테이블 drop

### 11.4 트랙 B — 평행 housekeeping (매주 30분-1시간)

트랙 A가 feature 누적이라면, 트랙 B는 **비서를 살아있게 유지하는** 평행 작업이다. 이게 빠지면 트랙 A가 아무리 잘 굴러가도 6개월 후 noise·drift로 무너진다.

| 주기 | 작업 | 시간 | 출력 |
|---|---|---|---|
| 매일 22시 | end-of-day check-in (push로 자동 trigger) | 3분 | `reflection` 테이블 1행 |
| 매주 일요일 22:00 | weekly retro: 이번 주 자동화한 task 정확도 self-audit | 15분 | error rate report |
| 매주 일요일 22:15 | skill 파일 review (git diff 확인) | 10분 | 다음 주 skill backlog |
| 매월 1일 | hallucination 사례 모음 → guardrail 추가 | 30분 | policy update PR |
| 매분기 | autonomy slider 조정, anti-atrophy rotation 결정 | 1시간 | `autonomy_v{n}.md` |
| 매분기 | 18개월 미사용 memory archive | 30분 | clean memory |
| 매분기 | 백업 복원 drill (새 머신에 처음부터 셋업) | 2시간 | restore_log |

### 11.5 Anti-scope 가드 — PR이 부풀지 않게

각 주마다 흔히 빠지는 함정과 대응:

- **"이왕 하는 김에..."** → No. 이번 PR은 1개 feature만. 다른 아이디어는 `backlog.md`로.
- **"인프라부터 제대로..."** → No. 인프라는 **검증된 코드만** Tier 1 → Tier 2로 옮긴다. Week 11 전에 home hub 옮기지 않는다.
- **"multi-agent로 만들면 더 멋질 듯..."** → No. 단일 orchestrator + typed tools. multi-agent는 phase 2 (Week 13+).
- **"회사 데이터로 테스트해보자"** → 🚫 절대 No. 모든 PR은 personal zone에서 검증. Zone A 적용은 IT 승인 후 별도 PR (분리된 repo 권장).
- **"한 주에 PR 2-3개 가능"** → 잠깐. 시간 여유 있으면 (a) 트랙 B에 투자, (b) 그 주 PR의 polish/test에 투자, (c) backlog 정리. PR 수보다 quality.
- **"이번 PR은 demo가 안 보여도 다음 주를 위한 기반..."** → Red flag. demo 안 보이는 PR은 자르거나 다음 주 feature와 합쳐서 vertical slice로 묶는다.

### 11.6 PR 사이즈 가이드

| 단계 | 적정 변경 line | 적정 시간 | 적정 file 수 |
|---|---|---|---|
| Week 1-3 (기반) | 200-500 line | 6-12시간/주 | 5-15 file |
| Week 4-9 (feature) | 100-400 line | 4-10시간/주 | 3-10 file |
| Week 10-12 (인프라·통합) | 100-600 line | 6-15시간/주 | 5-20 file |

이 범위를 벗어나면 PR을 자르거나 scope를 줄인다. 1000-line PR은 본인 혼자도 review가 안 된다.

### 11.7 Phase view ↔ PR view 매핑

| Phase (Section 10) | 트랙 A PR |
|---|---|
| Week 0: Pre-flight | A0 |
| Week 1-2: Observation + Foundation | A1, A2 |
| Week 3-4: Capture + 첫 통합 | A3, A4 |
| Week 5-6: Approval + Memory | A5, A6 |
| Week 7-9: Domain Skills | A7, A8, A9 |
| Week 10: Knowledge Twin essence | A10 |
| Week 11-12: Always-on Infra | A11, A12 |

> 이 매핑은 Section 10의 phase 설명과 함께 읽으면, "어떤 단계에서 어떤 PR이 나오는지" 동시에 보인다.

---

## 12. 측정 지표

12주 후 측정:

| 지표 | 측정 방법 | 1차 목표 |
|---|---|---|
| 시간 절감 | 주간 self-report + ActivityWatch 비교 | 주당 2-4시간 |
| Deep work 비율 | ActivityWatch 카테고리 분석 | 25% → 40% |
| 놓친 task 감소 | 주간 회고에서 "놓친 일" 개수 | 30% 감소 |
| 일정 충돌 감소 | 겹치는 일정·준비 누락 횟수 | 체감 감소 |
| 초안 작성 품질 | 초안 후 수정 시간, 채택률 | 수정 시간 25% 감소 |
| 추천 유용성 | digest/plan에 대한 5점 평가 | 평균 4.0 이상 |
| 승인 비율 | 제안 대비 승인 비율 | 40-60% (이상 범위) |
| Hallucination | 잘못된 요약·task 추출 건수 | 100건당 5건 이하 |
| Privacy 사고 | 민감정보 외부 전송·노출 시도 | 0건 |
| Habit retention | 주당 사용일수 | 5일 이상 |
| Improvement loop | 회고 후 규칙·선호 업데이트 수 | 매주 1개 이상 |

> **승인 비율 해석**: 너무 높으면(>80%) AI가 trivial한 것만 제안. 너무 낮으면(<30%) 품질 낮거나 권한 과다. 40-60%가 sweet spot.

---

## 13. 위험·실패 모드와 완화책

| # | 위험 | 발현 시 | 완화책 |
|---|---|---|---|
| 1 | **Cognitive atrophy** | 메일·우선순위 판단 능력 감퇴 | 매주 1-2 task 의도적 수동 + 분기별 rotation |
| 2 | **Hallucination** | "약속한 적 없는 deadline" draft | L2 이상은 verifiable task만. 외부 발송 전 사람 승인. support_refs 강제 |
| 3 | **Privacy leakage** | 회사 데이터가 외부 LLM API로 전송 | 3-zone 격리 + work.db는 사내 LLM만 + 매주 outbound audit |
| 4 | **Accountability gap** | AI가 잘못 보낸 메일 책임 모호 | 모든 자동 action audit log + "AI 보조" disclosure |
| 5 | **Over-confidence** | AI 출력 무비판적 신뢰 | 매월 정확도 audit + 신뢰도 calibration |
| 6 | **Prompt injection** | 외부 문서의 악의적 지시문이 실행됨 | retrieved text는 명령으로 취급 안 함 (policy로 강제) |
| 7 | **Tool poisoning** | 외부 시스템 반환값을 agent가 과신 | side-effect 전 preview/diff/justification 강제 |
| 8 | **권한 오남용** | 너무 일찍 write scope 열어서 실수 | scope를 기능별로 분리, 처음에는 모두 L3 |
| 9 | **카톡 정책 위반** | 비공식 자동화로 계정 정지 | Talk Memo API (본인에게만)만 사용. 친구·동료 자동 응답 안 함 |
| 10 | **Habit failure** | 3개월 만에 안 쓰게 됨 | 매일 UX trinity (08·18·22) 안정화가 최우선. 화려한 기능 말고 |

---

## 14. 예산

| 항목 | 월 예상 |
|---|---|
| Claude API (Sonnet 4.6) | $40-80 |
| Solar API (선택) | $5-10 |
| OpenAI embedding (선택) | $5-10 |
| VPS Lightsail | $5 |
| Domain (선택) | $1 |
| 홈허브 전기료 | ~3,000원 |
| **운영비 합계** | **월 7-12만원** |
| 일회성: 홈허브 하드웨어 | 50-90만원 (중고 Mac mini / NUC) |

---

## 15. 다음 단계 (Action Items)

### 이번 주 (Week 0)
1. ActivityWatch 설치
2. Obsidian vault 만들기 (없다면)
3. 매일 저녁 5분 daily note 시작
4. **회사 IT/Compliance에 "개인 AI 비서 프로젝트" 1줄 문의 (가장 중요)**
5. Anthropic API key, Google OAuth, GitHub PAT 준비

### Week 1 시작 전 결정해야 할 3가지
1. **회사 zone에서 어떤 LLM을 쓸 수 있는가?** (사내 Bedrock private endpoint? Solar 사설? 로컬 모델?) — IT 답변 후 결정
2. **첫 quick capture 채널은?** (CLI? 카톡 "나에게 보내기" → 봇 forward?) — 둘 다 만들되 카톡 우선
3. **Push 알림은 어디로?** (카톡 메모 + 이메일) — 둘 다, 시간대별로 다르게

### Phase 2 시작 전 (Week 4 끝)
1. 1차 자동화 5-7개 선정 결과 review
2. 홈허브 하드웨어 결정 (지금 안 쓰는 PC 있나?)
3. 첫 L3 (승인 후 실행) task 한 개 결정

---

## 16. 참고 자료

### Agent / SOTA
- [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk)
- [Anthropic Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [LangGraph (Phase 2 졸업 시)](https://www.langchain.com/langgraph)
- [2026 MCP Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)

### 메모리 (졸업 시 도입)
- [Mem0](https://mem0.ai/) · [Zep](https://www.getzep.com/) · [Letta](https://www.letta.com/)

### Task 식별 / Autonomy
- [Karpathy on Autonomy Slider — Latent Space](https://www.latent.space/p/s3)
- [Cal Newport — Deep Schedules](https://calnewport.com/from-deep-tallies-to-deep-schedules-a-recent-change-to-my-deep-work-habits/)
- [ActivityWatch](https://activitywatch.net/)

### 한국 도구
- [KakaoTalk Talk Memo API](https://developers.kakao.com/docs/latest/en/kakaotalk-message/rest-api)
- [Naver Mail IMAP](https://www.getmailbird.com/setup/access-naver-com-via-imap-smtp)
- [Naver Search MCP](https://github.com/isnow890/naver-search-mcp)
- [Solar by Upstage](https://www.upstage.ai/products/solar-mini)
- [HyperCLOVA X / CLOVA Studio](https://clova.ai/en/hyperclova)

### MCP
- [GitHub 공식 MCP](https://github.com/github/github-mcp-server)
- [Anthropic Skills GitHub](https://github.com/anthropics/skills)

### 참고 프로젝트
- [Khoj — 오픈소스 second brain agent](https://khoj.dev/)
- [Inbox Zero — 이메일 AI](https://github.com/elie222/inbox-zero)

### 한국 법
- [PIPA 가이드 (Securiti)](https://securiti.ai/south-korea-personal-information-protection-act/)

---

## 17. 한 줄 정리

> **"먼저 1주일 본인을 관찰하고 — 무엇을 자동화할 가치가 있는지, 무엇을 자동화하면 본인을 잃는지 알아낸 뒤 — FastAPI+SQLite로 단순한 backend를 시작해서 매일 쓰는 UX 세 개(아침 digest / 낮 quick capture / 저녁 review)를 안정화하고, Cowork chat과 카톡 메모 두 채널로 동일한 비서를 부르고, 검증된 코드만 홈허브로 옮겨 노트북이 닫혀있어도 항상 캡처가 일어나게 하라. 12주 후에는 단순 시간 절약이 아니라 — 미래의 내가 과거의 나를 다시 만날 수 있는 외부 기억(Knowledge Twin)이 동작하기 시작한다."**
