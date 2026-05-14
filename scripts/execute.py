"""C1 — 빌드 하네스 StepExecutor.

`phases/<task>/`의 step{N}.md를 순차 실행하는 오케스트레이터.
설계: docs/05_cc_harness.md §2 Phase E.

각 step마다:
1. 가드레일(CLAUDE.md + identity.md) + 이전 step 산출 요약 + step 지시문을 prompt로 합성
2. runner 호출 (기본: `claude` CLI subprocess) — 실패 시 최대 3회 재시도
3. 성공 → commit_fn 호출 + step status=completed + 산출 요약 누적
4. 3회 실패 → status=blocked, 중단

runner와 commit_fn은 inject 가능 (telegram.http_post / relay.forward_fn 패턴).
이 덕분에 오케스트레이션 로직(순서·재시도·상태 전이·컨텍스트 누적)은 실제
`claude` subprocess 없이 100% 단위 테스트 가능.

CLI:
    python scripts/execute.py <task-name>
    python scripts/execute.py <task-name> --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MAX_RETRIES = 3
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_BLOCKED = "blocked"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class StepResult:
    """runner 호출 결과."""

    ok: bool
    output: str = ""
    error: str = ""


# runner: step prompt → 실행 결과. 기본은 `claude` CLI subprocess.
RunnerFn = Callable[[str], StepResult]
# commit_fn: commit message → 변경분 커밋. 기본은 `git add -A && git commit`.
CommitFn = Callable[[str], None]


def _default_runner(prompt: str) -> StepResult:
    """`claude` CLI를 subprocess로 호출 (비대화형 1-shot)."""
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except FileNotFoundError:
        return StepResult(ok=False, error="`claude` CLI not found in PATH")
    except subprocess.TimeoutExpired:
        return StepResult(ok=False, error="claude CLI timed out (30min)")
    if proc.returncode != 0:
        return StepResult(ok=False, output=proc.stdout, error=proc.stderr)
    return StepResult(ok=True, output=proc.stdout)


def _default_commit(message: str) -> None:
    """변경분 전체를 커밋. 변경 없으면 조용히 통과."""
    subprocess.run(["git", "add", "-A"], check=True)
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True
    )
    if status.returncode == 0:
        return  # staged 변경 없음
    subprocess.run(["git", "commit", "-m", message], check=True)


@dataclass
class Step:
    slug: str
    file: str
    status: str = STATUS_PENDING


@dataclass
class ExecutionReport:
    task_name: str
    completed: list[str] = field(default_factory=list)
    blocked: str | None = None
    skipped: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.blocked is None


class StepExecutor:
    """phases/<task>/ step들을 순차 실행."""

    def __init__(
        self,
        task_name: str,
        *,
        phases_dir: Path,
        repo_root: Path | None = None,
        runner: RunnerFn | None = None,
        commit_fn: CommitFn | None = None,
        dry_run: bool = False,
    ) -> None:
        self.task_name = task_name
        self.phases_dir = phases_dir
        self.repo_root = repo_root or phases_dir.parent
        self.runner = runner or _default_runner
        self.commit_fn = commit_fn or _default_commit
        self.dry_run = dry_run
        self.task_dir = phases_dir / task_name
        self.index_path = self.task_dir / "index.json"

    # ── JSON I/O ──────────────────────────────────────────────────────
    def _load_index(self) -> dict:
        if not self.index_path.exists():
            raise FileNotFoundError(f"task index 없음: {self.index_path}")
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict) -> None:
        if self.dry_run:
            return
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # ── 가드레일·prompt 합성 ──────────────────────────────────────────
    def _guardrails(self) -> str:
        parts: list[str] = []
        for fname in ("CLAUDE.md", "identity.md"):
            fpath = self.repo_root / fname
            if fpath.exists():
                parts.append(f"## {fname}\n\n{fpath.read_text(encoding='utf-8')}")
        return "\n\n".join(parts)

    def _build_prompt(self, step: Step, accumulated: list[str]) -> str:
        step_text = (self.task_dir / step.file).read_text(encoding="utf-8")
        sections = [
            "# 가드레일 — 반드시 준수 (Edith 운영 schema·정체성)",
            self._guardrails(),
        ]
        if accumulated:
            sections.append("# 이전 step 산출 요약 (컨텍스트 누적)")
            sections.append("\n".join(f"- {a}" for a in accumulated))
        sections.append(f"# 이번 step 지시 — {step.slug}")
        sections.append(step_text)
        return "\n\n".join(sections)

    # ── 실행 ──────────────────────────────────────────────────────────
    def run(self) -> ExecutionReport:
        index = self._load_index()
        steps = [Step(**s) for s in index["steps"]]
        report = ExecutionReport(task_name=self.task_name, dry_run=self.dry_run)
        accumulated: list[str] = []

        if not self.dry_run and index.get("started_at") is None:
            index["started_at"] = _now()
        index["status"] = STATUS_IN_PROGRESS

        for i, step in enumerate(steps):
            if step.status == STATUS_COMPLETED:
                report.skipped.append(step.slug)
                accumulated.append(f"{step.slug}: (이전 실행에서 완료됨)")
                continue

            prompt = self._build_prompt(step, accumulated)

            if self.dry_run:
                print(f"[dry-run] step {i + 1}/{len(steps)} · {step.slug}")
                print(f"          file={step.file} · prompt {len(prompt)} chars")
                report.completed.append(step.slug)
                continue

            result = self._run_step_with_retries(step, prompt)
            steps[i].status = step.status
            index["steps"] = [vars(s) for s in steps]

            if not result.ok:
                step.status = STATUS_BLOCKED
                index["steps"][i]["status"] = STATUS_BLOCKED
                index["status"] = STATUS_BLOCKED
                self._save_index(index)
                report.blocked = step.slug
                return report

            step.status = STATUS_COMPLETED
            index["steps"][i]["status"] = STATUS_COMPLETED
            self._save_index(index)
            self.commit_fn(f"build({self.task_name}): {step.slug}")
            report.completed.append(step.slug)
            accumulated.append(f"{step.slug}: {result.output.strip()[:200]}")

        if not self.dry_run:
            index["status"] = STATUS_COMPLETED
            index["completed_at"] = _now()
            self._save_index(index)
        return report

    def _run_step_with_retries(self, step: Step, prompt: str) -> StepResult:
        last = StepResult(ok=False, error="not run")
        for attempt in range(1, MAX_RETRIES + 1):
            step.status = STATUS_IN_PROGRESS
            call_prompt = prompt
            if attempt > 1:
                call_prompt = (
                    f"{prompt}\n\n# 재시도 {attempt}/{MAX_RETRIES} — 직전 실패\n{last.error}"
                )
            last = self.runner(call_prompt)
            if last.ok:
                return last
        return last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Edith 빌드 하네스 step executor")
    parser.add_argument("task_name", help="phases/ 아래 task 디렉토리 이름")
    parser.add_argument(
        "--phases-dir", default="phases", help="phases 디렉토리 (기본: phases)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="runner·commit 호출 없이 실행 계획만 출력"
    )
    args = parser.parse_args(argv)

    executor = StepExecutor(
        args.task_name,
        phases_dir=Path(args.phases_dir),
        dry_run=args.dry_run,
    )
    report = executor.run()

    if report.dry_run:
        print(f"\n[dry-run] {report.task_name}: {len(report.completed)} step 예정")
        return 0
    if report.blocked:
        print(f"✗ {report.task_name}: '{report.blocked}'에서 막힘 (3회 재시도 실패)")
        return 1
    print(
        f"✓ {report.task_name}: {len(report.completed)} 완료"
        f"{f', {len(report.skipped)} skip' if report.skipped else ''}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
