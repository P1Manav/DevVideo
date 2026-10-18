"""
Evaluation report data structures.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EvalGate:
    """Result of a single evaluation gate."""
    name: str
    passed: bool
    value: str
    threshold: str
    details: str = ""


@dataclass
class EvalReport:
    """Full evaluation report for a generated video."""
    gates: list[EvalGate] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    all_gates_passed: bool = False
    backend_requested: str = ""
    backend_used: str = ""
    fallback_reason: str = ""
    renderer_used: str = ""
    renderer_fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_gates_passed": self.all_gates_passed,
            "gates": [asdict(g) for g in self.gates],
            "metrics": self.metrics,
            "backend_requested": self.backend_requested,
            "backend_used": self.backend_used,
            "fallback_reason": self.fallback_reason,
            "renderer_used": self.renderer_used,
            "renderer_fallback_reason": self.renderer_fallback_reason,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        logger.info(f"Eval report saved to {path}")

    @classmethod
    def load(cls, path: Path) -> EvalReport:
        data = json.loads(path.read_text(encoding="utf-8"))
        gates = [EvalGate(**g) for g in data.get("gates", [])]
        return cls(
            gates=gates,
            metrics=data.get("metrics", {}),
            all_gates_passed=data.get("all_gates_passed", False),
            backend_requested=data.get("backend_requested", ""),
            backend_used=data.get("backend_used", ""),
            fallback_reason=data.get("fallback_reason", ""),
            renderer_used=data.get("renderer_used", ""),
            renderer_fallback_reason=data.get("renderer_fallback_reason", ""),
        )
