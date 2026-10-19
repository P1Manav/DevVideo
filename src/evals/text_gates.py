"""Evaluation gates submodule."""
from __future__ import annotations
import html
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from PIL import Image

from ..schema import BANNED_PHRASES, ScriptPlan, is_disallowed_span
from .report import EvalGate

logger = logging.getLogger(__name__)

from .groundedness import STOPWORDS, _extract_content_tokens, check_groundedness

DANGLING_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "to", "for", "with", "by", "from",
    "and", "or", "but", "that", "which", "is", "are", "was", "be", "as",
    "at", "than", "then", "if", "most", "more", "e.g.", "i.e.", "etc", "etc.",
    "its", "into", "their", "our", "your", "natural", "matching", "multimodal",
    "understanding", "instructed",
}

JUNK_TOKENS = {
    "def", "class", "import", "return", "self", "https", "http", "www", "com",
    "png", "svg", "blog", "badge", "img"
}

def check_narration_quality_gate(
    script: ScriptPlan,
    repo_files: dict[str, str],
) -> EvalGate:
    """
    Gate: narration_quality
    - No banned phrases.
    - No beat whose content tokens include >= 2 junk tokens.
    - No beat whose content tokens are all < 4 chars.
    - No two scenes share an identical sentence skeleton.
    - Recap "start with" file is a code/entry file when code exists.
    """
    issues: list[str] = []

    # 1. Banned phrases check
    for scene in script.scenes:
        s_lower = scene.narration.lower()
        for bp in BANNED_PHRASES:
            if bp in s_lower:
                issues.append(f"{scene.id}: contains banned phrase / banned buzzwords '{bp}'")
        for b_idx, b in enumerate(scene.beats):
            b_lower = f"{b.say} {b.caption}".lower()
            for bp in BANNED_PHRASES:
                if bp in b_lower:
                    issues.append(f"{scene.id}[b{b_idx}]: contains banned phrase / banned buzzwords '{bp}'")

    # 2. Junk tokens & short content tokens
    for scene in script.scenes:
        for b_idx, b in enumerate(scene.beats):
            tokens = _extract_content_tokens(b.say)
            junk_matches = tokens & JUNK_TOKENS
            if len(junk_matches) >= 2:
                issues.append(f"{scene.id}[b{b_idx}]: contains {len(junk_matches)} junk tokens ({junk_matches})")
            if tokens and all(len(t) < 4 for t in tokens):
                issues.append(f"{scene.id}[b{b_idx}]: all content tokens are < 4 chars")

    # 3. No two scenes share an identical sentence skeleton
    skeletons: dict[str, str] = {}
    for scene in script.scenes:
        if scene.kind == "text":
            continue
        words = re.findall(r"\b[a-zA-Z]+\b", scene.narration.lower())
        if len(words) >= 5:
            skeleton = " ".join([w if w in STOPWORDS else "_" for w in words])
            if skeleton in skeletons:
                issues.append(f"Scene '{scene.id}' shares sentence skeleton with '{skeletons[skeleton]}'")
            else:
                skeletons[skeleton] = scene.id

    # 4. Recap 'start with' file is code/entry file when code exists
    code_exts = {".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp", ".rb"}
    has_code = any(any(f.endswith(ext) for ext in code_exts) for f in repo_files.keys())
    if has_code:
        recap = next((s for s in script.scenes if s.kind == "recap"), None)
        if recap:
            r_lower = recap.narration.lower()
            for non_code in ["license", "readme", "readme.md", "contributing", "notice"]:
                if f"start with {non_code}" in r_lower:
                    issues.append(f"Recap suggests non-code file '{non_code}' when code exists")
            code_files = [f for f in repo_files if any(f.endswith(ext) for ext in code_exts)]
            code_names = {Path(f).name.lower() for f in code_files} | {Path(f).stem.lower() for f in code_files} | {f.lower() for f in code_files}
            code_names |= {cn.lstrip("_") for cn in list(code_names)}
            code_names |= {cn.replace("_", " ") for cn in list(code_names)}
            has_mention = any(
                cn in r_lower or cn.replace(".", " dot ") in r_lower or f"open {cn}" in r_lower or f"start with {cn}" in r_lower
                for cn in code_names
            )
            if not has_mention:
                issues.append("Recap does not mention a code/entry file to start with")

    passed = (len(issues) == 0)
    return EvalGate(
        name="narration_quality",
        passed=passed,
        value="valid" if passed else f"{len(issues)} issues",
        threshold="0 issues",
        details="Narration adheres to honest grammar, tone, and quality standards"
        if passed else f"Narration quality issues: {issues[:3]}",
    )


