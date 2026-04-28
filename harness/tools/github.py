"""github_workflow_get_cron — GitHub Actions workflow의 cron schedule read.

write 도구 (github_workflow_update_cron)는 EXTERNAL_WRITE_TOOLS에 등록되어 R2가 차단.
F5 approval queue 완성 후 활성화 예정. 그 전까지 cron 변경은 `harness gh-cron set` CLI 직접.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.integrations.github_workflow import get_crons, parse_cron_to_kst
from harness.state import Context
from harness.tools import Tool


def _github_workflow_get_cron(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    workflow_path_arg = args.get("workflow_path")
    if workflow_path_arg:
        path = Path(workflow_path_arg).expanduser()
    else:
        env = os.environ.get("EDITH_DS_DIGEST_WORKFLOW")
        if not env:
            return {
                "ok": False,
                "error": "workflow_path arg 또는 EDITH_DS_DIGEST_WORKFLOW env 필요",
            }
        path = Path(env).expanduser()

    if not path.exists():
        return {"ok": False, "error": f"workflow not found: {path}"}

    crons = get_crons(path)
    items = []
    for c in crons:
        kst = parse_cron_to_kst(c)
        items.append(
            {
                "cron": c,
                "kst_time": f"{kst[0]:02d}:{kst[1]:02d}" if kst else None,
            }
        )
    return {"ok": True, "workflow": str(path), "n": len(items), "schedules": items}


GITHUB_WORKFLOW_GET_CRON = Tool(
    name="github_workflow_get_cron",
    description=(
        "GitHub Actions workflow YAML의 schedule.cron 조회. KST 시간 자동 변환. read-only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "workflow_path": {
                "type": "string",
                "description": "workflow YAML 절대 경로 (없으면 EDITH_DS_DIGEST_WORKFLOW env 사용)",
            },
        },
    },
    fn=_github_workflow_get_cron,
)
