"""Validator tests: one targeted test per defect class an LLM can plausibly produce."""
import pytest

from vatp_core import bt as btmod
from vatp_core.bt import BTNode
from vatp_core.scenarios import make_scenario
from vatp_core.validator import Validator

V = Validator()


def N(tag, name, children=None, **attrs):
    return BTNode(tag, name, {k: str(v) for k, v in attrs.items()}, children or [])


def world(idx=0):
    sc = make_scenario(idx, seed=1)
    return sc, sc.world


def simple_world():
    """crate in zone_a, bay empty, no blockers."""
    sc = make_scenario(1, seed=1)  # simple_delivery
    assert sc.template == "simple_delivery"
    return sc.world


def good_tree():
    return N("Sequence", "root", [
        N("NavigateTo", "a", zone="zone_a"),
        N("PickObject", "b", object="crate_1"),
        N("NavigateTo", "c", zone="loading_bay"),
        N("NavigateTo", "d", zone="zone_b"),
        N("PlaceObject", "e", object="crate_1", zone="zone_b"),
    ])


GOALS = [{"predicate": "object_at", "args": ["crate_1", "zone_b"]},
         {"predicate": "gripper_empty", "args": []}]


def codes(rep):
    return {i.code for i in rep.errors}


def test_valid_plan_passes():
    rep = V.validate_tree(good_tree(), simple_world(), GOALS, GOALS)
    assert rep.ok, rep.summary()
    assert rep.stats["nodes"] == 6


def test_xml_roundtrip_validates_identically():
    xml = btmod.to_xml(good_tree())
    assert V.validate_xml(xml, simple_world(), GOALS, GOALS).ok


def test_malformed_xml():
    assert codes(V.validate_xml("<root><oops", simple_world())) == {"XML_MALFORMED"}


def test_wrong_skeleton():
    assert "XML_MALFORMED" in codes(V.validate_xml("<root BTCPP_format='3'/>", simple_world()))


def test_unknown_skill():
    t = good_tree(); t.children[1].tag = "GraspObject"
    assert "UNKNOWN_NODE" in codes(V.validate_tree(t, simple_world()))


def test_unknown_zone_and_object():
    t = good_tree(); t.children[0].attrs["zone"] = "zone_c"; t.children[1].attrs["object"] = "pallet"
    assert {"UNKNOWN_ZONE", "UNKNOWN_OBJECT"} <= codes(V.validate_tree(t, simple_world()))


def test_blackboard_reference_rejected():
    t = good_tree(); t.children[0].attrs["zone"] = "{target}"
    assert "BLACKBOARD_REF" in codes(V.validate_tree(t, simple_world()))


def test_missing_and_extra_port():
    t = good_tree(); del t.children[0].attrs["zone"]; t.children[1].attrs["speed"] = "9"
    assert {"MISSING_PORT", "UNKNOWN_PORT"} <= codes(V.validate_tree(t, simple_world()))


def test_duplicate_node_names():
    t = good_tree(); t.children[1].name = "a"
    assert "DUPLICATE_NAME" in codes(V.validate_tree(t, simple_world()))


def test_bad_arity():
    t = N("Fallback", "f", [N("Wait", "w", seconds=1)])
    assert "BAD_ARITY" in codes(V.validate_tree(t, simple_world()))


def test_retry_bounds():
    inner = N("RetryUntilSuccessful", "r2", [N("Wait", "w", seconds=1)], num_attempts=4)
    t = N("RetryUntilSuccessful", "r1", [inner], num_attempts=4)
    c = codes(V.validate_tree(t, simple_world()))
    assert "RETRY_EXPLOSION" in c
    t2 = N("RetryUntilSuccessful", "r", [N("Wait", "w", seconds=1)], num_attempts=100)
    assert "OUT_OF_RANGE" in codes(V.validate_tree(t2, simple_world()))


def test_skip_navigation_is_illegal_transition():
    t = good_tree(); del t.children[0]  # never go to zone_a
    assert "NOT_AT_OBJECT" in codes(V.validate_tree(t, simple_world(), GOALS))


def test_place_without_pick():
    t = good_tree(); del t.children[1]
    assert "NOT_HOLDING" in codes(V.validate_tree(t, simple_world(), GOALS))


def test_geofence_direct_path_rejected_with_hint():
    t = good_tree(); del t.children[2]  # zone_a -> zone_b straight through the keep-out margin
    rep = V.validate_tree(t, simple_world(), GOALS)
    assert "GEOFENCE_PATH" in codes(rep)
    msg = next(i.message for i in rep.errors if i.code == "GEOFENCE_PATH")
    assert "loading_bay" in msg  # constructive hint


def test_payload_exceeded():
    w = simple_world(); w.objects["crate_1"].mass = 5.0
    assert "PAYLOAD_EXCEEDED" in codes(V.validate_tree(good_tree(), w))


def test_gripper_busy():
    w = simple_world()
    t = N("Sequence", "root", [
        N("NavigateTo", "a", zone="zone_a"), N("PickObject", "b", object="crate_1"),
        N("PickObject", "c", object="crate_1")])
    assert "GRIPPER_BUSY" in codes(V.validate_tree(t, w))


