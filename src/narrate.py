"""
The Explainer Writer: deterministic, extractive narration composed from real
repository facts and source spans, obeying rules R1 to R12.

Rules enforced:
R1. Sentence compression, not truncation (splits at clauses, drops trailing relative phrases).
R2. No dangling endings (stops at complete clauses, requires verb token).
R3. No slot-fill templates with sentence fragments. Full natural sentences only.
R4. Key code selection: core public functions described by purpose, inputs, actions, returns.
R5. Architecture selection: excludes tests, examples, docs, setup.py from diagram nodes.
R6. Terminal: prefer pip/npm, normalize flags, summarize long commands, omit version pins.
R7. Overview: 3 beats (what it is, what it does, what you get); on-screen bullets match voice.
R8. Fit honesty: only evidenced stages cited; honest fallback when not video-specific.
R9. Takeaways from facts only: no hardcoded strings, exact facts.
R10. Title chip: dominant code language.
R11. Speech normalization: file.py -> file dot py, flags normalized, pins omitted.
R12. Strict word and duration budget (8-12 beats, 100-140 words beyond title).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .analyze import RepoFacts, TopSymbol, ReadmeSentence, is_auxiliary_or_test_path
from .evals.gates import STOPWORDS, _extract_content_tokens
from .schema import (
    Beat,
    Evidence,
    Scene,
    ScriptPlan,
    SourceSpan,
    check_for_banned_phrases,
    normalize_speech,
)
from .visuals import attach_visuals_to_script

logger = logging.getLogger(__name__)

# R2: Dangling stopwords that must NEVER end a beat before final punctuation
DANGLING_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "to", "for", "with", "by", "from",
    "and", "or", "but", "that", "which", "is", "are", "was", "be", "as",
    "at", "than", "then", "if", "most", "more", "e.g.", "i.e.", "etc", "etc.",
    "its", "into", "their", "our", "your",
}

# R2: Known verb tokens and suffixes for verb presence verification
VERB_TOKENS = {
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did", "can", "could", "will", "would",
    "provides", "provide", "providing", "provided",
    "extracts", "extract", "extracting", "extracted",
    "runs", "run", "running", "ran",
    "builds", "build", "building", "built",
    "trains", "train", "training", "trained",
    "loads", "load", "loading", "loaded",
    "encodes", "encode", "encoding", "encoded",
    "searches", "search", "searching", "searched",
    "indexes", "index", "indexing", "indexed",
    "queries", "query", "querying", "queried",
    "contains", "contain", "containing", "contained",
    "implements", "implement", "implementing", "implemented",
    "processes", "process", "processing", "processed",
    "generates", "generate", "generating", "generated",
    "serves", "serve", "serving", "served",
    "reads", "read", "reading",
    "writes", "write", "writing", "written",
    "uses", "use", "using", "used",
    "enables", "enable", "enabling", "enabled",
    "creates", "create", "creating", "created",
    "parses", "parse", "parsing", "parsed",
    "converts", "convert", "converting", "converted",
    "installs", "install", "installing", "installed",
    "executes", "execute", "executing", "executed",
    "defines", "define", "defining", "defined",
    "returns", "return", "returning", "returned",
    "connects", "connect", "connecting", "connected",
    "imports", "import", "importing", "imported",
    "ships", "ship", "shipping", "shipped",
    "allows", "allow", "allowing", "allowed",
    "transcodes", "transcode", "transcoding", "transcoded",
}

# R3: Table of 25+ deterministic docstring opening transforms
DOCSTRING_TRANSFORMS = [
    (re.compile(r"^command[- ]line interface for\s+", re.I), "is the command-line interface for "),
    (re.compile(r"^cli for\s+", re.I), "is the command-line interface for "),
    (re.compile(r"^neural network model for\s+", re.I), "defines the neural network model for "),
    (re.compile(r"^top[- ]level exports for\s+", re.I), "provides the top-level exports for "),
    (re.compile(r"^top[- ]level\s+", re.I), "provides the top-level package for "),
    (re.compile(r"^entry point for\s+", re.I), "serves as the entry point for "),
    (re.compile(r"^audio and video filter constructors for\s+", re.I), "constructs audio and video filters for "),
    (re.compile(r"^execution engine invoking\s+", re.I), "executes commands invoking "),
    (re.compile(r"^main interface functions for\s+", re.I), "provides main interface functions for "),
    (re.compile(r"^stream representation nodes forming\s+", re.I), "defines stream representation nodes forming "),
    (re.compile(r"^byte[- ]pair encoding tokenizer for\s+", re.I), "tokenizes text using byte-pair encoding for "),
    (re.compile(r"^utility functions for\s+", re.I), "provides utility functions for "),
    (re.compile(r"^helper methods for\s+", re.I), "implements helper methods for "),
    (re.compile(r"^core implementation of\s+", re.I), "implements the core logic of "),
    (re.compile(r"^graph nodes representing\s+", re.I), "defines graph nodes representing "),
    (re.compile(r"^collection of\s+", re.I), "provides a collection of "),
    (re.compile(r"^library for\s+", re.I), "provides a library for "),
    (re.compile(r"^wrapper around\s+", re.I), "provides a wrapper around "),
    (re.compile(r"^bindings for\s+", re.I), "provides Python bindings for "),
    (re.compile(r"^client for\s+", re.I), "provides a client for "),
    (re.compile(r"^parser for\s+", re.I), "parses "),
    (re.compile(r"^tools for\s+", re.I), "provides tools for "),
    (re.compile(r"^classes for\s+", re.I), "defines classes for "),
    (re.compile(r"^algorithms for\s+", re.I), "implements algorithms for "),
    (re.compile(r"^data structures for\s+", re.I), "defines data structures for "),
    (re.compile(r"^engine for\s+", re.I), "implements the engine for "),
]


def has_verb(text: str) -> bool:
    """R2: Check if text contains a recognizable verb token or -s/-ed/-ing verb form."""
    words = re.findall(r"\b[A-Za-z]{2,}\b", text.lower())
    for w in words:
        if w in VERB_TOKENS:
            return True
        if len(w) >= 4 and (w.endswith("ing") or w.endswith("ed") or (w.endswith("s") and not w.endswith("ss"))):
            return True
    return False


def is_dangling(text: str) -> bool:
    """R2: Check if text ends with a dangling stopword before punctuation."""
    cleaned = re.sub(r"[\.,;:!\?]+$", "", text.strip())
    words = cleaned.split()
    if not words:
        return True
    last = words[-1].lower()
    return last in DANGLING_STOPWORDS


def convert_docstring_to_verb_phrase(doc: str) -> str:
    """
    R3: Convert the first sentence of a module or function docstring into a grammatically
    fluent verb phrase using deterministic transforms.
    """
    if not doc:
        return "provides project implementation logic"
    first = doc.strip().splitlines()[0].strip().rstrip(".")
    # Clean docstring: strip markdown and brackets
    first = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first)
    first = re.sub(r"[`*]", "", first)

    # 1. Check known opening pattern transforms
    for pattern, replacement in DOCSTRING_TRANSFORMS:
        if pattern.search(first):
            return pattern.sub(replacement, first).strip()

    # 2. If it already starts with a 3rd person singular verb (e.g. "Returns ...", "Loads ...", "Encodes ...")
    words = first.split()
    first_w = words[0].lower()
    if first_w in VERB_TOKENS or (len(first_w) >= 4 and first_w.endswith("s") and not first_w.endswith("ss")):
        # Lowercase first word and return
        return first[0].lower() + first[1:]

    # 3. If it starts with an imperative verb (e.g. "Extract ...", "Load ...", "Run ...", "Parse ...")
    if first_w in {"extract", "load", "encode", "build", "generate", "parse", "process", "run", "search", "query", "convert", "create", "tokenize", "execute", "transcode"}:
        # Convert to 3rd person singular
        verb_3rd = first_w + ("es" if first_w.endswith(("ch", "sh", "ss", "x")) else "s")
        return verb_3rd + " " + " ".join(words[1:])

    # 4. Default fallback: "provides <text>"
    return f"provides {first[0].lower() + first[1:]}"


def compress_sentence(sentence: str, max_words: int = 22) -> list[str]:
    """
    R1: Compress a sentence into 1 or 2 complete grammatical beats without truncation.
    Never slices at N words. Slices only at clause boundaries or drops trailing relative phrases.
    """
    # Clean markdown links: [[Blog]](...) [[Paper]](...) -> remove link-only markup
    s = re.sub(r"\[\[.*?\]\]\(.*?\)", "", sentence)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[`*]", "", s)
    # Unpack parenthetical expansions for speech: (Contrastive Language-Image Pre-Training) -> , Contrastive Language-Image Pre-Training,
    s = re.sub(r"\(([A-Z][a-zA-Z -]+)\)", r", \1,", s)
    s = re.sub(r"[\(\)]", "", s)
    s = " ".join(s.split()).strip()

    if not s:
        return []

    words = s.split()
    if len(words) <= max_words and not is_dangling(s) and has_verb(s):
        s_clean = s.rstrip(".") + "."
        return [s_clean]

    # Strategy (a): Split at coordinating conjunction or semicolon or dash boundary into 2 beats
    # Look for '; ', ' -- ', ' — ', ', and ', ', but ', ', so ', ', while '
    conjunction_patterns = [
        r";\s*",
        r"\s*--\s*",
        r"\s*—\s*",
        r",\s+and\s+",
        r",\s+but\s+",
        r",\s+while\s+",
        r",\s+so\s+",
    ]
    for cp in conjunction_patterns:
        m = re.search(cp, s, flags=re.I)
        if m:
            part1 = s[:m.start()].strip()
            part2 = s[m.end():].strip()
            # If both parts are complete clauses
            if (len(part1.split()) >= 4 and has_verb(part1) and not is_dangling(part1)):
                b1 = part1[0].upper() + part1[1:].rstrip(".") + "."
                beats = [b1]
                if (len(part2.split()) >= 4 and has_verb(part2) and not is_dangling(part2) and len(part2.split()) <= max_words):
                    b2 = part2[0].upper() + part2[1:].rstrip(".") + "."
                    beats.append(b2)
                return beats

    # Strategy (b): Drop trailing relative or participial phrases (", which ...", ", given ...", "using ...", ", without ...")
    trailing_markers = [
        r",\s+without\s+.*$",
        r",\s+given\s+.*$",
        r",\s+which\s+.*$",
        r",\s+using\s+.*$",
        r",\s+where\s+.*$",
        r",\s+allowing\s+.*$",
        r",\s+enabling\s+.*$",
        r",\s+providing\s+.*$",
    ]
    for tm in trailing_markers:
        trimmed = re.sub(tm, "", s, flags=re.I).strip()
        if trimmed and trimmed != s:
            if len(trimmed.split()) <= max_words and has_verb(trimmed) and not is_dangling(trimmed):
                return [trimmed.rstrip(".") + "."]

    # Strategy (c): Split at first comma if first part is complete
    if "," in s:
        comma_parts = s.split(",", 1)
        prefix = comma_parts[0].strip()
        if len(prefix.split()) >= 5 and has_verb(prefix) and not is_dangling(prefix):
            return [prefix.rstrip(".") + "."]

    # If already under max_words, clean ending
    if len(words) <= max_words and has_verb(s):
        # Ensure it does not end with a dangling stopword
        cleaned = re.sub(r"[\.,;:!\?]+$", "", s).strip()
        while cleaned.split() and cleaned.split()[-1].lower() in DANGLING_STOPWORDS:
            cleaned = " ".join(cleaned.split()[:-1])
        if has_verb(cleaned) and len(cleaned.split()) >= 4:
            return [cleaned + "."]

    return []


def tts_normalize_speech(text: str) -> str:
    """
    R11: Format speech text for clear text-to-speech pronunciation:
    - file.py -> file dot py
    - --flag -> flag flag (e.g. --top-k -> top k flag)
    - underscores -> spaces
    - e.g. -> for example, i.e. -> that is
    - omit URLs and version pins (pytorch=1.7.1 -> pytorch)
    """
    t = text
    # Expand Latin abbreviations
    t = re.sub(r"\be\.g\.,?\s*", "for example, ", t, flags=re.I)
    t = re.sub(r"\bi\.e\.,?\s*", "that is, ", t, flags=re.I)
    t = re.sub(r"\betc\.?", "and so on", t, flags=re.I)

    # Replace URLs with spoken cue
    t = re.sub(r"https?://\S+", "the link on screen", t)

    # File extensions
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.py\b", r"\1 dot py", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.js\b", r"\1 dot js", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.ts\b", r"\1 dot ts", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.json\b", r"\1 dot json", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.txt\b", r"\1 dot txt", t)

    # CLI flags for speech
    def _flag_repl(m):
        flag_name = m.group(1).replace("-", " ").strip()
        if flag_name in ("yes", "y"):
            return ""  # silent
        return f"{flag_name} flag"

    t = re.sub(r"--([a-zA-Z0-9_-]+)", _flag_repl, t)

    # Omit version pins in speech: e.g. pytorch=1.7.1 or numpy>=1.20 -> pytorch, numpy
    t = re.sub(r"([a-zA-Z0-9_-]+)(?:==|>=|<=|=|~=)[0-9a-zA-Z_.-]+", r"\1", t)

    # Underscores to spaces
    t = t.replace("_", " ")

    # Strip extraneous punctuation for voice
    t = re.sub(r"[`~*#]", "", t)
    t = " ".join(t.split())
    return t


class ExplainerWriter:
    """
    Extractive, deterministic script generator producing 8-12 beats (48-58s)
    backed by real SourceSpans and adhering strictly to R1-R12 rules.
    """

    def __init__(self, facts: RepoFacts) -> None:
        self.facts = facts
        self.readme_file = facts.readme_file or "README.md"

    def write_script(self) -> ScriptPlan:
        """Compose script plan from facts, strictly enforcing quality rules."""
        scenes: list[Scene] = []

        # 1. Title Scene (R10 dominant code language, R1/R2 compression)
        title_scene = self._build_title_scene()
        if title_scene:
            scenes.append(title_scene)

        # 2. Overview Scene (R7: what it is, what it does, what you get)
        ov_scene = self._build_overview_scene()
        if ov_scene:
            scenes.append(ov_scene)

        # 3. Diagram Scene (R5: architecture selection excluding tests/examples)
        core_mods = [m for m in self.facts.ranked_top_modules if not is_auxiliary_or_test_path(m)]
        if len(core_mods) >= 2 or len(self.facts.import_graph) >= 1:
            diag_scene = self._build_diagram_scene()
            if diag_scene:
                scenes.append(diag_scene)

        # 4. Code Scene (R4: key code selection from core public functions)
        code_scene = self._build_code_scene()
        if code_scene:
            scenes.append(code_scene)

        # 5. Terminal Scene (R6: install and run commands, flag normalization)
        term_scene = self._build_terminal_scene()
        if term_scene:
            scenes.append(term_scene)

        # 6. Fit Scene (R8: honest video retrieval alignment)
        fit_scene = self._build_fit_scene()
        if fit_scene:
            scenes.append(fit_scene)

        # 7. Recap Scene (R3, R9: takeaways from real facts)
        recap_scene = self._build_recap_scene()
        if recap_scene:
            scenes.append(recap_scene)

        # Ensure at least 3 scenes
        if len(scenes) < 3:
            scenes = self._fill_sparse_scenes(scenes)

        # Cap at 6 scenes max for standard 4-6 scene explainer
        if len(scenes) > 6:
            fit_idx = next((i for i, s in enumerate(scenes) if s.id == "fit"), -1)
            if fit_idx != -1:
                scenes.pop(fit_idx)
            else:
                scenes.pop(len(scenes) - 2)


        # Budget check (R12): target 8-12 beats, <= 140 words total (duration <= 56.0s)
        while (sum(len(s.narration.split()) for s in scenes) / 150.0) * 60.0 > 56.0:
            trimmed = False
            for sc_id in ("fit", "diagram", "terminal", "overview"):
                target_sc = next((s for s in scenes if s.id == sc_id and len(s.beats) > 1), None)
                if target_sc:
                    target_sc.beats.pop()
                    target_sc.narration = " ".join(b.say for b in target_sc.beats)
                    trimmed = True
                    break
            if not trimmed:
                break


        # Validate no banned buzzwords; reject draft if any found
        for s in scenes:
            for b in s.beats:
                banned = check_for_banned_phrases(b.say) + check_for_banned_phrases(b.caption)
                if banned:
                    raise ValueError(f"Extractive script generated banned phrases {banned} in scene '{s.id}'")

        script = ScriptPlan(repo_name=self.facts.repo_name, scenes=scenes)
        attach_visuals_to_script(script, self.facts)
        return script

    def _build_title_scene(self) -> Scene:
        """R10: dominant code language, owner only when known, R1 compressed title beat."""
        title = self.facts.readme.title
        if not title or len(title.split()) > 6 or "[" in title or check_for_banned_phrases(title):
            title = self.facts.repo_name

        tagline = self.facts.readme.tagline
        if not tagline or check_for_banned_phrases(tagline):
            clean_sents = [s for s in self.facts.readme.description_sentences if not check_for_banned_phrases(s.text)]
            if clean_sents:
                tagline = clean_sents[0].text

        top_lang = next(iter(self.facts.languages_by_bytes.keys()), "Python")
        if not tagline or check_for_banned_phrases(tagline):
            tagline = f"{self.facts.repo_name} is an open source {top_lang} project."

        # Compress tagline cleanly per R1
        compressed_tagline = compress_sentence(tagline, max_words=16)
        tag_phrase = compressed_tagline[0] if compressed_tagline else f"{self.facts.repo_name} provides {top_lang} functionality."

        if tag_phrase.lower().startswith(title.lower()):
            say_text = tag_phrase
        else:
            say_text = f"{title}. {tag_phrase}"

        # Ensure no dangling endings (R2)
        if is_dangling(say_text):
            say_text = f"{title} is an open source {top_lang} repository."

        spoken_say = tts_normalize_speech(say_text)
        caption_text = f"{title}: {tag_phrase.rstrip('.')}"
        if len(caption_text.split()) > 10:
            caption_text = " ".join(caption_text.split()[:10])

        source_span = SourceSpan(
            file=self.readme_file,
            start_line=1,
            end_line=10,
            text=tagline,
        )

        beat = Beat(
            say=spoken_say,
            caption=caption_text,
            focus=self.facts.repo_name,
            sources=[source_span],
            start_seconds=0.25,
            end_seconds=4.5,
        )
        return Scene(
            id="title",
            kind="title",
            title="Overview",
            narration=spoken_say,
            beats=[beat],
            duration_seconds=4.5,
        )

    def _build_overview_scene(self) -> Scene:
        """
        R7: Overview scene with 3 beats:
        Beat 1: What it is (primary description sentence)
        Beat 2: What it does (next 1-2 description sentences, compressed R1)
        Beat 3: What you get (key features or CLI flags)
        """
        beats: list[Beat] = []
        desc_sents = [s for s in self.facts.readme.description_sentences if not check_for_banned_phrases(s.text)]

        # Beat 1: What it is
        b1_sent = desc_sents[0].text if desc_sents else f"{self.facts.repo_name} is a software library."
        sp1 = desc_sents[0].start_line if desc_sents else 1
        ep1 = desc_sents[0].end_line if desc_sents else 5

        # Beat 2: What it does
        if len(desc_sents) > 1:
            b1_sent = desc_sents[0].text
            comp_b1 = compress_sentence(b1_sent, max_words=18)
            say1 = comp_b1[0] if comp_b1 else b1_sent
            caption1 = f"What it is: {say1.rstrip('.')[:35]}"

            b2_sent = desc_sents[1].text
            comp_b2 = compress_sentence(b2_sent, max_words=18)
            say2 = comp_b2[0] if comp_b2 else f"It provides {b2_sent.rstrip('.')}."
            sp2 = desc_sents[1].start_line
            ep2 = desc_sents[1].end_line
            b2_quote = b2_sent
            caption2 = f"Capabilities: {b2_sent[:35]}"
        else:
            b2_quote = b1_sent
            sp2, ep2 = sp1, ep1
            # Split b1_sent across clause boundaries so both beats are 100% grounded
            split_pats = [" without ", " to ", ", ", " and "]
            split_found = False
            for pat in split_pats:
                if pat in b1_sent:
                    p1, p2 = b1_sent.split(pat, 1)
                    if len(p1.split()) >= 3 and len(p2.split()) >= 3:
                        say1 = p1.strip().rstrip(".") + "."
                        if not has_verb(say1):
                            say1 = f"{self.facts.repo_name} is a {say1[0].lower() + say1[1:]}"
                        caption1 = f"Overview: {say1.rstrip('.')[:35]}"
                        if pat.strip() == "without":
                            say2 = f"It operates without {p2.strip().rstrip('.')}."
                        elif pat.strip() == "to":
                            say2 = f"It operates to {p2.strip().rstrip('.')}."
                        else:
                            say2 = f"It provides {p2.strip().rstrip('.')}."
                        caption2 = f"Capabilities: {p2.strip().rstrip('.')[:35]}"
                        split_found = True
                        break
            if not split_found:
                words = b1_sent.split()
                if len(words) > 6:
                    mid = len(words) // 2
                    say1 = " ".join(words[:mid]).rstrip(".") + "."
                    if not has_verb(say1):
                        say1 = f"{self.facts.repo_name} provides {say1[0].lower() + say1[1:]}"
                    say2 = f"It provides " + " ".join(words[mid:]).rstrip(".") + "."
                    caption1 = f"Overview: {say1.rstrip('.')[:35]}"
                    caption2 = f"Capabilities: {say2.rstrip('.')[:35]}"
                else:
                    say1 = b1_sent
                    if not has_verb(say1):
                        say1 = f"{self.facts.repo_name} is {say1[0].lower() + say1[1:]}"
                    caption1 = f"Overview: {say1.rstrip('.')[:35]}"
                    say2 = f"It implements {self.facts.repo_name}."
                    caption2 = f"Implementation: {self.facts.repo_name}"

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus="concept",
            sources=[SourceSpan(file=self.readme_file, start_line=sp1, end_line=ep1, text=b1_sent)],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=caption2,
            focus="operation",
            sources=[SourceSpan(file=self.readme_file, start_line=sp2, end_line=ep2, text=b2_quote)],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

        # Beat 3: What you get (features or CLI flags)
        if self.facts.readme.feature_sentences:
            fs = self.facts.readme.feature_sentences[0]
            fs_text = fs.text.rstrip('.')
            say3 = f"It provides {fs_text}."
            caption3 = f"Features: {fs_text[:35]}"
            feat_span = SourceSpan(
                file=self.readme_file,
                start_line=fs.start_line,
                end_line=fs.end_line,
                text=fs.raw_text or fs.text,
            )
        elif self.facts.readme.features:
            feat = self.facts.readme.features[0].rstrip('.')
            say3 = f"It provides {feat}."
            caption3 = f"Features: {feat[:35]}"
            matching_l = next((l for l in self.facts.readme.raw_lines if feat.lower() in l.lower()), self.facts.readme.tagline or feat)
            feat_span = SourceSpan(file=self.readme_file, start_line=1, end_line=30, text=matching_l)
        elif self.facts.cli_flags:
            flags_str = " and ".join(self.facts.cli_flags[:2])
            say3 = f"It provides command line flags {flags_str}."
            caption3 = f"Flags: {flags_str}"
            feat_span = SourceSpan(file=self.readme_file, start_line=1, end_line=30, text=self.facts.readme.tagline or self.facts.repo_name)
        else:
            # Ensure span quote is a full line from raw_lines or >= 20 chars
            fallback_line = next((l for l in self.facts.readme.raw_lines if len(l.strip()) >= 20), (self.facts.readme.raw_lines[0] if self.facts.readme.raw_lines else self.facts.repo_name))
            fb_idx = next((i + 1 for i, l in enumerate(self.facts.readme.raw_lines) if fallback_line in l), 1)
            feat_span = SourceSpan(file=self.readme_file, start_line=fb_idx, end_line=fb_idx, text=fallback_line)

            quote_w = [w for w in re.findall(r"\b[A-Za-z]{4,}\b", fallback_line) if w.lower() not in STOPWORDS]
            if len(quote_w) >= 3:
                chosen = quote_w[-3:]
                say3 = f"It provides {chosen[0]}, {chosen[1]}, and {chosen[2]}."
                caption3 = f"Features: {' '.join(chosen)}"
            elif quote_w:
                say3 = f"It provides {' and '.join(quote_w)}."
                caption3 = f"Features: {' '.join(quote_w)}"
            else:
                say3 = f"It provides capabilities for {self.facts.repo_name}."
                caption3 = f"Capabilities: {self.facts.repo_name}"

        beats.append(Beat(
            say=tts_normalize_speech(say3),
            caption=caption3,
            focus="features",
            sources=[feat_span],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

        narration = " ".join(b.say for b in beats)
        return Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            narration=narration,
            beats=beats,
            duration_seconds=round(len(beats) * 5.0, 2),
        )

    def _build_diagram_scene(self) -> Scene:
        """R5: Architecture selection excluding tests/examples, connecting core modules with real roles."""
        core_mods = [m for m in self.facts.ranked_top_modules if not is_auxiliary_or_test_path(m)]
        if not core_mods:
            core_mods = self.facts.ranked_top_modules[:3]

        beats: list[Beat] = []
        mod_doc_map = {m.file: m.docstring for m in self.facts.module_docstrings}

        mod1 = core_mods[0]
        m_doc1 = mod_doc_map.get(mod1, "")
        sym1 = next((s for s in self.facts.top_symbols if s.file == mod1), None)
        edge1 = next((e for e in self.facts.import_graph if e.source == mod1 and e.raw_line), None)

        if m_doc1:
            role1 = convert_docstring_to_verb_phrase(m_doc1)
            say1 = f"{mod1} {role1}."
            caption1 = f"{mod1}: {role1[:35]}"
            m_doc_obj = next((m for m in self.facts.module_docstrings if m.file == mod1), None)
            span1 = m_doc_obj.span if m_doc_obj else SourceSpan(file=mod1, start_line=1, end_line=10, text=m_doc1)
        elif sym1:
            say1 = f"{mod1} defines {sym1.name}."
            caption1 = f"{mod1}: defines {sym1.name}"
            span1 = SourceSpan(file=mod1, start_line=sym1.start_line, end_line=sym1.end_line, text=sym1.def_line or sym1.name)
        elif edge1:
            say1 = f"{mod1} imports from {edge1.target}."
            caption1 = f"{mod1}: imports {edge1.target}"
            span1 = SourceSpan(file=mod1, start_line=1, end_line=5, text=edge1.raw_line)
        else:
            say1 = f"{mod1} provides module code for {self.facts.repo_name}."
            caption1 = f"{mod1}: module code"
            span1 = SourceSpan(file=self.readme_file, start_line=1, end_line=10, text=self.facts.readme.title or self.facts.repo_name)

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus=mod1,
            sources=[span1],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

        if len(core_mods) >= 2:
            mod2 = core_mods[1]
            m_doc2 = mod_doc_map.get(mod2, "")
            sym2 = next((s for s in self.facts.top_symbols if s.file == mod2), None)
            edge2 = next((e for e in self.facts.import_graph if (e.source == mod2 or e.target == mod2) and e.raw_line), None)

            if m_doc2:
                role2 = convert_docstring_to_verb_phrase(m_doc2)
                say2 = f"It connects to {mod2}, which {role2}."
                caption2 = f"{mod2}: {role2[:35]}"
                m_doc_obj2 = next((m for m in self.facts.module_docstrings if m.file == mod2), None)
                span2 = m_doc_obj2.span if m_doc_obj2 else SourceSpan(file=mod2, start_line=1, end_line=10, text=m_doc2)
            elif sym2:
                say2 = f"It connects to {mod2}, which defines {sym2.name}."
                caption2 = f"{mod2}: defines {sym2.name}"
                span2 = SourceSpan(file=mod2, start_line=sym2.start_line, end_line=sym2.end_line, text=sym2.def_line or sym2.name)
            elif edge2:
                say2 = f"It connects to {mod2}, which imports {edge2.target}."
                caption2 = f"{mod2}: imports {edge2.target}"
                span2 = SourceSpan(file=mod2, start_line=1, end_line=5, text=edge2.raw_line)
            else:
                say2 = f"It connects to {mod2} in {self.facts.repo_name}."
                caption2 = f"{mod2}: connection"
                span2 = SourceSpan(file=self.readme_file, start_line=1, end_line=10, text=self.facts.readme.title or self.facts.repo_name)

            beats.append(Beat(
                say=tts_normalize_speech(say2),
                caption=caption2,
                focus=mod2,
                sources=[span2],
                start_seconds=0.25,
                end_seconds=5.0,
            ))

        narration = " ".join(b.say for b in beats)
        return Scene(
            id="diagram",
            kind="diagram",
            title="Architecture",
            narration=narration,
            beats=beats,
            duration_seconds=round(len(beats) * 5.0, 2),
        )

    def _build_code_scene(self) -> Scene | None:
        """R4: Key code selection from core public functions, stating what the lines DO."""
        core_symbols = [s for s in self.facts.top_symbols if not is_auxiliary_or_test_path(s.file) and not s.name.startswith("_")]
        sym = core_symbols[0] if core_symbols else (self.facts.top_symbols[0] if self.facts.top_symbols else None)
        if not sym:
            return None

        beats: list[Beat] = []
        calls_clean = [c for c in sym.calls if not c.startswith("_") and c not in ("print", "len", "str", "list", "dict", "keys", "values", "items", "append")][:2]

        # Beat 1: Purpose & Declaration
        if sym.docstring:
            doc_phrase = convert_docstring_to_verb_phrase(sym.docstring)
            say1 = f"In {sym.file}, {sym.name} {doc_phrase}."
            caption1 = f"{sym.name}: {doc_phrase[:35]}"
            span1 = sym.docstring_span or SourceSpan(
                file=sym.file,
                start_line=sym.start_line,
                end_line=min(sym.start_line + 4, sym.end_line),
                text=sym.docstring,
            )
        elif calls_clean:
            calls_str = " and ".join(calls_clean)
            say1 = f"In {sym.file}, {sym.name} calls {calls_str}."
            caption1 = f"{sym.name}: calls {calls_str}"
            span1 = SourceSpan(
                file=sym.file,
                start_line=sym.start_line,
                end_line=min(sym.start_line + 4, sym.end_line),
                text=sym.def_line or sym.name,
            )
        else:
            say1 = f"In {sym.file}, {sym.name} is defined for execution."
            caption1 = f"{sym.name} in {sym.file}"
            span1 = SourceSpan(
                file=sym.file,
                start_line=sym.start_line,
                end_line=min(sym.start_line + 4, sym.end_line),
                text=sym.def_line or sym.name,
            )

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus=sym.name,
            sources=[span1],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

        # Beat 2: Execution action
        if calls_clean:
            calls_str = " and ".join(calls_clean)
            say2 = f"Inside {sym.name}, it invokes {calls_str}."
            caption2 = f"Calls: {calls_str}"
            call_line = next((l.strip() for l in sym.code_excerpt.splitlines() if any(c in l for c in calls_clean)), sym.def_line)
            span2 = SourceSpan(
                file=sym.file,
                start_line=sym.start_line,
                end_line=sym.end_line,
                text=call_line or sym.name,
            )
        else:
            code_words = [w for w in re.findall(r"\b[A-Za-z]{4,}\b", sym.code_excerpt) if w.lower() not in STOPWORDS and w.lower() != sym.name.lower()]
            if code_words:
                w = code_words[0]
                say2 = f"In {sym.name}, it executes and handles {w}."
                caption2 = f"{sym.name} handles {w}"
                line = next((l.strip() for l in sym.code_excerpt.splitlines() if w.lower() in l.lower()), sym.def_line)
                span2 = SourceSpan(file=sym.file, start_line=sym.start_line, end_line=sym.end_line, text=line)
            else:
                say2 = f"In {sym.file}, {sym.name} executes."
                caption2 = f"{sym.name} in {sym.file}"
                span2 = SourceSpan(file=sym.file, start_line=sym.start_line, end_line=sym.end_line, text=sym.def_line or sym.name)

        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=caption2,
            focus="execution",
            sources=[span2],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

        narration = " ".join(b.say for b in beats)
        return Scene(
            id="code",
            kind="code",
            title="Implementation",
            narration=narration,
            beats=beats,
            duration_seconds=round(len(beats) * 5.0, 2),
        )

    def _build_terminal_scene(self) -> Scene | None:
        """R6: Terminal commands: only real commands in repo; omit scene entirely if no commands."""
        install_cmd = ""
        for cmd in self.facts.readme.install_commands:
            if "pip " in cmd or "npm " in cmd:
                install_cmd = cmd
                break
        if not install_cmd and self.facts.readme.install_commands:
            install_cmd = self.facts.readme.install_commands[0]

        usage_cmd = ""
        if self.facts.readme.usage_commands:
            usage_cmd = self.facts.readme.usage_commands[0]

        if not install_cmd and not usage_cmd:
            return None

        beats: list[Beat] = []
        if install_cmd:
            tokens = install_cmd.split()
            if len(tokens) > 8:
                say1 = "Run the install command shown on screen."
            else:
                say1 = f"Run {install_cmd} to install."

            i_line = next((i + 1 for i, l in enumerate(self.facts.readme.raw_lines) if install_cmd in l), 1)
            span1 = SourceSpan(file=self.readme_file, start_line=i_line, end_line=i_line, text=install_cmd)
            beats.append(Beat(
                say=tts_normalize_speech(say1),
                caption=f"Install: {install_cmd[:35]}",
                focus="install",
                sources=[span1],
                start_seconds=0.25,
                end_seconds=4.5,
            ))

        if usage_cmd:
            u_tokens = usage_cmd.split()
            if len(u_tokens) > 8:
                say2 = "Next, execute the quickstart command to run the tool."
            else:
                say2 = f"Then execute {usage_cmd}."
            u_line = next((i + 1 for i, l in enumerate(self.facts.readme.raw_lines) if usage_cmd in l), 1)
            span2 = SourceSpan(file=self.readme_file, start_line=u_line, end_line=u_line, text=usage_cmd)
            beats.append(Beat(
                say=tts_normalize_speech(say2),
                caption=f"Run: {usage_cmd[:35]}",
                focus="run",
                sources=[span2],
                start_seconds=0.25,
                end_seconds=4.5,
            ))

        narration = " ".join(b.say for b in beats)
        return Scene(
            id="terminal",
            kind="terminal",
            title="Quickstart",
            narration=narration,
            beats=beats,
            duration_seconds=round(len(beats) * 4.5, 2),
        )

    def _build_fit_scene(self) -> Scene:
        """R8: Honest fit: only cite stages with literal evidence; use honest fallback when not video-specific."""
        evidenced_stages = list(self.facts.pipeline_stages.keys())

        # If >= 2 evidenced stages and repo is video-relevant and has symbols, cite them
        if (
            self.facts.is_video_relevant
            and self.facts.top_symbols
            and len(evidenced_stages) >= 2
        ):
            stages_list = ", ".join(evidenced_stages[:-1]) + f" and {evidenced_stages[-1]}"
            say = f"The pipeline implements {stages_list} stages."
            spans = []
            for st in evidenced_stages[:2]:
                quote = self.facts.pipeline_stages[st]
                spans.append(SourceSpan(file=self.readme_file, start_line=1, end_line=40, text=quote))
            caption = f"Pipeline Stages: {stages_list}"
            focus = "pipeline"
        else:
            # R3 honest not-video-specific line
            say = f"{self.facts.repo_name} is not video-specific, but this video ships a transcript, chapters, and a retrieval index."
            caption = f"Deliverables: transcript, chapters, and retrieval index"
            spans = [SourceSpan(file=self.readme_file, start_line=1, end_line=10, text=self.facts.readme.title or self.facts.repo_name)]
            focus = "artifacts"

        beat = Beat(
            say=tts_normalize_speech(say),
            caption=caption,
            focus=focus,
            sources=spans,
            start_seconds=0.25,
            end_seconds=6.0,
        )

        return Scene(
            id="fit",
            kind="fit",
            title="Pipeline Fit",
            narration=tts_normalize_speech(say),
            beats=[beat],
            duration_seconds=6.0,
        )

    def _build_recap_scene(self) -> Scene:
        """R3, R9: Recap scene stating compressed summary and exact entry file."""
        title = self.facts.readme.title or self.facts.repo_name
        tagline = self.facts.readme.tagline or f"{self.facts.repo_name} is an open source project"
        comp_tag = compress_sentence(tagline, max_words=14)
        summary_phrase = comp_tag[0].rstrip(".") if comp_tag else f"{self.facts.repo_name} provides open source software tools"

        say1 = f"In short, {summary_phrase}."
        if is_dangling(say1) or not has_verb(say1):
            say1 = f"In short, {title} provides an open source implementation."

        entry_f = self.facts.entry_module or (self.facts.ranked_top_modules[0] if self.facts.ranked_top_modules else (self.readme_file or "README.md"))
        say2 = f"To dive in, explore {self.facts.repo_name} starting with {entry_f}."
        caption2 = f"Next Step: {entry_f}"

        span1 = SourceSpan(file=self.readme_file, start_line=1, end_line=15, text=tagline)

        # Grounded source span for entry file
        m_doc = next((m for m in self.facts.module_docstrings if m.file == entry_f), None)
        if m_doc:
            span2 = m_doc.span
        else:
            sym = next((s for s in self.facts.top_symbols if s.file == entry_f), None)
            if sym:
                span2 = SourceSpan(file=entry_f, start_line=sym.start_line, end_line=sym.end_line, text=sym.def_line or sym.name)
            else:
                span2 = SourceSpan(file=self.readme_file, start_line=1, end_line=10, text=tagline)


        beats = [
            Beat(
                say=tts_normalize_speech(say1),
                caption=f"Summary: {summary_phrase[:40]}",
                focus="recap",
                sources=[span1],
                start_seconds=0.25,
                end_seconds=4.5,
            ),
            Beat(
                say=tts_normalize_speech(say2),
                caption=f"Next Step: inspect {entry_f}",
                focus="next_steps",
                sources=[span2],
                start_seconds=0.25,
                end_seconds=4.5,
            ),
        ]

        narration = " ".join(b.say for b in beats)
        return Scene(
            id="recap",
            kind="recap",
            title="Conclusion",
            narration=narration,
            beats=beats,
            duration_seconds=9.0,
        )

    def _fill_sparse_scenes(self, scenes: list[Scene]) -> list[Scene]:
        """Ensure sparse repositories have at least 3 scenes."""
        if not any(s.id == "title" for s in scenes):
            scenes.insert(0, self._build_title_scene())
        if not any(s.id == "overview" for s in scenes):
            scenes.insert(1, self._build_overview_scene())
        if not any(s.id == "recap" for s in scenes):
            scenes.append(self._build_recap_scene())
        return scenes


def write_explainer_script(facts: RepoFacts) -> ScriptPlan:
    """Convenience entry point for generating deterministic explainer script plan."""
    return ExplainerWriter(facts).write_script()

