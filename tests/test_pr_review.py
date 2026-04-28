"""Phase 3 F7 — PR Review heuristic tests.

머지 기준: 5 sample PR → issue 발견 ≥80% (사람 리뷰 대비), false positive ≤20%.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.integrations.github_pr import (
    GitHubPRSource,
    LocalPRSource,
    find_issues,
    review,
)

# ── unit: find_issues ──


def test_no_issues_clean_diff() -> None:
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
+def add(a, b):
+    \"\"\"adds two numbers.\"\"\"
+    return a + b
diff --git a/tests/test_x.py b/tests/test_x.py
+++ b/tests/test_x.py
+def test_add():
+    \"\"\"check add.\"\"\"
+    assert add(1, 2) == 3
"""
    assert find_issues(diff) == []


def test_todo_marker_detected() -> None:
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
+def hack():
+    # TODO: refactor this later
+    pass
"""
    issues = find_issues(diff)
    types = [i.type for i in issues]
    assert "todo_marker" in types


def test_fixme_detected() -> None:
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
+# FIXME: edge case
+x = 1
"""
    issues = find_issues(diff)
    assert any(i.type == "todo_marker" for i in issues)


def test_large_diff_detected() -> None:
    added_lines = "\n".join(f"+    line{i} = {i}" for i in range(550))
    diff = f"diff --git a/x.py b/x.py\n+++ b/x.py\n{added_lines}\n"
    issues = find_issues(diff)
    assert any(i.type == "large_diff" for i in issues)


def test_missing_docstring_detected() -> None:
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
+def public_fn(a, b):
+    return a + b
"""
    issues = find_issues(diff)
    assert any(i.type == "missing_docstring" for i in issues)


def test_private_fn_no_docstring_check() -> None:
    """`_private` 함수는 docstring 없어도 OK."""
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
+def _private(x):
+    return x * 2
"""
    issues = find_issues(diff)
    assert not any(i.type == "missing_docstring" for i in issues)


def test_no_tests_detected() -> None:
    diff = """diff --git a/harness/x.py b/harness/x.py
+++ b/harness/x.py
+def foo():
+    \"\"\"foo.\"\"\"
+    pass
"""
    issues = find_issues(diff)
    assert any(i.type == "no_tests" for i in issues)


def test_tests_present_no_warning() -> None:
    diff = """diff --git a/harness/x.py b/harness/x.py
+++ b/harness/x.py
+def foo(): pass
diff --git a/tests/test_x.py b/tests/test_x.py
+++ b/tests/test_x.py
+def test_foo(): pass
"""
    issues = find_issues(diff)
    assert not any(i.type == "no_tests" for i in issues)


def test_secret_leak_detected_anthropic() -> None:
    diff = """diff --git a/cfg.py b/cfg.py
+++ b/cfg.py
+API_KEY = "sk-ant-api03-XXXXXXXXXXXXXXXXXXXXabc123def456"
"""
    issues = find_issues(diff)
    assert any(i.type == "secret_leak" and i.severity == "high" for i in issues)


def test_secret_leak_aws() -> None:
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
+aws = "AKIAIOSFODNN7EXAMPLE"
"""
    issues = find_issues(diff)
    assert any(i.type == "secret_leak" for i in issues)


def test_empty_diff() -> None:
    assert find_issues("") == []


# ── 5 sample PRs accuracy ──


def test_5_sample_prs_accuracy() -> None:
    """F7 머지 기준 — 5개 sample PR에서 known issue 발견율 ≥80%."""
    samples = [
        # PR 1: clean — 0 issues
        (
            """diff --git a/harness/x.py b/harness/x.py
+++ b/harness/x.py
+def helper():
+    \"\"\"clean.\"\"\"
+    return 42
diff --git a/tests/test_x.py b/tests/test_x.py
+++ b/tests/test_x.py
+def test_helper(): assert True
""",
            set(),
        ),
        # PR 2: TODO + missing_docstring + no_tests
        (
            """diff --git a/harness/y.py b/harness/y.py
+++ b/harness/y.py
+def public_fn(x):
+    # TODO: validate input
+    return x
""",
            {"todo_marker", "missing_docstring", "no_tests"},
        ),
        # PR 3: secret leak (high)
        (
            """diff --git a/secrets.py b/secrets.py
+++ b/secrets.py
+ANTHROPIC = "sk-ant-api03-XXXXXXXXXXXXXXXXXXXXabc"
""",
            {"secret_leak", "no_tests"},
        ),
        # PR 4: FIXME marker
        (
            """diff --git a/x.py b/x.py
+++ b/x.py
+def public_fn():
+    \"\"\"docs.\"\"\"
+    # FIXME: edge case
+    return 1
diff --git a/tests/test_x.py b/tests/test_x.py
+++ b/tests/test_x.py
+def test_x(): pass
""",
            {"todo_marker"},
        ),
        # PR 5: large diff
        (
            "diff --git a/big.py b/big.py\n+++ b/big.py\n"
            + "\n".join(f"+    line{i}" for i in range(550))
            + "\ndiff --git a/tests/test_big.py b/tests/test_big.py\n"
            + "+++ b/tests/test_big.py\n+def test_x(): pass\n",
            {"large_diff"},
        ),
    ]
    correct = 0
    total_known = 0
    false_positives = 0
    for diff, expected_types in samples:
        issues = find_issues(diff)
        actual_types = {i.type for i in issues}
        for et in expected_types:
            total_known += 1
            if et in actual_types:
                correct += 1
        # FP: actual에 있는데 expected에 없는 type
        false_positives += len(actual_types - expected_types)

    if total_known:
        recall_rate = correct / total_known
        assert recall_rate >= 0.80, f"recall {recall_rate:.0%} < 80%"
    # false positive rate over total issues found
    total_issues = sum(len(find_issues(d)) for d, _ in samples)
    fp_rate = false_positives / max(total_issues, 1)
    assert fp_rate <= 0.20, f"FP rate {fp_rate:.0%} > 20%"


# ── PRSource ──


def test_local_pr_source(tmp_path: Path) -> None:
    diff_text = "diff --git a/x b/x\n+++ b/x\n+abc\n"
    p = tmp_path / "pr.diff"
    p.write_text(diff_text, encoding="utf-8")
    src = LocalPRSource(p, title_str="Add abc")
    assert src.title() == "Add abc"
    assert src.diff() == diff_text


def test_local_pr_source_missing(tmp_path: Path) -> None:
    src = LocalPRSource(tmp_path / "missing.diff")
    assert src.diff() == ""


def test_review_aggregates(tmp_path: Path) -> None:
    diff = """diff --git a/x.py b/x.py
+++ b/x.py
-old
+new line 1
+new line 2
"""
    p = tmp_path / "x.diff"
    p.write_text(diff, encoding="utf-8")
    r = review(LocalPRSource(p))
    assert r.n_added == 2
    assert r.n_removed == 1
    assert r.n_files == 1


def test_github_pr_source_raises_unconfigured(tmp_path: Path) -> None:
    src = GitHubPRSource("o", "r", 1, token_path=tmp_path / "missing")
    with pytest.raises(RuntimeError):
        src.diff()
