import copy

from vatp_core.llm import make_backend
from vatp_core.mock_planner import MockBackend
from vatp_core.planner import Failure, Planner
from vatp_core.rag import Retriever
from vatp_core.scenarios import generate_suite, make_scenario, Scenario
from vatp_core.skills import load_library
from vatp_core.validator import Validator, _holds
from vatp_core.world import World


# ------------------------------------------------------------------------ RAG
def test_rag_retrieves_failure_specific_procedure():
    r = Retriever()
    assert r.search("GRASP_FAILED PickObject", k=1, prefix="RP-")[0].id == "RP-02"
    assert r.search("UNEXPECTED_OBSTACLE loading_bay blocked", k=1, prefix="RP-")[0].id == "RP-01"
    assert r.search("NAV_TIMEOUT NavigateTo", k=1, prefix="RP-")[0].id == "RP-03"
    assert r.search("PLACE_FAILED", k=1, prefix="RP-")[0].id == "RP-04"


def test_rag_always_includes_all_safety_rules():
    assert len(Retriever().always("SC-")) >= 9


# ------------------------------------------------------------- skill library
def test_skill_library_loads_and_every_predicate_is_known():
    lib = load_library()
    assert {"NavigateTo", "PickObject", "PlaceObject", "CheckZoneClear"} <= set(lib.skills)
    assert "Fallback" in lib.controls
    assert "NavigateTo" in lib.prompt_description()


# ----------------------------------------------------------------- scenarios
def test_suite_has_20_solvable_deterministic_scenarios():
    a, b = generate_suite(20, seed=0), generate_suite(20, seed=0)
    assert len(a) == 20
    assert [s.to_yaml() for s in a] == [s.to_yaml() for s in b]
    kinds = {s.fault.type for s in a}
    assert {"none", "obstacle_spawn", "grasp_fail", "nav_block", "place_fail"} <= kinds


def test_scenario_yaml_roundtrip():
    s = make_scenario(9, seed=0)
    s2 = Scenario.from_yaml(s.to_yaml())
    assert s2.to_yaml() == s.to_yaml()
    assert isinstance(s2.world, World)


# -------------------------------------------- planner + validator + repair loop
def _apply_success(sc: Scenario, planner_result) -> World:
    """Independent oracle: pick the symbolic success path and check required goals hold."""
    from vatp_core.validator import _Executor
    v = Validator()
    ex = _Executor(v, sc.world, [])
    outs = ex.run(planner_result.tree, [(True, sc.world.copy())])
    succ = [w for ok, w in outs if ok]
    assert succ, "no success path"
    return succ[0]


def test_all_20_scenarios_planned_valid_and_goal_correct_without_defects():
    planner = Planner(MockBackend(defect_rate=0.0))
    for sc in generate_suite(20, seed=0):
        res = planner.plan(sc.instruction, sc.world, sc.required_goals)
        assert res.ok, (sc.id, sc.template, res.report.summary())
        final = _apply_success(sc, res)
        assert all(_holds(g, final) for g in sc.required_goals), (sc.id, sc.template)
        assert res.n_repairs == 0


def test_repair_loop_fixes_every_injected_defect_class():
    seen = set()
    for seed in range(30):
        planner = Planner(MockBackend(defect_rate=1.0, seed=seed))
        sc = make_scenario(seed % 4, seed=seed)
        res = planner.plan(sc.instruction, sc.world, sc.required_goals)
        first = res.attempts[0]
        injected = (first.plan or {}).get("_injected_defect")
        assert injected, "defect_rate=1.0 must inject"
        assert any(i.severity == "error" for i in first.issues), f"validator MISSED defect '{injected}'"
        assert res.ok and res.n_repairs >= 1
        seen.add(injected)
    assert {"drop_nav", "direct_nav", "bad_zone", "bad_skill", "blackboard", "drop_place", "unbounded"} <= seen


def test_replan_after_unexpected_obstacle_clears_it_and_finishes():
    sc = make_scenario(1, seed=0)  # simple delivery, bay initially clear
    w = sc.world.copy()
    # mid-mission: robot at zone_a holding the crate; a box has appeared in the bay
    w.robot_zone, w.robot_pos = "zone_a", w.zones["zone_a"].access
    w.holding, w.objects["crate_1"].zone = "crate_1", None
    from vatp_core.world import WorldObject
    w.objects["obstacle_1"] = WorldObject("obstacle_1", 0.5, "loading_bay")
    planner = Planner(MockBackend())
    res = planner.replan(sc.instruction, w, Failure("n9", "NavigateTo", "NAV_BLOCKED", "bay obstructed"),
                         required_goals=[{"predicate": "object_at", "args": ["crate_1", "zone_b"]},
                                         {"predicate": "gripper_empty", "args": []}])
    assert res.ok, res.report.summary()
    tags = [n.tag for n in res.tree.walk()]
    assert "PickObject" in tags and "PlaceObject" in tags
    # the holding crate must be parked before the obstacle is picked
    places = [n.attrs for n in res.tree.walk() if n.tag == "PlaceObject"]
    assert {"object": "obstacle_1", "zone": "staging"} in places
    assert places[-1] == {"object": "crate_1", "zone": "zone_b"}


def test_make_backend_mock():
    assert make_backend("mock").name.startswith("mock")


def test_metrics_shape():
    sc = make_scenario(0, seed=0)
    res = Planner(MockBackend()).plan(sc.instruction, sc.world, sc.required_goals)
    m = res.metrics()
    assert m["ok"] and m["nodes"] > 3 and m["first_attempt_valid"]
