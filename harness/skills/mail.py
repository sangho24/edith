"""mail skill — F3 Gmail triage."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import mail

SKILL = Skill(
    name="mail",
    scope="any",
    tools=[mail.MAIL_TRIAGE, mail.MAIL_SEARCH],
    eval_globs=["evals/golden/f3_mail_triage.yaml"],
    channels=["telegram", "email"],
)
