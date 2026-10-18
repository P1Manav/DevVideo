#!/usr/bin/env python3
"""
Quality check tool: Generates scripts (no video rendering) for every test fixture,
evaluates extractive narration quality, specificity, and provenance gates,
and prints the full narration.

Exits 0 if all fixtures pass quality checks; exits 1 on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingest import ingest_local
from src.analyze import analyze_repo
from src.plan import OfflinePlanner
from src.schema import check_for_banned_phrases

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
JUNK_TOKENS = {
    "def", "class", "import", "return", "self", "https", "http",
    "www", "com", "png", "svg", "blog", "badge", "img",
}


def check_fixture_quality(fixture_dir: Path) -> tuple[bool, list[str]]:
    """Evaluate one fixture's generated narration against quality gates."""
    errors = []
    content = ingest_local(str(fixture_dir))
    facts = analyze_repo(content)
    planner = OfflinePlanner()
    script = planner.plan(facts)

    print(f"\n========================================================")
    print(f"FIXTURE: {fixture_dir.name} ({len(script.scenes)} scenes)")
    print(f"========================================================")

    full_narration_lines = []
    recap_start_file = None

    for s_idx, scene in enumerate(script.scenes, start=1):
        print(f"\n[{s_idx}] Scene '{scene.id}' ({scene.kind}):")
        for b_idx, beat in enumerate(scene.beats, start=1):
            print(f"  Beat {b_idx}: \"{beat.say}\"")
            print(f"    Caption: \"{beat.caption}\" | Focus: {beat.focus}")
            if beat.sources:
                for src in beat.sources:
                    print(f"    Source: {src.file}:{src.start_line}-{src.end_line} -> \"{src.text[:60]}\"")
            full_narration_lines.append(beat.say)

            # 1. Check banned phrases
            banned = check_for_banned_phrases(beat.say) + check_for_banned_phrases(beat.caption)
            if banned:
                errors.append(f"Scene '{scene.id}' beat {b_idx} contains banned buzzwords: {banned}")

            # 2. Check junk tokens
            words = [w.lower().strip(".,!?:;\"'()") for w in beat.say.split()]
            junk_found = [w for w in words if w in JUNK_TOKENS]
            if len(junk_found) >= 2:
                errors.append(f"Scene '{scene.id}' beat {b_idx} has >=2 junk tokens: {junk_found}")

            # 3. Check for gibberish template patterns
            say_lower = beat.say.lower()
            gibberish_patterns = [
                "we explore",
                "this project organizes",
                "structured solutions for",
                "primary implementation logic",
                "developer workflows",
                "provides critical",
                "powers multimodal",
            ]
            for pat in gibberish_patterns:
                if pat in say_lower:
                    errors.append(f"Scene '{scene.id}' beat {b_idx} contains gibberish pattern: '{pat}'")

            # 4. Check word budget
            if len(beat.say.split()) > 22:
                errors.append(f"Scene '{scene.id}' beat {b_idx} exceeds 22 words ({len(beat.say.split())} words)")

            # 5. Provenance check for non-title/recap
            if scene.kind not in ("title", "recap"):
                if not beat.sources:
                    errors.append(f"Scene '{scene.id}' beat {b_idx} lacks required SourceSpan")

        if scene.kind == "recap":
            for b in scene.beats:
                if "start with" in b.say.lower():
                    recap_start_file = b.caption.replace("Start with ", "").strip()

    # Fixture-specific assertions
    fname = fixture_dir.name
    full_text = " ".join(full_narration_lines).lower()

    if fname == "clip_like":
        # First sentence of CLIP should be about contrastive language-image
        if "contrastive" not in full_text and "language-image" not in full_text:
            errors.append("clip_like narration missing core idea ('contrastive language-image')")
        if "blog" in script.scenes[0].beats[0].say.lower():
            errors.append("clip_like title narration used link text 'blog' instead of real prose")

    if fname == "vidsearch_py":
        if "vidsearch" not in full_text:
            errors.append("vidsearch_py narration missing repo name")

    # Recap file check: when code exists, recap must start with a code file, never README/LICENSE
    has_code = any(f.endswith((".py", ".js", ".ts")) for f in facts.tree)
    if has_code and recap_start_file:
        if recap_start_file.lower().startswith(("readme", "license")):
            errors.append(f"Recap suggests starting with '{recap_start_file}' instead of code file")

    passed = len(errors) == 0
    return passed, errors


def main() -> int:
    fixtures = [
        FIXTURES_DIR / "vidsearch_py",
        FIXTURES_DIR / "clip_like",
        FIXTURES_DIR / "html_readme",
        FIXTURES_DIR / "js_tool",
        FIXTURES_DIR / "docs_only",
    ]

    all_passed = True
    total_errors = 0

    print("================================================================")
    print("DevVideo Narration & Script Quality Check Harness")
    print("================================================================")

    for fix in fixtures:
        if not fix.exists():
            print(f"[SKIP] Fixture {fix.name} not found")
            continue

        passed, errors = check_fixture_quality(fix)
        if passed:
            print(f"\n>>> RESULT [{fix.name}]: PASSED (All quality gates green)")
        else:
            print(f"\n>>> RESULT [{fix.name}]: FAILED ({len(errors)} errors):")
            for err in errors:
                print(f"    - {err}")
            all_passed = False
            total_errors += len(errors)

    print("\n----------------------------------------------------------------")
    if all_passed:
        print(f"[OK] All {len(fixtures)} fixtures PASSED narration quality check!")
        return 0
    else:
        print(f"[FAIL] Quality check failed with {total_errors} errors across fixtures.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
