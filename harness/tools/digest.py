"""digest_latest tool — F4/F14 ds-digest 최근 결과 read."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.integrations.ds_digest import LocalDigestSource, get_digest_source
from harness.state import Context
from harness.tools import Tool


def _digest_latest(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    # 명시적 로컬 경로(테스트·고정 fixture)가 최우선.
    fixture_env = os.environ.get("EDITH_DS_DIGEST_LATEST")
    if fixture_env:
        return LocalDigestSource(Path(fixture_env)).latest()
    # 그 외 — EDITH_DS_DIGEST_URL 있으면 GitHub Pages, 없으면 로컬.
    return get_digest_source(ctx.edith_home).latest()


DIGEST_LATEST = Tool(
    name="digest_latest",
    description="ds-digest (DS 큐레이션 파이프라인)의 가장 최근 결과 read. read-only.",
    input_schema={"type": "object", "properties": {}},
    fn=_digest_latest,
)
