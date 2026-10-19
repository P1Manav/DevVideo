"""
The Explainer Writer package: deterministic, extractive narration composed from real
repository facts and source spans, obeying rules R1 to R12 and T1 to T10.
"""
from __future__ import annotations

import logging
from ..analyze import RepoFacts, is_auxiliary_or_test_path
from ..schema import Beat, Scene, ScriptPlan, check_for_banned_phrases
from ..visuals import attach_visuals_to_script
from .compress import clean_caption_text, compress_sentence, has_verb, is_dangling
from .scenes_code import build_code_scene
from .scenes_diagram import build_diagram_scene
from .scenes_fit import build_fit_scene
from .scenes_overview import build_overview_scene
from .scenes_recap import build_recap_scene
from .scenes_terminal import build_terminal_scene
from .scenes_title import build_title_scene
from .speech import humanize_identifier, tts_normalize_speech
from .verbs import (
    DOCSTRING_TRANSFORMS,
    IMPERATIVE_VERBS,
    convert_docstring_to_verb_phrase,
    transform_bullet_to_sentence,
)

logger = logging.getLogger(__name__)


class ExplainerWriter:
    """
    Extractive, deterministic script generator producing 8-12 beats (48-58s)
    backed by real SourceSpans and adhering strictly to R1-R12 and T1-T10 rules.
    """

    def __init__(self, facts: RepoFacts) -> None:
        self.facts = facts
        self.readme_file = facts.readme_file or "README.md"

    def write_script(self) -> ScriptPlan:
        """Compose script plan from facts, strictly enforcing quality rules."""
        scenes: list[Scene] = []

        # 1. Title Scene (R10 dominant first-party code language, R1/R2 compression)
        title_scene = build_title_scene(self.facts, self.readme_file)
        if title_scene:
            scenes.append(title_scene)

        # 2. Overview Scene (R7/T9: what it is, what it does, what you get)
        ov_scene = build_overview_scene(self.facts, self.readme_file)
        if ov_scene:
            scenes.append(ov_scene)

        # 3. Diagram Scene (R5: architecture selection excluding tests/examples)
        core_mods = [m for m in self.facts.ranked_top_modules if not is_auxiliary_or_test_path(m)]
        if len(core_mods) >= 2 or len(self.facts.import_graph) >= 1:
            diag_scene = build_diagram_scene(self.facts, self.readme_file)
            if diag_scene:
                scenes.append(diag_scene)

        # 4. Code Scene (R4/T4/T5/T6: key code selection from core public functions)
        code_scene = build_code_scene(self.facts, self.readme_file)
        if code_scene:
            scenes.append(code_scene)

        # 5. Terminal Scene (R6/T7: install and run commands, valid shell only)
        term_scene = build_terminal_scene(self.facts, self.readme_file)
        if term_scene:
            scenes.append(term_scene)

        # 6. Fit Scene (Phase 4 / N3: ALWAYS present, honest pipeline fit)
        fit_scene = build_fit_scene(self.facts, self.readme_file)
        if fit_scene:
            scenes.append(fit_scene)

        # 7. Recap Scene (R3, R9, T8: takeaways from real facts, first-party entry)
        recap_scene = build_recap_scene(self.facts, self.readme_file)
        if recap_scene:
            scenes.append(recap_scene)

        # Ensure at least 3 scenes
        if len(scenes) < 3:
            if not any(s.id == "title" for s in scenes):
                scenes.insert(0, build_title_scene(self.facts, self.readme_file))
            if not any(s.id == "overview" for s in scenes):
                scenes.insert(1, build_overview_scene(self.facts, self.readme_file))
            if not any(s.id == "recap" for s in scenes):
                scenes.append(build_recap_scene(self.facts, self.readme_file))

        # Budget check (R12): target 8-12 beats, duration <= 58.0s
        # Phase 4: NEVER drop fit scene! Drop secondary beats in overview/diagram/code instead.
        while (sum(len(s.narration.split()) for s in scenes) / 140.0) * 60.0 > 56.0:
            trimmed = False
            for sc_id in ("code", "overview", "diagram", "terminal"):
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


def write_explainer_script(facts: RepoFacts) -> ScriptPlan:
    """Convenience entry point for generating deterministic explainer script plan."""
    return ExplainerWriter(facts).write_script()


generate_explainer_script = write_explainer_script
