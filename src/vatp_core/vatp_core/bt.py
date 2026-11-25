"""Behavior-tree data model, BehaviorTree.CPP v4 XML (de)serialisation, and the
compiler from the LLM's constrained JSON plan (flat node graph) to a tree.

Why a flat node list instead of nested JSON?  Grammar-constrained decoding
(structured outputs) does not support recursive schemas, and a flat graph makes
dangling references / cycles / shared children *explicit, checkable errors*
rather than something silently lost in nesting.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Iterator

from .issues import Issue

MAIN_TREE_ID = "MainTree"


@dataclass
class BTNode:
    tag: str
    name: str  # unique instance id (BT.CPP `name` attribute)
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["BTNode"] = field(default_factory=list)

    def walk(self) -> Iterator["BTNode"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def count(self) -> int:
        return sum(1 for _ in self.walk())

    def depth(self) -> int:
        return 1 + max((c.depth() for c in self.children), default=0)

    def find(self, name: str) -> "BTNode | None":
        return next((n for n in self.walk() if n.name == name), None)

    def to_element(self) -> ET.Element:
        el = ET.Element(self.tag)
        el.set("name", self.name)
        for k, v in self.attrs.items():
            el.set(k, v)
        for c in self.children:
            el.append(c.to_element())
        return el


class BTParseError(ValueError):
    pass


def to_xml(root: BTNode, tree_id: str = MAIN_TREE_ID) -> str:
    top = ET.Element("root", {"BTCPP_format": "4", "main_tree_to_execute": tree_id})
    bt = ET.SubElement(top, "BehaviorTree", {"ID": tree_id})
    bt.append(root.to_element())
    ET.indent(top, space="  ")
    return ET.tostring(top, encoding="unicode")


def _from_element(el: ET.Element, auto: list[int]) -> BTNode:
    attrs = dict(el.attrib)
    name = attrs.pop("name", None)
    if name is None:
        auto[0] += 1
        name = f"_auto{auto[0]}"
    return BTNode(el.tag, name, attrs, [_from_element(c, auto) for c in el])


def parse_xml(xml: str) -> BTNode:
    """Parse BT.CPP v4 XML produced by us (or anything else) into a BTNode tree.

    Raises BTParseError for malformed XML or an unexpected document skeleton;
    semantic checks live in the validator.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise BTParseError(f"malformed XML: {e}") from e
    if root.tag != "root":
        raise BTParseError(f"document element must be <root>, got <{root.tag}>")
    if root.get("BTCPP_format") != "4":
        raise BTParseError("missing BTCPP_format=\"4\"")
    trees = [c for c in root if c.tag == "BehaviorTree"]
    if len(trees) != 1:
        raise BTParseError(f"exactly one <BehaviorTree> required, found {len(trees)}")
    main = root.get("main_tree_to_execute")
    if main != trees[0].get("ID"):
        raise BTParseError("main_tree_to_execute must name the <BehaviorTree> ID")
    kids = list(trees[0])
    if len(kids) != 1:
        raise BTParseError(f"<BehaviorTree> must contain exactly one root node, found {len(kids)}")
    return _from_element(kids[0], [0])


# --------------------------------------------------------------------------
# LLM plan JSON -> tree
# --------------------------------------------------------------------------
def plan_json_schema(tags: list[str]) -> dict[str, Any]:
    """JSON schema for the constrained LLM output (flat node graph)."""
    return {
        "type": "object",
        "properties": {
            "rationale": {"type": "string"},
            "goals": {
                "type": "array",
                "description": "Postconditions the tree must establish on every success path.",
                "items": {
                    "type": "object",
                    "properties": {
                        "predicate": {"type": "string", "enum": ["object_at", "robot_at", "gripper_empty", "zone_clear"]},
                        "args": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["predicate", "args"],
                    "additionalProperties": False,
                },
            },
            "root": {"type": "string", "description": "id of the root node"},
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string", "enum": sorted(tags)},
                        "params": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                                "required": ["name", "value"],
                                "additionalProperties": False,
                            },
                        },
                        "children": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "type", "params", "children"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["rationale", "goals", "root", "nodes"],
        "additionalProperties": False,
    }


def compile_plan(plan: dict[str, Any]) -> tuple[BTNode | None, list[Issue]]:
    """Resolve the flat node graph into a tree; report structural defects as Issues."""
    issues: list[Issue] = []
    nodes_raw = plan.get("nodes", [])
    by_id: dict[str, dict[str, Any]] = {}
    for n in nodes_raw:
        nid = n.get("id", "")
        if not nid:
            issues.append(Issue("MISSING_ID", "node without id"))
            continue
        if nid in by_id:
            issues.append(Issue("DUPLICATE_ID", f"node id '{nid}' used twice", nid))
            continue
        by_id[nid] = n

    root_id = plan.get("root")
    if root_id not in by_id:
        issues.append(Issue("BAD_ROOT", f"root '{root_id}' is not a defined node"))
        return None, issues

    parent_of: dict[str, str] = {}
    for nid, n in by_id.items():
        for c in n.get("children", []):
            if c not in by_id:
                issues.append(Issue("DANGLING_CHILD", f"child '{c}' of '{nid}' is not defined", nid))
            elif c in parent_of:
                issues.append(Issue("SHARED_CHILD", f"node '{c}' has two parents ('{parent_of[c]}','{nid}')", c))
            else:
                parent_of[c] = nid
    if root_id in parent_of:
        issues.append(Issue("CYCLE", f"root '{root_id}' is also a child of '{parent_of[root_id]}'", root_id))

    visiting: set[str] = set()
    reached: set[str] = set()

    def build(nid: str) -> BTNode | None:
        if nid in visiting:
            issues.append(Issue("CYCLE", f"cycle through node '{nid}'", nid))
            return None
        visiting.add(nid)
        reached.add(nid)
        n = by_id[nid]
        params: dict[str, str] = {}
        for p in n.get("params", []):
            if p["name"] in params:
                issues.append(Issue("DUPLICATE_PARAM", f"param '{p['name']}' repeated", nid))
            params[p["name"]] = str(p["value"])
        kids: list[BTNode] = []
        for c in n.get("children", []):
            if c in by_id:
                k = build(c)
                if k is not None:
                    kids.append(k)
        visiting.discard(nid)
        return BTNode(n["type"], nid, params, kids)

    tree = build(root_id)
    for nid in by_id:
        if nid not in reached:
            issues.append(Issue("UNREACHABLE_NODE", f"node '{nid}' is not reachable from root", nid, "warning"))
    if any(i.severity == "error" for i in issues):
        return None, issues
    return tree, issues


def tree_to_plan(root: BTNode, goals: list[dict[str, Any]] | None = None, rationale: str = "") -> dict[str, Any]:
    """Inverse of compile_plan (used by the mock planner, mutation tests and replan splicing)."""
    nodes = [
        {
            "id": n.name,
            "type": n.tag,
            "params": [{"name": k, "value": v} for k, v in n.attrs.items()],
            "children": [c.name for c in n.children],
        }
        for n in root.walk()
    ]
    return {"rationale": rationale, "goals": goals or [], "root": root.name, "nodes": nodes}
