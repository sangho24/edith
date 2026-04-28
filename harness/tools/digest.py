"""digest_latest tool — F4 ds-digest 최근 결과 read."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.integrations.ds_digest import LocalDigestSource
from harness.state import Context
from harness.tools import Tool


def _digest_latest(args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    fixture_env = os.environ.get("EDITH_DS_DIGEST_LATEST")
    fixture_path = (
        Path(fixture_env) if fixture_env else ctx.edith_home / "raw" / "digest" / "latest.json"
    )
    return LocalDigestSource(fixture_path).latest()


DIGEST_LATEST = Tool(
    name="digest_latest",
    description="ds-digest (DS 큐레이션 파이프라인)의 가장 최근 결과 read. read-only.",
    input_schema={"type": "object", "properties": {}},
    fn=_digest_latest,
)
