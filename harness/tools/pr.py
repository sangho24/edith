"""pr_review LLM tool — F7. 로컬 .patch / .diff 파일에 대해 heuristic review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.integrations.github_pr import LocalPRSource, review
from harness.state import Context
from harness.tools import Tool


def _pr_review(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    diff_path_arg = args.get("diff_path")
    if not diff_path_arg:
        return {"ok": False, "error": "diff_path 필요"}
    path = Path(diff_path_arg).expanduser()
    if not path.is_absolute():
        path = ctx.edith_home / path
    if not path.exists():
        return {"ok": False, "error": f"diff file not found: {path}"}

    src = LocalPRSource(path, title_str=args.get("title", path.stem))
    r = review(src)
    return {
        "ok": True,
        "title": r.title,
        "n_files": r.n_files,
        "n_added": r.n_added,
        "n_removed": r.n_removed,
        "n_issues": len(r.issues),
        "severity_counts": r.severity_counts,
        "issues": [
            {
                "type": i.type,
                "severity": i.severity,
                "note": i.note,
                "line_no": i.line_no,
                "snippet": i.snippet,
            }
            for i in r.issues
        ],
    }


PR_REVIEW = Tool(
    name="pr_review",
    description=(
        "로컬 PR diff 파일 (.patch / .diff)에 대해 heuristic 1차 리뷰. "
        "TODO/FIXME, 큰 diff, missing docstring, no tests, secret leak 검출. read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "diff_path": {
                "type": "string",
                "description": "diff 파일 경로 (절대 또는 edith_home 기준 relative)",
            },
            "title": {"type": "string", "description": "PR 제목 (선택)"},
        },
        "required": ["diff_path"],
    },
    fn=_pr_review,
)
