"""GeminiBackend tests against a local fake HTTP server (no network, no API key needed)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vatp_core import bt as btmod
from vatp_core.llm import GeminiBackend, LLMError, Prompt, gemini_schema, make_backend
from vatp_core.mock_planner import MockBackend
from vatp_core.planner import Planner
from vatp_core.scenarios import make_scenario
from vatp_core.skills import load_library

KEY = "test-key-should-never-leak-123"


class _Fake(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.script: list[tuple[int, dict]] = []
        self.requests: list[dict] = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}/v1beta"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep test output quiet
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
        code, payload = self.server.script.pop(0)
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def server():
    s = _Fake()
    yield s
    s.shutdown()
    s.server_close()


def ok(plan, finish="STOP"):
    return 200, {"candidates": [{"content": {"parts": [{"text": json.dumps(plan)}]}, "finishReason": finish}],
                 "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7, "thoughtsTokenCount": 3},
                 "modelVersion": "fake-1"}


def backend(server, **kw):
    return GeminiBackend(model="fake-model", api_key=KEY, base_url=server.url, backoff_s=0.0, **kw)


SCHEMA = btmod.plan_json_schema(["Sequence", "NavigateTo"])


def test_request_shape_and_parsing(server):
    server.script = [ok({"root": "n1", "nodes": [], "goals": [], "rationale": "x"})]
    res = backend(server).generate(Prompt("SYS", "USER"), SCHEMA)
    r = server.requests[0]
    assert r["path"].endswith("/models/fake-model:generateContent")
    assert r["key"] == KEY  # sent as a header, not in the URL
    assert KEY not in r["path"]
    assert r["body"]["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert r["body"]["contents"][0]["parts"][0]["text"] == "USER"
    gc = r["body"]["generationConfig"]
    assert gc["responseMimeType"] == "application/json" and gc["temperature"] == 0.0
    assert "additionalProperties" not in json.dumps(gc["responseSchema"])
    assert res.data["root"] == "n1"
    assert (res.input_tokens, res.output_tokens, res.model) == (11, 10, "fake-1")


def test_schema_sanitising_keeps_property_named_type():
    s = gemini_schema(SCHEMA)
    assert "additionalProperties" not in json.dumps(s)
    node = s["properties"]["nodes"]["items"]["properties"]
    assert "type" in node and node["type"]["enum"] == ["NavigateTo", "Sequence"]  # enum kept, name kept
    assert set(s["required"]) == {"rationale", "goals", "root", "nodes"}


def test_retries_rate_limit_then_succeeds(server):
    server.script = [(429, {"error": {"message": "quota"}}), (503, {}), ok({"a": 1})]
    assert backend(server).generate(Prompt("s", "u"), SCHEMA).data == {"a": 1}
    assert len(server.requests) == 3


def test_gives_up_after_retries(server):
    server.script = [(429, {"error": {"message": "quota"}})] * 3
    with pytest.raises(LLMError, match="gave up after 3 attempts"):
        backend(server, retries=2).generate(Prompt("s", "u"), SCHEMA)


def test_client_error_is_not_retried_and_does_not_leak_key(server):
    server.script = [(400, {"error": {"message": "bad schema"}})]
    with pytest.raises(LLMError) as e:
        backend(server).generate(Prompt("s", "u"), SCHEMA)
    assert "400" in str(e.value) and "bad schema" in str(e.value) and KEY not in str(e.value)
    assert len(server.requests) == 1


@pytest.mark.parametrize("resp,match", [
    (ok({"a": 1}, finish="MAX_TOKENS"), "truncated"),
    ((200, {"promptFeedback": {"blockReason": "SAFETY"}}), "blocked"),
    ((200, {"candidates": []}), "no candidates"),
    ((200, {"candidates": [{"content": {"parts": [{"text": "not json"}]}, "finishReason": "STOP"}]}), "invalid JSON"),
])
def test_bad_responses_become_llm_errors(server, resp, match):
    server.script = [resp]
    with pytest.raises(LLMError, match=match):
        backend(server).generate(Prompt("s", "u"), SCHEMA)


def test_missing_key_and_factory(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        make_backend("gemini")
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    b = make_backend("gemini", model="m")
    assert b.name == "gemini:m"


def _mock_plan(sc, defect=False):
    from vatp_core.llm import Prompt as P
    mb = MockBackend(defect_rate=1.0 if defect else 0.0, seed=0)
    plan = mb.generate(P("", "", {"world": sc.world, "mode": "plan", "instruction": sc.instruction, "attempt": 0}), {}).data
    plan.pop("_injected_defect", None)
    return plan


def test_planner_repair_loop_through_http_backend(server):
    """A defective first answer is rejected by the validator, the error text goes back in the prompt,
    and the corrected second answer is accepted - all through the real HTTP code path."""
    sc = make_scenario(1, seed=0)
    good = _mock_plan(sc)
    bad = json.loads(json.dumps(good))
    for n in bad["nodes"]:  # hallucinate a zone
        if n["type"] == "NavigateTo":
            n["params"] = [{"name": "zone", "value": "zone_c"}]
    server.script = [ok(bad), ok(good)]
    res = Planner(backend(server)).plan(sc.instruction, sc.world, sc.required_goals)
    assert res.ok and res.n_repairs == 1
    assert res.metrics()["backend"] == "gemini:fake-model"
    assert any(i.code == "UNKNOWN_ZONE" for i in res.attempts[0].issues)
    second_prompt = server.requests[1]["body"]["contents"][0]["parts"][0]["text"]
    assert "REJECTED BY THE VALIDATOR" in second_prompt and "zone_c" in second_prompt


def test_planner_rejects_when_model_keeps_failing(server):
    sc = make_scenario(1, seed=0)
    bad = _mock_plan(sc)
    bad["nodes"][0]["type"] = "GraspObject"
    server.script = [ok(bad)] * 3
    res = Planner(backend(server), max_repairs=2).plan(sc.instruction, sc.world, sc.required_goals)
    assert not res.ok and res.xml is None and len(res.attempts) == 3  # nothing would execute


def test_thinking_level_is_sent_and_named(server):
    server.script = [ok({"a": 1}), ok({"a": 1})]
    b = backend(server, thinking_level="low")
    assert b.name == "gemini:fake-model[thinking=low]"
    b.generate(Prompt("s", "u"), SCHEMA)
    assert server.requests[0]["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    backend(server).generate(Prompt("s", "u"), SCHEMA)  # unset -> field absent, model default applies
    assert "thinkingConfig" not in server.requests[1]["body"]["generationConfig"]


def test_daily_quota_fails_fast_without_retrying(server):
    err = {"error": {"message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12205s"}]}}
    server.script = [(429, err)]
    with pytest.raises(LLMError, match="DAILY request quota exhausted.*12205s"):
        backend(server).generate(Prompt("s", "u"), SCHEMA)
    assert len(server.requests) == 1  # no pointless retries
