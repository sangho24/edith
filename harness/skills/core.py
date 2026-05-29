"""core skill — wiki·raw·util 원시 tool. scope 무관, 항상 on."""

from __future__ import annotations

from harness.skills import Skill
from harness.tools import raw, util, wiki

SKILL = Skill(
    name="core",
    scope="any",
    tools=[
        wiki.WIKI_READ,
        wiki.WIKI_WRITE,
        wiki.WIKI_SEARCH,
        raw.RAW_READ,
        raw.RAW_LIST,
        raw.CAPTURE_TEXT,
        util.QUERY_DB,
        util.REQUEST_APPROVAL,
        util.EMIT_LOG,
    ],
    eval_globs=[
        "evals/golden/h1_smoke.yaml",
        "evals/golden/h4_eval_self.yaml",
        "evals/golden/h7_frontmatter.yaml",
        "evals/golden/w1_compile_basic.yaml",
        "evals/golden/f1_capture_via_llm.yaml",
        "evals/golden/f4_morning_brief.yaml",
        "evals/golden/f5_approval_flow.yaml",
        "evals/golden/a2_wiki_scope_block.yaml",
        "evals/golden/f20_call_demo.yaml",
        "evals/golden/f20_call_raises.yaml",
    ],
)
