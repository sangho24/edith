# Edith — Knowledge Twin

상호님(AI Scientist @ 삼일PwC AX Node, 학생)의 개인 Knowledge Twin.
[Karpathy LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) + [agent harness](https://github.com/jha0313/harness_framework) 기반.

## 핵심 철학

- **Compilation, not Q&A** — raw source를 LLM이 markdown wiki로 컴파일. 이후엔 wiki 위에서 동작.
- **Harness-first** — feature보다 측정·재현·롤백 환경(eval·trace·policy) 먼저.
- **3-zone isolation** — work / school / personal 데이터 물리·논리적 분리.

## 디렉토리

| 폴더 | 의미 | 권한 |
|---|---|---|
| `raw/` | Layer 1 — 원본 source | LLM은 읽기만, immutable |
| `wiki/` | Layer 2 — LLM이 컴파일한 markdown | LLM이 자유 R/W |
| `harness/` | runtime, tools, trace, eval, policy | 마이그레이션 PR로만 변경 |
| `evals/golden/` | 골든 테스트 케이스 (YAML) | 새 feature는 여기 케이스 먼저 추가 |

## 핵심 문서

| 파일 | 역할 |
|---|---|
| `identity.md` | 비서가 누구인지 — 어조·거절 룰·우선순위 |
| `CLAUDE.md` | 운영 schema — 디렉토리 규칙·답변 양식·compile 절차 |

## 실행

```bash
make install           # uv venv + 의존성
make serve             # Web GUI + API → http://127.0.0.1:8765
make check             # CI 풀세트 (lint + typecheck + test)
```

**Web GUI** (`make serve` 후 브라우저): 채팅으로 Edith에게 질문/요청, ☀️ Brief(오늘 일정·메일·digest·헬스), ✋ Approvals(외부 write 승인 큐), 📊 Traces(실행 기록).

**Telegram**: bot 연결 시 `/start` `/help` `/brief` + 자연어 질문. 진입 토폴로지는 [`docs/03_network_topology.md`](docs/03_network_topology.md).

조작 surface는 GUI(브라우저) · Telegram · CLI(`harness ...`) · iPhone Shortcut 넷 다 같은 runtime을 친다.

## 빅픽쳐 / 문서

| 문서 | 내용 |
|---|---|
| [`docs/01_strategy.md`](docs/01_strategy.md) | **전략** — 비전(Knowledge Twin), 문제 정의, 8개 task domain, 자동화 5단계, 3-zone 격리, two-channel surface, 3-tier 배포 |
| [`docs/02_roadmap.md`](docs/02_roadmap.md) | **실행 로드맵** — Phase 0/1/2/3, harness 7개 컴포넌트 (H1-H7), 12개 feature (F1-F12), 12주 흐름 |
| [`identity.md`](identity.md) | 비서 정체성 (Edith) — 어조·거절 룰·Push 정책·anti-atrophy |
| [`CLAUDE.md`](CLAUDE.md) | 운영 schema (Karpathy Layer 3) — 디렉토리 규칙·답변 양식·compile 절차 |

## 다음 단계

- Phase 1 (Week 1-3) — Harness Foundation: H1 Runtime → H2 Tool Registry → ... → H7 Memory Hooks
- Phase 2 (Week 3-5) — LLM Wiki Compilation: `harness compile` + 5개 씨앗 entity 페이지
- Phase 3 (Week 5-12) — Features F1-F12 (각각 eval YAML 먼저, 구현 PR 나중)
