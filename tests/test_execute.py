"""C1 — 빌드 하네스 StepExecutor 테스트.

runner·commit_fn을 inject해서 오케스트레이션 로직(순서·재시도·상태 전이·
컨텍스트 누적·가드레일 주입)을 실제 `claude` subprocess 없이 검증.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from execute import StepExecutor, StepResult  # noqa: E402


class RecordingRunner:
    """호출 prompt를 기록하고, 미리 정한 결과를 순서대로 반환."""

    def __init__(self, results: list[StepResult] | None = None) -> None:
        self.results = results or []
        self.prompts: list[str] = []
        self._default = StepResult(ok=True, output="done")

    def __call__(self, prompt: str) -> StepResult:
        self.prompts.append(prompt)
        idx = len(self.prompts) - 1
        return self.results[idx] if idx < len(self.results) else self._default


class RecordingCommit:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


def _setup_task(
    tmp_path: Path, n_steps: int = 3, statuses: list[str] | None = None
) -> Path:
    """tmp_path를 repo_root로, phases/demo/ 에 task 셋업. phases_dir 반환."""
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\nEdith 운영 schema.\n", encoding="utf-8")
    (tmp_path / "identity.md").write_text("# identity\nEdith 정체성.\n", encoding="utf-8")
    phases = tmp_path / "phases"
    task = phases / "demo"
    task.mkdir(parents=True)
    steps = []
    for i in range(n_steps):
        slug = f"step-{i + 1}"
        (task / f"step{i + 1}.md").write_text(
            f"# {slug}\n\n작업: 데모 step {i + 1} 수행.\n", encoding="utf-8"
        )
        steps.append(
            {
                "slug": slug,
                "file": f"step{i + 1}.md",
                "status": (statuses[i] if statuses else "pending"),
            }
        )
    (task / "index.json").write_text(
        json.dumps(
            {"name": "demo", "status": "pending", "started_at": None, "steps": steps},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return phases


def _make(tmp_path: Path, **kw) -> StepExecutor:
    phases = kw.pop("phases", None) or _setup_task(tmp_path, kw.pop("n_steps", 3))
    return StepExecutor("demo", phases_dir=phases, repo_root=tmp_path, **kw)


# ── 기본 순차 실행 ────────────────────────────────────────────────────


def test_runs_all_steps_in_order(tmp_path: Path) -> None:
    runner = RecordingRunner()
    commit = RecordingCommit()
    report = _make(tmp_path, runner=runner, commit_fn=commit).run()
    assert report.ok
    assert report.completed == ["step-1", "step-2", "step-3"]
    assert len(runner.prompts) == 3
    assert commit.messages == [
        "build(demo): step-1",
        "build(demo): step-2",
        "build(demo): step-3",
    ]


def test_index_status_persisted(tmp_path: Path) -> None:
    phases = _setup_task(tmp_path)
    StepExecutor(
        "demo", phases_dir=phases, repo_root=tmp_path,
        runner=RecordingRunner(), commit_fn=RecordingCommit(),
    ).run()
    index = json.loads((phases / "demo" / "index.json").read_text(encoding="utf-8"))
    assert index["status"] == "completed"
    assert index["started_at"] is not None
    assert index["completed_at"] is not None
    assert all(s["status"] == "completed" for s in index["steps"])


# ── 완료 step skip ────────────────────────────────────────────────────


def test_skips_completed_steps(tmp_path: Path) -> None:
    phases = _setup_task(tmp_path, n_steps=3, statuses=["completed", "pending", "pending"])
    runner = RecordingRunner()
    report = StepExecutor(
        "demo", phases_dir=phases, repo_root=tmp_path,
        runner=runner, commit_fn=RecordingCommit(),
    ).run()
    assert report.skipped == ["step-1"]
    assert report.completed == ["step-2", "step-3"]
    assert len(runner.prompts) == 2  # step-1은 runner 호출 안 함


# ── 재시도 ────────────────────────────────────────────────────────────


def test_retries_then_succeeds(tmp_path: Path) -> None:
    runner = RecordingRunner(
        [
            StepResult(ok=False, error="첫 시도 실패"),
            StepResult(ok=True, output="두 번째 성공"),
        ]
    )
    report = _make(tmp_path, n_steps=1, runner=runner, commit_fn=RecordingCommit()).run()
    assert report.ok
    assert report.completed == ["step-1"]
    assert len(runner.prompts) == 2
    assert "재시도 2/3" in runner.prompts[1]
    assert "첫 시도 실패" in runner.prompts[1]


def test_blocked_after_3_failures(tmp_path: Path) -> None:
    runner = RecordingRunner([StepResult(ok=False, error="계속 실패")] * 3)
    commit = RecordingCommit()
    report = _make(tmp_path, n_steps=3, runner=runner, commit_fn=commit).run()
    assert not report.ok
    assert report.blocked == "step-1"
    assert len(runner.prompts) == 3  # step-1만 3회, step-2/3는 시도 안 함
    assert commit.messages == []  # 실패 step은 커밋 안 함


def test_blocked_status_persisted(tmp_path: Path) -> None:
    phases = _setup_task(tmp_path, n_steps=2)
    runner = RecordingRunner([StepResult(ok=False, error="x")] * 3)
    StepExecutor(
        "demo", phases_dir=phases, repo_root=tmp_path,
        runner=runner, commit_fn=RecordingCommit(),
    ).run()
    index = json.loads((phases / "demo" / "index.json").read_text(encoding="utf-8"))
    assert index["status"] == "blocked"
    assert index["steps"][0]["status"] == "blocked"
    assert index["steps"][1]["status"] == "pending"


# ── dry-run ───────────────────────────────────────────────────────────


def test_dry_run_calls_nothing(tmp_path: Path) -> None:
    phases = _setup_task(tmp_path)
    runner = RecordingRunner()
    commit = RecordingCommit()
    report = StepExecutor(
        "demo", phases_dir=phases, repo_root=tmp_path,
        runner=runner, commit_fn=commit, dry_run=True,
    ).run()
    assert report.dry_run
    assert runner.prompts == []
    assert commit.messages == []
    # index.json 안 건드림
    index = json.loads((phases / "demo" / "index.json").read_text(encoding="utf-8"))
    assert index["status"] == "pending"


# ── 가드레일 주입 + 컨텍스트 누적 ─────────────────────────────────────


def test_guardrails_injected_into_prompt(tmp_path: Path) -> None:
    runner = RecordingRunner()
    _make(tmp_path, n_steps=1, runner=runner, commit_fn=RecordingCommit()).run()
    assert "Edith 운영 schema" in runner.prompts[0]  # CLAUDE.md
    assert "Edith 정체성" in runner.prompts[0]  # identity.md
    assert "step-1" in runner.prompts[0]


def test_context_accumulates_across_steps(tmp_path: Path) -> None:
    runner = RecordingRunner(
        [
            StepResult(ok=True, output="step1이 만든 산출물 ABC"),
            StepResult(ok=True, output="step2 done"),
        ]
    )
    _make(tmp_path, n_steps=2, runner=runner, commit_fn=RecordingCommit()).run()
    # step-2 prompt에 step-1 산출 요약이 들어있어야
    assert "step1이 만든 산출물 ABC" in runner.prompts[1]
    assert "이전 step 산출 요약" in runner.prompts[1]
    # step-1 prompt엔 누적 컨텍스트 없음
    assert "이전 step 산출 요약" not in runner.prompts[0]


def test_missing_task_raises(tmp_path: Path) -> None:
    phases = tmp_path / "phases"
    phases.mkdir()
    with pytest.raises(FileNotFoundError, match="task index"):
        StepExecutor("nope", phases_dir=phases, repo_root=tmp_path).run()
