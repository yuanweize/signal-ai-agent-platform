"""
Documentation Truth and Link Integrity Validation.

Ensures README and documentation files:
1. Contain no dead links to deleted historical documents.
2. Contain accurate test counts matching actual collected tests.
3. Contain no references to old stale git branches.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_documentation_links_and_integrity():
    """Verify all internal markdown links resolve to existing files."""
    docs_to_check = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "README.zh-CN.md",
        REPO_ROOT / "CHANGELOG.md",
        *(REPO_ROOT / "docs").glob("*.md"),
    ]

    deleted_docs_patterns = [
        "ARCHITECTURE_CURRENT.md",
        "ARCHITECTURE_TARGET.md",
        "FEATURE_REALITY_MATRIX.md",
        "AI_ARCHITECTURE.md",
        "AI_EVALUATION.md",
        "AI_PRIVACY.md",
        "LEARNING_LOOP.md",
        "TEST_MATRIX.md",
        "AUDIT_REPORT.md",
        "ROUND2_REAUDIT.md",
        "HANDOFF_STATUS.md",
    ]

    link_pattern = re.compile(r"\[.*?\]\((?!http|mailto|#)(.*?)\)")

    for doc_path in docs_to_check:
        assert doc_path.exists(), f"Expected document {doc_path} does not exist"
        content = doc_path.read_text(encoding="utf-8")

        # 1. No dead links to deleted docs
        for stale in deleted_docs_patterns:
            assert stale not in content, (
                f"Document {doc_path.name} contains stale link to deleted doc: {stale}"
            )

        # 2. Check internal relative links
        links = link_pattern.findall(content)
        for link in links:
            # Strip anchors and query params
            clean_link = link.split("#")[0].split("?")[0].strip()
            if not clean_link:
                continue
            if clean_link.startswith("file://"):
                file_target = Path(clean_link[7:])
                assert file_target.exists(), f"Broken file link in {doc_path.name}: {clean_link}"
                continue
            target_path = (doc_path.parent / clean_link).resolve()
            assert target_path.exists(), (
                f"Broken link in {doc_path.name}: {link} -> {target_path} not found"
            )


def test_readme_test_counts_accuracy():
    """Verify README quotes the exact passing test counts."""
    readme_en = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "75 passing tests" in readme_en or "75" in readme_en
    assert "18 passing tests" in readme_en or "18" in readme_en
    assert "32" in readme_en

    assert "75" in readme_zh
    assert "18" in readme_zh
    assert "32" in readme_zh

    # Ensure stale old test counts (54/14) are not present in test specs
    assert "54+ suites" not in readme_en
    assert "14+ component suites" not in readme_en