def test_zone_not_placeable_dock():
    t = N("Sequence", "root", [
        N("NavigateTo", "a", zone="zone_a"), N("PickObject", "b", object="crate_1"),
        N("NavigateTo", "c", zone="dock"), N("PlaceObject", "d", object="crate_1", zone="dock")])
    assert "ZONE_NOT_PLACEABLE" in codes(V.validate_tree(t, simple_world()))


def test_end_holding_and_goal_not_established():
    t = good_tree(); t.children.pop()  # forget to place
    c = codes(V.validate_tree(t, simple_world(), GOALS, GOALS))
    assert {"END_HOLDING", "GOAL_NOT_ESTABLISHED"} <= c


def test_declared_goal_must_be_wellformed():
    bad = [{"predicate": "object_at", "args": ["crate_1"]}]
    assert "BAD_GOAL" in codes(V.validate_tree(good_tree(), simple_world(), bad))


def test_transit_corridor_blocked_requires_clearing():
    sc = make_scenario(0, seed=3)
    # force the blocked variant
    w = sc.world
    w.objects["small_box_1"].zone = "loading_bay"
    naive = N("Sequence", "root", [
        N("NavigateTo", "a", zone="zone_a"), N("PickObject", "b", object="crate_1"),
        N("NavigateTo", "c", zone="loading_bay"), N("NavigateTo", "d", zone="zone_b"),
        N("PlaceObject", "e", object="crate_1", zone="zone_b")])
    rep = V.validate_tree(naive, w)
    assert "TRANSIT_BLOCKED" in codes(rep)


def test_conditional_fallback_branch_explored():
    """Fallback[CheckZoneClear(bay), Sequence[clear]] — bay blocked => clear branch is executed symbolically."""
    sc = make_scenario(0, seed=3)
    w = sc.world
    w.objects["small_box_1"].zone = "loading_bay"
    clear = N("Sequence", "clr", [
        N("NavigateTo", "c1", zone="loading_bay"), N("PickObject", "c2", object="small_box_1"),
        N("NavigateTo", "c3", zone="staging"),
        N("PlaceObject", "c4", object="small_box_1", zone="staging")])
    deliver = [
        N("NavigateTo", "d1", zone="zone_a"), N("PickObject", "d2", object="crate_1"),
        N("NavigateTo", "d3", zone="loading_bay"), N("NavigateTo", "d4", zone="zone_b"),
        N("PlaceObject", "d5", object="crate_1", zone="zone_b")]
    t = N("Sequence", "root", [N("Fallback", "fb", [N("CheckZoneClear", "chk", zone="loading_bay"), clear]), *deliver])
    goals = [{"predicate": "object_at", "args": ["crate_1", "zone_b"]},
             {"predicate": "zone_clear", "args": ["loading_bay"]}, {"predicate": "gripper_empty", "args": []}]
    rep = V.validate_tree(t, w, goals, goals)
    assert rep.ok, rep.summary()


def test_dead_branch_still_statically_checked():
    sc = make_scenario(1, seed=1)
    w = sc.world  # bay is clear -> the clear-branch is never taken symbolically
    bad_branch = N("NavigateTo", "x", zone="nowhere")
    t = N("Fallback", "fb", [N("CheckZoneClear", "chk", zone="loading_bay"), bad_branch])
    assert "UNKNOWN_ZONE" in codes(V.validate_tree(t, w))


# --------------------------------------------------------------- plan JSON -> tree
def test_compile_errors_are_reported():
    plan = {"root": "a", "goals": [], "rationale": "", "nodes": [
        {"id": "a", "type": "Sequence", "params": [], "children": ["b", "zz", "b"]},
        {"id": "b", "type": "Wait", "params": [{"name": "seconds", "value": "1"}], "children": []}]}
    tree, issues = btmod.compile_plan(plan)
    assert tree is None
    assert {"DANGLING_CHILD", "SHARED_CHILD"} <= {i.code for i in issues}


def test_cycle_detected():
    plan = {"root": "a", "goals": [], "rationale": "", "nodes": [
        {"id": "a", "type": "Sequence", "params": [], "children": ["b"]},
        {"id": "b", "type": "Sequence", "params": [], "children": ["a"]}]}
    tree, issues = btmod.compile_plan(plan)
    assert tree is None and any(i.code == "CYCLE" for i in issues)


def test_validate_plan_json_end_to_end():
    plan = btmod.tree_to_plan(good_tree(), GOALS)
    tree, rep = V.validate_plan(plan, simple_world(), GOALS)
    assert rep.ok and tree is not None


@pytest.mark.parametrize("idx", range(4))
def test_validator_is_fast(idx):
    sc = make_scenario(idx, seed=0)
    from vatp_core.mock_planner import MockBackend
    from vatp_core.llm import Prompt
    plan = MockBackend().generate(Prompt("", "", {"world": sc.world, "mode": "plan",
                                                   "instruction": sc.instruction}), {}).data
    _, rep = V.validate_plan(plan, sc.world, sc.required_goals)
    assert rep.ok, rep.summary()
    assert rep.elapsed_ms < 100
