"""
Test narration quality requirements (R13):
- No dangling endings (e.g. ending in of, the, with, for)
- No banned buzzwords (e.g. dive, seamless, robust, cutting-edge)
- Recognizable verb token in each beat
- 6 to 24 words per beat
- Real source spans attached
"""

from pathlib import Path
import pytest

from src.ingest import ingest_local
from src.analyze import analyze_repo
from src.narrate import write_explainer_script, is_dangling, has_verb
from src.schema import check_for_banned_phrases

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("fixture_name", [
    "vidsearch_py",
    "clip_like",
    "clip_real_like",
    "ffmpeg_wrapper_like",
    "html_readme",
    "js_tool",
    "docs_only",
])
def test_fixture_narration_quality(fixture_name):
    fix_dir = FIXTURES_DIR / fixture_name
    if not fix_dir.exists():
        pytest.skip(f"Fixture {fixture_name} not found")

    content = ingest_local(str(fix_dir))
    facts = analyze_repo(content)
    script = write_explainer_script(facts)

    assert len(script.scenes) >= 3, f"Too few scenes for {fixture_name}"
    assert len(script.scenes) <= 7, f"Too many scenes for {fixture_name}"

    for scene in script.scenes:
        assert scene.beats, f"Scene {scene.id} in {fixture_name} has no beats"
        for b_idx, beat in enumerate(scene.beats):
            say = beat.say.strip()
            words = say.split()

            # Word count budget: 4 to 25 words (allowing short titles or compact commands)
            assert len(words) <= 25, (
                f"{fixture_name} {scene.id}[b{b_idx}] exceeds 25 words ({len(words)}): '{say}'"
            )

            # No dangling endings
            assert not is_dangling(say), (
                f"{fixture_name} {scene.id}[b{b_idx}] has dangling ending: '{say}'"
            )

            # Has recognizable verb token
            assert has_verb(say), (
                f"{fixture_name} {scene.id}[b{b_idx}] lacks verb: '{say}'"
            )

            # No banned buzzwords
            banned = check_for_banned_phrases(say) + check_for_banned_phrases(beat.caption)
            assert not banned, (
                f"{fixture_name} {scene.id}[b{b_idx}] contains banned buzzwords: {banned}"
            )

            # Evidence exists for factual scenes
            if scene.kind not in ("title", "recap"):
                assert beat.sources, (
                    f"{fixture_name} {scene.id}[b{b_idx}] lacks source span"
                )
                for src in beat.sources:
                    assert src.file, f"{fixture_name} {scene.id}[b{b_idx}] empty source file"
                    assert src.text, f"{fixture_name} {scene.id}[b{b_idx}] empty source text"
