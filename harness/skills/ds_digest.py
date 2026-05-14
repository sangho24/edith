"""ds-digest skill — F4 사용자 본인의 DS 뉴스레터(sangho24/ds-digest) 연동.

현재: read-only (digest_latest) + ds-digest의 GitHub Actions cron 조회.
다음 단계: GitHubPagesDigestSource(latest.json fetch), morning brief 편입.
digest에 *기여*(소스 추가 등)는 external write → request_approval 게이트 필요.
"""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import digest, github

SKILL = Skill(
    name="ds-digest",
    scope="personal",
    tools=[digest.DIGEST_LATEST, github.GITHUB_WORKFLOW_GET_CRON],
    eval_globs=["evals/golden/f14_ds_digest.yaml"],
    channels=["telegram", "email"],
)
