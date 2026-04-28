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
