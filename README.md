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

## Phase 0 demo

```bash
echo "테스트 — 오늘 X에 대해 생각함" > raw/captures/$(date +%F)_test.md
ls raw/captures/
```

이 시점에 LLM은 아직 동작하지 않습니다. 그게 의도된 것입니다.
**"raw is immutable, wiki is LLM-owned, schema is the config"** 원칙이 layout에 박힌 게 Phase 0의 산출물입니다.

## 다음 단계

- Phase 1 (Week 1-3) — Harness Foundation: H1 Runtime → H2 Tool Registry → ... → H7 Memory Hooks
- Phase 2 (Week 3-5) — LLM Wiki Compilation: `harness compile` + 5개 씨앗 entity 페이지
- Phase 3 (Week 5-12) — Features F1-F12 (각각 eval YAML 먼저, 구현 PR 나중)
