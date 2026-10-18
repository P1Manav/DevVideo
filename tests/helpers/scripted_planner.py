"""
Test helper: ScriptedPlanner for exercising the reasoning and revision loop.
"""

from __future__ import annotations

from src.analyze import RepoFacts
from src.schema import Beat, Evidence, OnScreen, Scene, ScriptPlan


class ScriptedPlanner:
    """
    Returns a sequence of predetermined plans on successive calls.
    Allows simulating:
    1. First draft failing verification (e.g. missing evidence file or banned buzzword)
    2. Second draft passing verification after receiving feedback
    """
    name = "scripted"

    def __init__(self, plans: list[ScriptPlan]) -> None:
        self.plans = plans
        self.call_count = 0
        self.received_feedbacks: list[list[str] | None] = []

    def plan(
        self,
        facts: RepoFacts,
        limits=None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        self.received_feedbacks.append(feedback)
        if self.call_count < len(self.plans):
            plan = self.plans[self.call_count]
            self.call_count += 1
            return plan
        return self.plans[-1]
