"""
Unit and regression tests for src/analyze.py.

Tests:
- Python AST import graph and symbol extraction
- CLI flag extraction from argparse
- JS/TS import graph extraction
- README cleaning (HTML tags, badges, images, link syntax stripped)
- Repo with no README does NOT crash (P4 regression test)
- Domain relevance word-boundary scoring (E3 regression test: CSS lib vs Video repo)
- Non-Python / docs-only degradation
"""

from pathlib import Path
import pytest

from src.ingest import ingest_local, RepoContent
from src.analyze import (
    analyze_repo,
    clean_readme,
    compute_domain_relevance,
    RepoFacts,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VIDSEARCH_DIR = FIXTURES_DIR / "vidsearch_py"
JS_TOOL_DIR = FIXTURES_DIR / "js_tool"
DOCS_ONLY_DIR = FIXTURES_DIR / "docs_only"
HTML_README_DIR = FIXTURES_DIR / "html_readme"


class TestReadmeCleaning:
    def test_strip_html_tags_and_badges(self):
        """Clean README strips HTML tags, badges, and image links."""
        raw = (
            '<div align="center">\n'
            '  <p><img src="logo.png" alt="Logo"/></p>\n'
            '  <h1>Project Title</h1>\n'
            '  <a href="https://badge"><img src="badge.svg"/></a>\n'
            '</div>\n\n'
            'This is the real description.\n\n'
            '## Installation\n\n'
            '```bash\npip install foo\n```\n'
        )
        cleaned = clean_readme(raw)
        assert cleaned.title == "Project Title"
        assert "This is the real description" in cleaned.description
        assert "<div" not in cleaned.description
        assert "Installation" in cleaned.sections
        assert len(cleaned.code_fences) == 1
        assert "pip install foo" in cleaned.code_fences[0]

    def test_empty_or_none_readme(self):
        """Regression test for P4: None or empty README returns clean defaults without crashing."""
        cleaned_none = clean_readme(None)
        assert cleaned_none.title == ""
        assert cleaned_none.description == ""
        assert cleaned_none.code_fences == []

        cleaned_empty = clean_readme("   ")
        assert cleaned_empty.title == ""


class TestDomainRelevance:
    def test_word_boundary_avoids_maintain_ai_false_positive(self):
        """Regression test for E3: 'maintain' containing 'ai' must not trigger AI relevance."""
        text = "This is a CSS framework to maintain clean layouts and maintainable stylesheets."
        score, matched = compute_domain_relevance(text)
        assert score == 0.0
        assert "ai" not in matched
        assert len(matched) == 0

    def test_video_repo_relevance_high(self):
        """Video understanding project receives high relevance score >= 0.35."""
        text = "VidSearch video frame embedding retrieval index faiss vector search multimodal"
        score, matched = compute_domain_relevance(text)
        assert score >= 0.35
        assert "video" in matched
        assert "frame" in matched
        assert "retrieval" in matched
        assert "faiss" in matched


class TestAnalyzeVidsearchPy:
    def test_analyze_vidsearch_py_facts(self):
        """Analyzes vidsearch_py fixture and extracts complete facts."""
        content = ingest_local(str(VIDSEARCH_DIR))
        facts = analyze_repo(content)

        assert isinstance(facts, RepoFacts)
        assert facts.repo_name == "vidsearch_py"
        assert facts.languages_by_bytes.get("Python", 0) > 0
        assert facts.is_video_relevant is True
        assert facts.relevance_score >= 0.35

        # README cleaned
        assert facts.readme.title == "VidSearch"
        assert "<p" not in facts.readme.description
        assert "<img" not in facts.readme.description

        # CLI flags extracted
        assert "--query" in facts.cli_flags
        assert "--index" in facts.cli_flags

        # Entry points detected
        assert any("cli.py" in ep or "__main__.py" in ep for ep in facts.entry_points)

        # Internal import edges
        edge_pairs = [(e.source, e.target) for e in facts.import_graph]
        assert any("embed.py" in src and "frames.py" in dst for src, dst in edge_pairs) or \
               any("cli.py" in src and "search.py" in dst for src, dst in edge_pairs)

        # Top symbols
        names = [s.name for s in facts.top_symbols]
        assert "extract_keyframes" in names
        assert "search_video_index" in names


class TestAnalyzeJSTool:
    def test_analyze_js_tool_facts(self):
        """Analyzes JS tool fixture and extracts JS imports and package entry points."""
        content = ingest_local(str(JS_TOOL_DIR))
        facts = analyze_repo(content)

        assert facts.languages_by_bytes.get("JavaScript", 0) > 0
        assert any("bin/main.js" in ep for ep in facts.entry_points)
        assert any("commander" in dep for dep in facts.dependencies)


class TestAnalyzeDocsOnly:
    def test_analyze_docs_only_degrades_cleanly(self):
        """Degrades cleanly for documentation-only repos without crashing."""
        content = ingest_local(str(DOCS_ONLY_DIR))
        facts = analyze_repo(content)

        assert facts.readme.title == "Video Retrieval Guide"
        assert len(facts.top_symbols) == 0
        assert len(facts.import_graph) == 0
        assert len(facts.tree) > 0


class TestNoReadmeRepo:
    def test_no_readme_repo_never_crashes(self, tmp_path):
        """Regression test for P4: repo with no README produces valid RepoFacts."""
        code_file = tmp_path / "hello.py"
        code_file.write_text("def hello():\n    return 'world'\n")

        content = ingest_local(str(tmp_path))
        facts = analyze_repo(content)

        assert facts.readme.title == ""
        assert facts.readme.description == ""
        assert len(facts.top_symbols) == 1
        assert facts.top_symbols[0].name == "hello"