def check_specificity_gate(
    script: ScriptPlan,
    repo_files: dict[str, str],
    facts: Any | None = None,
) -> EvalGate:
    """
    Gate: specificity
    Every beat names >= 1 repo-specific item (identifier, flag, filename,
    dependency, or a content word from the README description).
    """
    specific_items: set[str] = set()
    for f in repo_files:
        specific_items.add(Path(f).name.lower())
        specific_items.add(Path(f).stem.lower())
        specific_items.add(f.lower())

    specific_items.add(script.repo_name.lower())
    for rn_tok in script.repo_name.lower().replace("_", " ").replace("-", " ").split():
        if len(rn_tok) >= 3:
            specific_items.add(rn_tok)

    # Output artifact terms
    specific_items.update({"transcript", "vtt", "chapters", "json", "index", "jsonl", "mp4"})

    # All identifiers from all code files in the repo
    for fpath, code in repo_files.items():
        for sym in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code):
            specific_items.add(sym.lower())

    if facts:
        readme = getattr(facts, "readme", None)
        if readme:
            desc_sents = getattr(readme, "description_sentences", [])
            for ds in desc_sents:
                t = ds if isinstance(ds, str) else getattr(ds, "text", "")
                for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", t):
                    if w.lower() not in STOPWORDS:
                        specific_items.add(w.lower())
            for feat in getattr(readme, "features", []):
                for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", feat):
                    if w.lower() not in STOPWORDS:
                        specific_items.add(w.lower())
            for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", getattr(readme, "tagline", "") + " " + getattr(readme, "title", "")):
                if w.lower() not in STOPWORDS:
                    specific_items.add(w.lower())
        for sym in getattr(facts, "top_symbols", []):
            specific_items.add(sym.name.lower())
        for fl in getattr(facts, "cli_flag_details", []) or getattr(facts, "cli_flags", []):
            flag_name = getattr(fl, "flag", "").lstrip("-").lower()
            if flag_name:
                specific_items.add(flag_name)
        for dep in getattr(facts, "dependencies", {}):
            specific_items.add(dep.lower())
        for st in getattr(facts, "pipeline_stages", {}):
            specific_items.add(st.lower())

    # For repositories with no or few code files, all words from documentation files count as specific items
    has_code = any(f.endswith((".py", ".js", ".ts", ".go", ".rs", ".cpp", ".c", ".java")) for f in repo_files)
    if not has_code:
        for fpath, content in repo_files.items():
            for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", content):
                if w.lower() not in STOPWORDS:
                    specific_items.add(w.lower())

    non_specific_beats: list[str] = []
    total_beats = 0

    for scene in script.scenes:
        beats_to_check = scene.beats if scene.beats else [
            Beat(say=scene.narration, caption=scene.id, focus=None, sources=[])
        ]
        for b_idx, b in enumerate(beats_to_check):
            total_beats += 1
            beat_text = f"{b.say} {b.caption}".lower()
            has_specific = False
            for item in specific_items:
                if len(item) >= 3 and re.search(rf"\b{re.escape(item)}\b", beat_text):
                    has_specific = True
                    break
            if not has_specific:
                non_specific_beats.append(f"{scene.id}[b{b_idx}]")

    passed = (len(non_specific_beats) == 0)
    return EvalGate(
        name="specificity",
        passed=passed,
        value=f"{total_beats - len(non_specific_beats)}/{total_beats} specific",
        threshold="100%",
        details="All beats name >= 1 repo-specific item"
        if passed else f"Non-specific beats: {non_specific_beats}",
    )


