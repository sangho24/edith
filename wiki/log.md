# Compile Log

> 시계열 일지 (append only). LLM이 raw → wiki 컴파일 또는 schema 개선 제안 시 한 줄 append.

## 형식

```
YYYY-MM-DD HH:MM · raw/<source> → wiki/<target> (요약)
YYYY-MM-DD HH:MM · 모순 발견 → contradictions.md (entities/<name>.md)
YYYY-MM-DD HH:MM · 정책 차단 → reason: <reason>
YYYY-MM-DD HH:MM · 새 페이지 → wiki/<path> (entity|concept|summary)
```

## 진입

(빈 상태 — Phase 1 H7 Memory Hooks 동작 시점부터 자동 누적)

## schema 개선 제안

2026-05-14 · Phase 4 H8 skill registry 도입. CLAUDE.md "Tool 사용 규칙" 섹션이 `harness/tools/`만 언급하는데, tool은 이제 `harness/skills/<name>.py`의 Skill manifest로 묶여 등록됨. 제안: "Tool 사용 규칙"을 "Skill·Tool 사용 규칙"으로 갱신하고, "새 feature는 eval YAML 먼저" 룰이 `Skill.eval_globs`로 강제됨을 명시. (자기 갱신 정책에 따라 CLAUDE.md는 사용자가 직접 수정.)
