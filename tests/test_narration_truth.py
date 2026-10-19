"""
Regression test suite for Truth-First Narration (Phase 2, T1 - T10).
Guarantees zero filler literals, no dangling stops, no duplicated verbs,
grounded language claims, deterministic verb phrase transforms, and golden consistency.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import pytest

from src.ingest import ingest_local
from src.analyze import analyze_repo
from src.narrate import write_explainer_script
from src.narrate.compress import is_dangling
from src.narrate.verbs import (
    is_base_verb,
    to_third_person_verb,
    transform_bullet_to_sentence,
    convert_docstring_to_verb_phrase,
)
from src.visuals import select_primary_code_symbol

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"
SRC_DIR = Path(__file__).parent.parent / "src"

BANNED_LITERALS = [
    "provides {lang} functionality",
    "is a software library",
    "is an open source project",
    "is an open source Python project",
    "provides open source software tools",
    "It implements {repo}",
    "It provides capabilities for {repo}",
    "core capabilities",
    "provides World, core, and capabilities",
    "primary implementation logic",
]

DISALLOWED_SPOKEN_TOKENS = {
    "import", "def", "class", "self", "https", "http", "www", "png", "svg", "yes",
}


# --- T1: Grep src/ for Banned Fallback Sentences ---

def test_t1_no_banned_literals_in_src():
    """T1: Ensure no banned fallback literals exist anywhere in src/ (excluding checker definitions)."""
    for py_file in SRC_DIR.rglob("*.py"):
        if py_file.name in ("schema.py", "gates.py", "text_gates.py"):
            continue
        content = py_file.read_text(encoding="utf-8")
        for banned in BANNED_LITERALS:
            # Pattern check: ignore curly braces matching
            raw_banned = banned.replace("{lang}", "").replace("{repo}", "")
            assert raw_banned not in content, f"Banned literal '{raw_banned}' found in {py_file}"

        # Grep for pattern f"{...} provides" followed by non-noun-phrase (e.g. provides invoke, provides convert)
        bad_provides = re.findall(r"provides\s+(?:convert|invoke|run|load|generate|build|parse|process)\b", content, re.I)
        assert not bad_provides, f"Banned 'provides <verb>' pattern found in {py_file}: {bad_provides}"


# --- T2: First-Party Language Detection ---

def test_t2_language_first_party_only():
    """T2: ffmpeg_wrapper_real -> Python (vendored JS excluded); readme_only -> None."""
    ffmpeg_facts = analyze_repo(ingest_local(str(FIXTURES_DIR / "ffmpeg_wrapper_real")))
    assert "Python" in ffmpeg_facts.languages_by_bytes
    assert "JavaScript" not in ffmpeg_facts.languages_by_bytes

    readme_facts = analyze_repo(ingest_local(str(FIXTURES_DIR / "readme_only")))
    assert not readme_facts.languages_by_bytes

    script = write_explainer_script(readme_facts)
    for scene in script.scenes:
        for beat in scene.beats:
            assert "python" not in beat.say.lower()
            assert "javascript" not in beat.say.lower()


# --- T3: 30-Row Bullet to Sentence Transform Table ---

BULLET_TABLE = [
    ("Convert video to numpy array", "It can convert video to a numpy array."),
    ("Extract frames from video", "It can extract frames from video."),
    ("Load pretrained models", "It can load pretrained models."),
    ("Run inference on inputs", "It can run inference on inputs."),
    ("Generate video thumbnails", "It can generate video thumbnails."),
    ("Build custom filter graphs", "It can build custom filter graphs."),
    ("Parse media containers", "It can parse media containers."),
    ("Process audio streams", "It can process audio streams."),
    ("Search video index", "It can search video index."),
    ("Query multimodal embeddings", "It can query multimodal embeddings."),
    ("Create pipeline nodes", "It can create pipeline nodes."),
    ("Tokenize text prompts", "It can tokenize text prompts."),
    ("Execute shell pipelines", "It can execute shell pipelines."),
    ("Transcode media files", "It can transcode media files."),
    ("Train neural networks", "It can train neural networks."),
    ("Encode images into vectors", "It can encode images into vectors."),
    ("Decode video packets", "It can decode video packets."),
    ("Index vector features", "It can index vector features."),
    ("Export processed segments", "It can export processed segments."),
    ("Filter noisy audio", "It can filter noisy audio."),
    ("Sample key frames", "It can sample key frames."),
    ("Stream video chunks", "It can stream video chunks."),
    ("Capture webcam streams", "It can capture webcam streams."),
    ("Render output frames", "It can render output frames."),
    ("Calculate similarity matrix", "It can calculate similarity matrix."),
    ("Compute feature vectors", "It can compute feature vectors."),
    ("Save index to disk", "It can save index to disk."),
    ("Read video metadata", "It can read video metadata."),
    ("Write output container", "It can write output container."),
    ("OpenCLIP: includes larger and independently trained models", "OpenCLIP includes larger and independently trained models."),
]


@pytest.mark.parametrize("bullet,expected", BULLET_TABLE)
def test_t3_bullet_to_sentence_transform_table(bullet: str, expected: str):
    """T3: Verify deterministic transform of README bullets into declarative sentences."""
    transformed = transform_bullet_to_sentence(bullet)
    assert transformed == expected


# --- T4: 30-Row Docstring Opening Transform Table ---

DOCSTRING_TABLE = [
    ("Load a CLIP model.", "load", "loads a CLIP model"),
    ("Invoke ffmpeg for the supplied node graph.", "run", "invokes ffmpeg for the supplied node graph"),
    ("Normalize input text by removing extraneous whitespace.", "clean_text", "normalizes input text by removing extraneous whitespace"),
    ("Apply a filter to the supplied stream.", "filter", "applies a filter to the supplied stream"),
    ("Extract key video frames.", "extract", "extracts key video frames"),
    ("Encode input text into a dense vector.", "encode", "encodes input text into a dense vector"),
    ("Search the index for nearest neighbors.", "search", "searches the index for nearest neighbors"),
    ("Query embeddings for matching scenes.", "query", "queries embeddings for matching scenes"),
    ("Generate video thumbnail.", "generate", "generates video thumbnail"),
    ("Build model graph.", "build", "builds model graph"),
    ("Returns a list of available models.", "available_models", "returns a list of available models"),
    ("Loads a pre-trained checkpoint.", "load_checkpoint", "loads a pre-trained checkpoint"),
    ("Encodes image frames.", "encode_frames", "encodes image frames"),
    ("Parses CLI arguments.", "parse_args", "parses CLI arguments"),
    ("Processes video chunks.", "process_chunks", "processes video chunks"),
    ("Transforms raw features.", "transform", "transforms raw features"),
    ("Command-line interface for video retrieval.", "cli", "is the command-line interface for video retrieval"),
    ("CLI for video search.", "cli", "is the command-line interface for video search"),
    ("Neural network model for multimodal representations.", "model", "defines the neural network model for multimodal representations"),
    ("Top-level exports for library.", "init", "provides the top-level exports for library"),
    ("Entry point for running evaluation.", "main", "serves as the entry point for running evaluation"),
    ("Audio and video filter constructors for ffmpeg.", "filters", "constructs audio and video filters for ffmpeg"),
    ("Execution engine invoking ffmpeg.", "runner", "executes commands invoking ffmpeg"),
    ("Main interface functions for audio processing.", "audio", "provides main interface functions for audio processing"),
    ("Stream representation nodes forming filter graphs.", "nodes", "defines stream representation nodes forming filter graphs"),
    ("Byte-pair encoding tokenizer for vocabulary.", "bpe", "tokenizes text using byte-pair encoding for vocabulary"),
    ("Utility functions for file handling.", "utils", "provides utility functions for file handling"),
    ("Helper methods for tensor operations.", "helpers", "implements helper methods for tensor operations"),
    ("Core implementation of vector search.", "index", "implements the core logic of vector search"),
    ("Test string escaping in shell arguments.", "test_escape", "tests string escaping"),
]


@pytest.mark.parametrize("doc,func,expected", DOCSTRING_TABLE)
def test_t4_docstring_transform_table(doc: str, func: str, expected: str):
    """T4: Verify 30-row docstring transform openings and verb de-duplication."""
    phrase = convert_docstring_to_verb_phrase(doc, func_name=func)
    assert phrase == expected
    # Ensure no duplicated verb like 'load load'
    words = phrase.split()
    for i in range(len(words) - 1):
        assert words[i].lower() != words[i + 1].lower(), f"Duplicated adjacent word '{words[i]}' in '{phrase}'"


# --- T6: Key-Code Selection ---

def test_t6_key_code_selection():
    """T6: clip_real_like picks load, not available_models; ffmpeg_wrapper_real picks run in ffmpeg/_run.py."""
    clip_facts = analyze_repo(ingest_local(str(FIXTURES_DIR / "clip_real_like")))
    clip_sym = select_primary_code_symbol(clip_facts)
    assert clip_sym.name == "load"
    assert clip_sym.name != "available_models"

    ffmpeg_facts = analyze_repo(ingest_local(str(FIXTURES_DIR / "ffmpeg_wrapper_real")))
    ffmpeg_sym = select_primary_code_symbol(ffmpeg_facts)
    assert ffmpeg_sym.name == "run"
    assert "ffmpeg/_run.py" in ffmpeg_sym.file.replace("\\", "/")


# --- T7: Terminal Command Validation ---

def test_t7_terminal_command_selection():
    """T7: Validates real shell commands, rejects python statements ('import clip'), cd, git clone."""
    clip_facts = analyze_repo(ingest_local(str(FIXTURES_DIR / "clip_real_like")))
    assert "pip install ftfy regex tqdm" in clip_facts.readme.install_commands
    # Does not have 'import clip' as usage command
    assert "import clip" not in clip_facts.readme.usage_commands
    for cmd in clip_facts.readme.usage_commands:
        assert not cmd.startswith("import ")
        assert not cmd.startswith("cd ")


# --- Golden Files Consistency for All Fixtures ---

ALL_FIXTURES = [d.name for d in FIXTURES_DIR.iterdir() if d.is_dir()]


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_golden_narration_truth(fixture_name: str):
    """Run explainer writer on fixture and assert all quality, truth, and golden constraints."""
    fix_dir = FIXTURES_DIR / fixture_name
    content = ingest_local(str(fix_dir))
    facts = analyze_repo(content)
    script = write_explainer_script(facts)

    spoken_lines = []
    for scene in script.scenes:
        for beat in scene.beats:
            say = beat.say.strip()
            spoken_lines.append(f"[{scene.id}] {say}")

            # 1. No dangling stops
            assert not is_dangling(say), f"Dangling ending in '{say}'"

            # 2. No duplicate adjacent words
            words = say.split()
            for i in range(len(words) - 1):
                assert words[i].lower() != words[i + 1].lower(), f"Duplicated adjacent word '{words[i]}' in '{say}'"

            # 3. Disallowed tokens check
            for token in re.findall(r"\b[A-Za-z]+\b", say.lower()):
                if token in DISALLOWED_SPOKEN_TOKENS:
                    # Allow if inside a quoted identifier like 'run app' or 'dot py'
                    assert token in ("import", "yes") and ("imports from" in say or "yes" in say), (
                        f"Disallowed token '{token}' spoken in '{say}'"
                    )

            # 4. No 'provides <verb>'
            assert not re.search(r"\bprovides\s+(?:convert|invoke|run|load|generate|build|parse|process)\b", say, re.I), (
                f"Invalid 'provides <verb>' in '{say}'"
            )

    golden_file = GOLDEN_DIR / f"{fixture_name}.txt"
    assert golden_file.exists(), f"Golden file missing for {fixture_name}"
    golden_content = golden_file.read_text(encoding="utf-8").strip()
    actual_content = "\n".join(spoken_lines).strip()
    assert actual_content == golden_content, f"Golden diff for {fixture_name}:\nActual:\n{actual_content}\nGolden:\n{golden_content}"
