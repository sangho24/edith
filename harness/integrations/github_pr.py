"""Phase 3 F7 — GitHub PR Review.

PRSource ABC + LocalPRSource (.patch / .diff 파일 읽기, test/dev) +
GitHubPRSource (placeholder, F7.x에서 PAT + REST API).

issue 분류 (heuristic, no LLM):
- todo_marker: TODO/FIXME/HACK 새 라인
- large_diff: 추가 라인 ≥500
- missing_docstring: 새 public Python def에 docstring 없음
- no_tests: 소스 변경 있는데 tests/ 변경 없음
- secret_leak: API key / token 패턴 매치
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["low", "medium", "high"]


@dataclass
class PRIssue:
    type: str
    severity: Severity
    note: str
    line_no: int | None = None
    snippet: str | None = None


class PRSource(ABC):
    @abstractmethod
    def diff(self) -> str: ...

    @abstractmethod
    def title(self) -> str: ...


class LocalPRSource(PRSource):
    """diff 파일에서 직접 읽기 — test/dev 용."""

    def __init__(self, diff_path: Path, title_str: str = "") -> None:
        self.diff_path = diff_path
        self.title_str = title_str or diff_path.stem

    def diff(self) -> str:
        if not self.diff_path.exists():
            return ""
        return self.diff_path.read_text(encoding="utf-8")

    def title(self) -> str:
        return self.title_str


class GitHubPRSource(PRSource):
    """GitHub REST API. F7.x에서 PAT 통합 후 활성화."""

    def __init__(self, owner: str, repo: str, pr_number: int, token_path: Path | None = None):
        self.owner = owner
        self.repo = repo
        self.pr_number = pr_number
        self.token_path = token_path or Path.home() / ".config" / "edith" / "github_token"

    def diff(self) -> str:
        if not self.token_path.exists():
            raise RuntimeError(f"GitHub PAT 미설정 ({self.token_path}). F7.x에서 통합 예정.")
        raise NotImplementedError("F7.x에서 GitHub REST API 통합")

    def title(self) -> str:
        if not self.token_path.exists():
            raise RuntimeError(f"GitHub PAT 미설정 ({self.token_path})")
        raise NotImplementedError("F7.x에서 GitHub REST API 통합")


# ── heuristic issue detection ──

_TODO_PATTERN = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_PUBLIC_DEF_PATTERN = re.compile(r"^\s*def\s+([a-z][a-zA-Z0-9_]*)\s*\(")
_DOCSTRING_START = re.compile(r'^\s*"""')
# secret patterns (subset of policies.PII_PATTERNS, just keys)
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("aws_key", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("gh_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
]


def _added_lines(diff_text: str) -> list[tuple[int, str]]:
    """returns [(line_no, content), ...] for + lines."""
    out = []
    for i, line in enumerate(diff_text.splitlines(), start=1):
        if line.startswith("+") and not line.startswith("+++"):
            out.append((i, line[1:]))
    return out


def _changed_files(diff_text: str) -> list[str]:
    """+++ b/path/to/file.py 라인에서 파일 경로 추출."""
    files = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[len("+++ b/") :].strip())
    return files


def find_issues(diff_text: str) -> list[PRIssue]:
    issues: list[PRIssue] = []
    if not diff_text.strip():
        return issues

    added = _added_lines(diff_text)
    files = _changed_files(diff_text)

    # 1. TODO/FIXME markers
    for ln, content in added:
        if _TODO_PATTERN.search(content):
            issues.append(
                PRIssue(
                    type="todo_marker",
                    severity="low",
                    note="TODO/FIXME/HACK 마커가 새 코드에 추가됨",
                    line_no=ln,
                    snippet=content.strip()[:100],
                )
            )

    # 2. Large diff
    n_added = len(added)
    if n_added >= 500:
        issues.append(
            PRIssue(
                type="large_diff",
                severity="medium",
                note=f"추가 라인 {n_added}개 — PR을 작게 나누는 것 추천",
            )
        )

    # 3. Missing docstring on new public def
    expecting_docstring_for: str | None = None
    for ln, content in added:
        m = _PUBLIC_DEF_PATTERN.match(content)
        if m:
            expecting_docstring_for = m.group(1)
            continue
        if expecting_docstring_for and content.strip():
            if not _DOCSTRING_START.match(content):
                issues.append(
                    PRIssue(
                        type="missing_docstring",
                        severity="low",
                        note=f"새 public 함수 `{expecting_docstring_for}`에 docstring 없음",
                        line_no=ln,
                    )
                )
            expecting_docstring_for = None

    # 4. Source change without tests
    src_files = [f for f in files if not f.startswith("tests/") and f.endswith(".py")]
    test_files = [f for f in files if f.startswith("tests/") or "test_" in f.split("/")[-1]]
    if src_files and not test_files:
        issues.append(
            PRIssue(
                type="no_tests",
                severity="medium",
                note=f"소스 {len(src_files)}개 변경, tests/ 변경 없음",
            )
        )

    # 5. Secret leak (high severity!)
    for ln, content in added:
        for name, pat in _SECRET_PATTERNS:
            if pat.search(content):
                issues.append(
                    PRIssue(
                        type="secret_leak",
                        severity="high",
                        note=f"잠재적 secret 패턴 매치: {name}",
                        line_no=ln,
                        snippet=content.strip()[:60] + "...",
                    )
                )

    return issues


@dataclass
class PRReview:
    title: str
    n_files: int
    n_added: int
    n_removed: int
    issues: list[PRIssue] = field(default_factory=list)

    @property
    def severity_counts(self) -> dict[Severity, int]:
        counts: dict[Severity, int] = {"low": 0, "medium": 0, "high": 0}
        for i in self.issues:
            counts[i.severity] += 1
        return counts

    def render_text(self) -> str:
        lines = [
            f"PR review: {self.title}",
            f"files: {self.n_files} · +{self.n_added} -{self.n_removed}",
        ]
        c = self.severity_counts
        if not self.issues:
            lines.append("✓ 발견된 이슈 없음")
            return "\n".join(lines)
        lines.append(f"issues: high={c['high']} · medium={c['medium']} · low={c['low']}")
        icons = {"high": "❗", "medium": "⚠️", "low": "·"}
        for i in self.issues:
            ln = f" L{i.line_no}" if i.line_no else ""
            lines.append(f"  {icons[i.severity]} [{i.type}]{ln} {i.note}")
            if i.snippet:
                lines.append(f"     {i.snippet}")
        return "\n".join(lines)


def review(source: PRSource) -> PRReview:
    diff = source.diff()
    n_added = sum(
        1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    n_removed = sum(
        1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    files = _changed_files(diff)
    return PRReview(
        title=source.title(),
        n_files=len(files),
        n_added=n_added,
        n_removed=n_removed,
        issues=find_issues(diff),
    )
