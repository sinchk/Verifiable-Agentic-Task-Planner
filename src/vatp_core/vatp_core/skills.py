"""Skill library loader: typed view over spec/skills.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SPEC_PATH = Path(__file__).parent / "spec" / "skills.yaml"


@dataclass(frozen=True)
class Port:
    name: str
    type: str  # zone | object | float | int | string
    required: bool = True
    min: float | None = None
    max: float | None = None

    @staticmethod
    def from_dict(name: str, d: dict[str, Any]) -> "Port":
        return Port(name, d["type"], d.get("required", True), d.get("min"), d.get("max"))


@dataclass(frozen=True)
class Skill:
    name: str
    kind: str  # condition | action
    description: str
    ports: dict[str, Port]
    pre: tuple[str, ...] = ()
    eff: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlNode:
    name: str
    min_children: int
    max_children: int | None
    ports: dict[str, Port] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillLibrary:
    version: int
    skills: dict[str, Skill]
    controls: dict[str, ControlNode]
    failure_codes: tuple[str, ...]

    def is_known(self, tag: str) -> bool:
        return tag in self.skills or tag in self.controls

    def prompt_description(self) -> str:
        """Compact, deterministic text rendering for the LLM prompt."""
        lines = ["CONTROL / DECORATOR NODES:"]
        for c in self.controls.values():
            ports = ", ".join(
                f"{p.name}:{p.type}[{p.min}..{p.max}]" for p in c.ports.values()
            )
            n = f"{c.min_children}..{c.max_children if c.max_children else 'N'} children"
            lines.append(f"  - {c.name} ({n}){' ports: ' + ports if ports else ''}")
        lines.append("SKILLS (leaf nodes):")
        for s in self.skills.values():
            ports = ", ".join(f"{p.name}:{p.type}" for p in s.ports.values())
            lines.append(f"  - {s.name} [{s.kind}] ({ports}) — {s.description}")
            if s.pre:
                lines.append(f"      requires: {', '.join(s.pre)}")
            if s.eff:
                lines.append(f"      effects: {', '.join(s.eff)}")
        return "\n".join(lines)


@lru_cache(maxsize=1)
def load_library(path: str | None = None) -> SkillLibrary:
    raw = yaml.safe_load(Path(path or SPEC_PATH).read_text())
    skills = {
        name: Skill(
            name=name,
            kind=d["kind"],
            description=d["description"],
            ports={p: Port.from_dict(p, pd) for p, pd in d.get("ports", {}).items()},
            pre=tuple(d.get("pre", [])),
            eff=tuple(d.get("eff", [])),
        )
        for name, d in raw["skills"].items()
    }
    controls = {
        name: ControlNode(
            name=name,
            min_children=d["min_children"],
            max_children=d["max_children"],
            ports={p: Port.from_dict(p, pd) for p, pd in d.get("ports", {}).items()},
        )
        for name, d in raw["control_nodes"].items()
    }
    return SkillLibrary(
        version=raw["version"],
        skills=skills,
        controls=controls,
        failure_codes=tuple(raw["failure_codes"]),
    )
