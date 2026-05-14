# 05 · Claude Code 빌드 하네스 — Edith를 단계적으로 짓는 메타 하네스

> 2026-05-14 v0.1 · 설계 문서
> 참조: [jha0313/harness_framework](https://github.com/jha0313/harness_framework)
> 대상: Edith feature를 Claude Code로 구현할 때 "어떻게 쪼개고, 어떻게 실행하고, 어떻게 가드레일을 거는가"

---

## 0. 두 개의 하네스를 구분한다

Edith에는 이름은 같지만 **층위가 다른 하네스 두 개**가 있다.

| | **런타임 하네스** (`harness/`) | **빌드 하네스** (이 문서) |
|---|---|---|
| 언제 도는가 | Edith가 사용자 질문에 답할 때 | 개발자가 Edith feature를 구현할 때 |
| 무엇을 돌리는가 | LLM agent loop (input→action→obs) | Claude Code를 step 단위로 |
| 산출물 | trace, wiki 갱신, 답변 | 커밋된 코드 + 통과한 eval |
| 핵심 파일 | `harness/runtime.py` | `scripts/execute.py` (설계 대상) |
| 가드레일 | `policy.allow()` · eval · trace | CLAUDE.md 주입 · golden eval 게이트 · step 격리 |

`docs/02_roadmap.md`가 말하는 "harness-first"는 **런타임 하네스**를 먼저 짓는다는 뜻이고,
이 문서는 그 런타임 하네스 위에 feature(F1-F12)를 **얹는 작업 자체를 규율**하는 빌드 하네스다.

jha0313/harness_framework는 후자에 해당한다 — generic Claude Code를 *disciplined step executor*로 바꾸는 config.
Karpathy의 Layer 3가 generic agent를 *disciplined wiki maintainer*로 바꾸는 것과 같은 발상의, 빌드타임 버전.

---

## 1. 왜 빌드 하네스가 필요한가

지금까지 PR 1-19는 사람이 머릿속으로 쪼개서 Claude Code에 통째로 던졌다. 잘 굴러왔지만 세 가지 한계가 있다.

1. **컨텍스트 재구성 비용** — 새 세션마다 "지금 어디까지 했고 뭘 해야 하는지"를 사람이 다시 설명한다. `docs/04_session_2026-04-29.md`가 그 부트스트랩 비용의 증거.
2. **스코프 드리프트** — 한 PR이 여러 레이어를 건드리면 리뷰가 어렵고, 깨졌을 때 원인 격리가 안 된다. PR 16이 두 번 커밋된 것(`2152ea1`, `e760ca4`)이 그 사례.
3. **검증의 비일관성** — eval-first 룰(CLAUDE.md)이 있지만, 강제하는 건 사람의 규율뿐. step 정의 자체에 검증 명령이 박혀 있지 않다.

빌드 하네스는 이 셋을 **step 파일의 구조로** 강제한다. step이 self-contained면 컨텍스트 재구성이 0이고, step이 한 레이어면 드리프트가 없고, step에 validation 명령이 박혀 있으면 검증이 빠질 수 없다.

---

## 2. 5-페이즈 워크플로우

jha0313의 A-E를 Edith 규칙(eval-first, 3-zone, harness-first)에 맞춰 옮긴 것.

```
Phase A  Exploration   docs/ 읽고 현재 상태 파악
Phase B  Discussion    결정 필요한 것 사용자와 합의
Phase C  Step Design   PR-크기 step으로 분해 (7원칙)
Phase D  File Creation  phases/ 아래 index.json + step{N}.md 생성
Phase E  Execution     scripts/execute.py 가 step을 순차 실행
```

### Phase A — Exploration

`docs/01_strategy.md`(전략) · `docs/02_roadmap.md`(로드맵) · 이 문서 · 관련 wiki 페이지를 읽는다.
넓은 탐색이 필요하면 Explore 에이전트를 병렬로. 산출물 없음 — 머릿속 모델만.

### Phase B — Discussion

구현 전에 **결정이 갈리는 지점**을 사용자에게 올린다. 예: "헬스 데이터 소스 — Apple Health vs 웨어러블 API"는
설계가 완전히 갈리므로 Phase C 전에 합의해야 한다. 이 단계를 건너뛰면 step을 다시 짜야 한다.

### Phase C — Step Design (7원칙)

jha0313의 7원칙을 그대로 채택하되, Edith 항목 2개를 덧붙인다.

| # | 원칙 | Edith 적용 |
|---|---|---|
| 1 | step 하나는 한 레이어/모듈 | `harness/skills/<name>.py` 하나, 또는 integration 하나 |
| 2 | step 파일은 self-contained | 독립 Claude 세션이 step 파일만 읽고 작업 가능해야 |
| 3 | 선행조건을 경로로 명시 | "이 step 전에 읽을 것: docs/05, harness/skills/__init__.py" |
| 4 | 시그니처만 명시, 구현은 에이전트에게 | `def latest() -> dict` 까지만, 본문은 위임 |
| 5 | 검증은 실행 가능한 명령으로 | `uv run pytest tests/test_X.py` — 추상 서술 금지 |
| 6 | 주의사항은 "X 하지 마라 — Y 때문에" 형식 | "tool 파일 이동 금지 — import 경로 28곳 깨짐" |
| 7 | step 이름은 kebab-case slug | `ds-digest-github-pages-source` |
| **E1** | **feature step은 eval YAML을 step 1로** | CLAUDE.md "새 feature는 eval 먼저" 룰. skill manifest의 `eval_globs`가 가리킬 파일을 먼저 만든다 |
| **E2** | **scope를 step manifest에 명시** | 헬스=personal 고정 등. 3-zone leak 방지 |

### Phase D — File Creation

```
phases/
├── index.json                    전체 task 목록 + 상태
└── <task-slug>/
    ├── index.json                step 배열 + 상태 전이
    ├── step1.md                  (feature면) eval YAML 작성
    ├── step2.md                  구현
    └── step3.md                  통합·문서
```

`phases/<task>/step{N}.md` 섹션 고정:

```markdown
# step2 · ds-digest-github-pages-source

## 선행조건 (읽을 것)
- docs/05_cc_harness.md
- harness/integrations/ds_digest.py
- phases/ds-digest-skill/step1.md  (이번 task의 eval)

## 작업
harness/integrations/ds_digest.py 에 GitHubPagesDigestSource 추가.
시그니처: `class GitHubPagesDigestSource(DigestSource): def latest(self) -> dict`
https://sangho24.github.io/ds-digest/latest.json 을 fetch.

## 수용 기준
- DigestSource 인터페이스 준수
- 네트워크 실패 시 {"date": None, "items": [], "n": 0} 반환

## 검증
uv run pytest tests/test_ds_digest.py -q
uv run ruff check harness/integrations/ds_digest.py

## 하지 말 것
- LocalDigestSource 삭제 금지 — 오프라인 fallback으로 유지
- requests 추가 금지 — httpx 이미 의존성에 있음
```

### Phase E — Execution

`scripts/execute.py`의 `StepExecutor` (설계, 미구현):

- `phases/<task>/`의 step을 **순차 실행**. step{N} 끝나야 step{N+1} 시작.
- 매 step마다 **가드레일 주입**: `CLAUDE.md` + `identity.md` + step의 선행조건 파일들을 Claude Code 컨텍스트에 prepend.
- **컨텍스트 누적**: 완료된 step의 산출 요약을 다음 step에 전달.
- **에러 복구**: step 실패 시 에러 메시지를 붙여 최대 3회 재시도. 3회 실패면 `blocked` 마킹 후 중단.
- **git 통합**: task 시작 시 `feat-<task-slug>` 브랜치 생성, step별 timestamped 커밋. (Edith는 지금 main 직커밋 — 빌드 하네스 도입 시 브랜치 전환 권장.)
- **상태 추적**: `index.json`에 `pending | completed | blocked | error` + `created_at/started_at/completed_at` 타임스탬프.

```
python3 scripts/execute.py ds-digest-skill
python3 scripts/execute.py ds-digest-skill --push
```

---

## 3. 런타임 하네스와의 접점

빌드 하네스의 step 검증 명령은 런타임 하네스의 게이트를 그대로 호출한다 — **두 하네스가 같은 eval을 공유**한다.

```
빌드 하네스 step 검증        런타임 하네스 게이트
─────────────────────       ──────────────────────
uv run pytest          ───→  tests/ (328개)
uv run harness eval    ───→  evals/golden/*.yaml (H4)
                             skill.eval_globs (harness/skills/)
```

그래서 빌드 하네스가 새로 만드는 건 *오케스트레이션*뿐이고, *판정 기준*은 이미 런타임 하네스에 있다.
skill 추상화(`harness/skills/`) 도입으로 이 접점이 더 깔끔해졌다 — feature step의 산출물이
"skill 파일 1개 + eval_globs가 가리키는 YAML"로 정형화되기 때문.

---

## 4. 도입 순서 (현황)

| step | 내용 | 검증 | 상태 |
|---|---|---|---|
| 1 | `phases/` 골격 + `phases/index.json` 스키마 | `phases/b4-golden-evals/` 레퍼런스 | ✅ 2026-05-14 |
| 2 | `scripts/execute.py` `StepExecutor` (재시도·상태·컨텍스트 누적) | `tests/test_execute.py` (10 tests, runner·commit inject) | ✅ 2026-05-14 |
| 3 | `.claude/commands/build.md` 슬래시 커맨드 (Phase A-E 가이드) | dry-run 1회 확인 | ✅ 2026-05-14 |
| 4 | 첫 실전 task — `b4-golden-evals` (papers/repo/jd skill에 golden 추가) | golden eval 통과 | 준비됨 — 사용자 실행 대기 |

**검증 보완** (실 `claude` subprocess를 이 환경에서 못 돌리는 문제):
- runner·commit_fn을 inject 가능하게 설계 → 오케스트레이션 로직은 mock으로 100% 단위 테스트.
- `--dry-run` → runner·commit 호출 없이 실행 계획만 출력. `python scripts/execute.py b4-golden-evals --dry-run`.
- 첫 실전 task를 **저위험**으로 선정 (`b4-golden-evals`는 기존 로직 안 건드리고 golden YAML만 추가 — 헛짓해도 피해가 YAML 몇 개).

step 4 실행은 사용자가 `python scripts/execute.py b4-golden-evals`로 1회 실검증 — 자기 자신을 자기 자신으로 검증한다.

### v1이 아직 안 하는 것
- `feat-<task>` 브랜치 자동 생성 — v1은 현재 브랜치에 step별 커밋. 브랜치 전략은 후속.
- step의 선행조건 파일을 prompt에 자동 첨부 — v1은 가드레일(CLAUDE.md+identity.md)만 주입,
  선행조건은 step.md에 경로로 명시되고 runner(claude)가 직접 읽는다.

---

## 5. 한 줄 정리

> **런타임 하네스가 "Edith가 어떻게 답하는가"를 측정·재현·롤백한다면,
> 빌드 하네스는 "Edith를 어떻게 짓는가"를 step·가드레일·eval 게이트로 규율한다.
> 둘은 같은 eval을 공유하므로, 잘 지어진 것만 머지되고 잘 답하는 것만 남는다.**

---

## 변경 이력

- 2026-05-14 v0.1 — jha0313/harness_framework 참조, 빌드 하네스 5-페이즈 설계 초안. skill 추상화(`harness/skills/`) 도입 직후 작성.
- 2026-05-14 v0.2 — C1 구현 (PR 31). `scripts/execute.py` StepExecutor + `tests/test_execute.py` + `phases/b4-golden-evals/` + `.claude/commands/build.md`. §4 현황 갱신.
