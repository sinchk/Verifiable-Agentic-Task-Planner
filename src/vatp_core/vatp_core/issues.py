"""Structured validation issues (machine-readable so they can be fed back to the LLM)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Issue:
    code: str  # stable identifier, e.g. UNKNOWN_SKILL, PRECONDITION, GEOFENCE
    message: str
    node: str | None = None  # BT node name (== id in the plan)
    severity: str = "error"  # error | warning

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        loc = f" @{self.node}" if self.node else ""
        return f"[{self.severity.upper()} {self.code}{loc}] {self.message}"


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