def check_onscreen_text_integrity_gate(
    script: ScriptPlan,
    facts: Any | None = None,
    repo_files: dict[str, str] | None = None,
) -> EvalGate:
    """
    Gate: onscreen_text_integrity
    Verifies that:
    1. No on-screen text (captions, bullets, takeaways, titles) ends mid-word or with a dangling stopword.
    2. Every bullet and caption is a substring/normalization of a source span or identifier from facts.
    """
    violations: list[str] = []

    facts_pool: set[str] = set()
    facts_pool.add(script.repo_name.lower())
    for w in script.repo_name.replace("-", " ").replace("_", " ").split():
        facts_pool.add(w.lower())

    if repo_files:
        for rf_content in repo_files.values():
            facts_pool.update(_extract_content_tokens(rf_content))

    if facts:
        if hasattr(facts, "repo_name"):
            facts_pool.add(facts.repo_name.lower())
        for sym in getattr(facts, "top_symbols", []):
            name = getattr(sym, "name", str(sym))
            facts_pool.add(name.lower())
            for part in re.split(r"[_\-.]", name):
                if part:
                    facts_pool.add(part.lower())
            for c in getattr(sym, "calls", []):
                facts_pool.add(c.lower())
                for part in re.split(r"[_\-.]", c):
                    if part:
                        facts_pool.add(part.lower())
            if getattr(sym, "docstring", ""):
                facts_pool.update(_extract_content_tokens(sym.docstring))
            f = getattr(sym, "file", "")
            if f:
                facts_pool.add(f.lower())
                facts_pool.add(Path(f).stem.lower())
        for md in getattr(facts, "module_docstrings", []):
            facts_pool.update(_extract_content_tokens(getattr(md, "docstring", "")))
        for mod in getattr(facts, "ranked_top_modules", []):
            facts_pool.add(mod.lower())
            facts_pool.add(Path(mod).stem.lower())
            for part in re.split(r"[_\-./]", mod):
                if part:
                    facts_pool.add(part.lower())
        for fl in getattr(facts, "cli_flags", []):
            flag_str = getattr(fl, "flag", str(fl))
            facts_pool.add(flag_str.lower().lstrip("-"))
            for part in re.split(r"[_\-.]", flag_str):
                clean_p = part.lstrip("-").lower()
                if clean_p:
                    facts_pool.add(clean_p)
        for dep in getattr(facts, "dependencies", []):
            facts_pool.add(str(dep).lower())
        for st in getattr(facts, "pipeline_stages", {}):
            facts_pool.add(str(st).lower())
            facts_pool.update(_extract_content_tokens(str(facts.pipeline_stages[st])))
        if hasattr(facts, "readme"):
            for feat in getattr(facts.readme, "features", []):
                facts_pool.update(_extract_content_tokens(feat))
            if getattr(facts.readme, "title", None):
                facts_pool.update(_extract_content_tokens(facts.readme.title))
            if getattr(facts.readme, "tagline", None):
                facts_pool.update(_extract_content_tokens(facts.readme.tagline))
            for s in getattr(facts.readme, "description_sentences", []):
                s_txt = getattr(s, "text", str(s))
                facts_pool.update(_extract_content_tokens(s_txt))
        for p in getattr(facts, "tree", []):
            p_clean = p.rstrip("/")
            facts_pool.add(p_clean.lower())
            facts_pool.add(Path(p_clean).stem.lower())
            for part in p_clean.split("/"):
                facts_pool.add(part.lower())
                facts_pool.add(Path(part).stem.lower())
        if getattr(facts, "readme_file", None):
            rf = getattr(facts, "readme_file")
            facts_pool.add(rf.lower())
            facts_pool.add(Path(rf).stem.lower())

    artifact_tokens = {
        "transcript", "chapters", "retrieval", "index", "artifacts", "deliverables",
        "pipeline", "stages", "next", "step", "summary", "features", "overview",
        "capabilities", "core", "codebase", "module", "code", "run", "options",
        "explore", "implements", "entry", "point", "defines", "primary", "operations",
        "inspect", "check", "start", "guide", "documentation", "focuses", "operates",
        "connects", "imports", "executes", "handles", "call", "calls", "install",
        "open", "source", "software", "project", "tools", "utility", "library", "package", "tool",
        "supported", "operation",
    }

    for scene in script.scenes:
        if scene.title:
            t_clean = re.sub(r"[\.,;:!\?]+$", "", scene.title).strip()
            t_words = t_clean.split()
            if t_words and t_words[-1].lower() in DANGLING_STOPWORDS:
                violations.append(f"{scene.id}: title ends with dangling stopword '{t_words[-1]}'")

        scene_span_texts = []
        if scene.evidence:
            scene_span_texts.append(scene.evidence.quote or scene.evidence.text or "")
        for b in scene.beats:
            for s in b.sources:
                scene_span_texts.append(s.text or "")
        norm_spans = " ".join(" ".join(t.split()).lower() for t in scene_span_texts if t)

        for b_idx, beat in enumerate(scene.beats):
            cap = beat.caption.strip()
            if not cap:
                continue

            # Phase 3: Unbalanced quotes and brackets
            if cap.count('"') % 2 != 0:
                violations.append(f"{scene.id}[b{b_idx}]: caption has unbalanced quotes in '{cap}'")
            if cap.count("(") != cap.count(")"):
                violations.append(f"{scene.id}[b{b_idx}]: caption has unbalanced parentheses in '{cap}'")
            if cap.count("[") != cap.count("]"):
                violations.append(f"{scene.id}[b{b_idx}]: caption has unbalanced brackets in '{cap}'")

            cap_clean = re.sub(r"[\.,;:!\?\"'\)\]\}]+$", "", cap).strip()
            words = cap_clean.split()
            if words and words[-1].lower() in DANGLING_STOPWORDS:
                violations.append(f"{scene.id}[b{b_idx}]: caption ends with dangling stopword '{words[-1]}'")

            if cap.endswith("...") or cap.endswith("…"):
                violations.append(f"{scene.id}[b{b_idx}]: caption ends with truncation ellipsis")

            # Phase 3: Check duplicate repo name
            repo_name = getattr(facts, "repo_name", "") or script.repo_name
            if repo_name and re.search(rf"\b{re.escape(repo_name)}:\s*{re.escape(repo_name)}\b", cap, re.I):
                violations.append(f"{scene.id}[b{b_idx}]: caption duplicates repo name '{repo_name}' twice in a row")

            # Phase 3: Partial clause check (no verb in string > 3 words unless command/label)
            core_cap = re.sub(r"^[^:]+:\s*", "", cap).strip()
            norm_core = " ".join(core_cap.split()).lower()

            if scene.kind not in ("title", "terminal"):
                core_words = core_cap.split()
                cmd_prefixes = ("pip", "python", "npm", "npx", "yarn", "pnpm", "cargo", "docker", "make", "go", "node", "pytest")
                if len(core_words) > 3 and not any(core_words[0].lower().startswith(p) for p in cmd_prefixes):
                    from ..narrate.compress import has_verb
                    if not has_verb(core_cap):
                        violations.append(f"{scene.id}[b{b_idx}]: caption is partial clause without verb '{core_cap}'")

            if norm_core and norm_core in norm_spans:
                continue

            cap_tokens = _extract_content_tokens(core_cap)
            if cap_tokens:
                scene_tokens = _extract_content_tokens(beat.say) | _extract_content_tokens(scene.narration)
                uncovered = cap_tokens - (facts_pool | artifact_tokens | scene_tokens)
                covered_ratio = len(cap_tokens - uncovered) / len(cap_tokens)
                if covered_ratio < 0.50 and norm_core not in norm_spans:
                    violations.append(f"{scene.id}[b{b_idx}]: caption '{core_cap}' not grounded in source spans or facts ({uncovered})")

        if scene.on_screen and scene.on_screen.content:
            lines = [l.strip() for l in scene.on_screen.content.splitlines() if l.strip()]
            for l_idx, line in enumerate(lines):
                if scene.kind == "terminal":
                    # For terminal, verify balanced quotes per command line
                    if line.count('"') % 2 != 0:
                        violations.append(f"{scene.id}: on_screen command line {l_idx+1} has unbalanced quotes in '{line}'")
                    continue
                if scene.kind == "code":
                    continue
                # Phase 3: Balanced quotes and brackets on-screen
                if line.count('"') % 2 != 0:
                    violations.append(f"{scene.id}: on_screen line {l_idx+1} has unbalanced quotes in '{line}'")
                line_clean = re.sub(r"[\.,;:!\?\"'\)\]\}]+$", "", line).strip()
                l_words = line_clean.split()
                if l_words and l_words[-1].lower() in DANGLING_STOPWORDS:
                    violations.append(f"{scene.id}: on_screen line {l_idx+1} ends with dangling stopword '{l_words[-1]}'")
                if line.endswith("...") or line.endswith("…"):
                    violations.append(f"{scene.id}: on_screen line {l_idx+1} ends with truncation ellipsis")

    passed = len(violations) == 0
    return EvalGate(
        name="onscreen_text_integrity",
        passed=passed,
        value="0 violations" if passed else f"{len(violations)} violations",
        threshold="0 violations",
        details="All on-screen text verified for integrity and grounding"
        if passed else f"Integrity violations: {violations[:5]}",
    )
