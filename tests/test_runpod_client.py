# tests/test_runpod_client.py
import httpx
from app import runpod_client


class _FakeResponse:
    def __init__(self, payload): self._payload = payload
    def raise_for_status(self): pass
    def json(self): return self._payload


def test_list_pods_normalizes(monkeypatch):
    payload = {"data": {"myself": {"pods": [
        {"id": "abc", "name": "qwen", "desiredStatus": "RUNNING",
         "costPerHr": 0.45, "gpuCount": 1,
         "machine": {"gpuDisplayName": "A40"},
         "runtime": {"uptimeInSeconds": 3600}},
    ]}}}
    monkeypatch.setenv("RUNPOD_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(payload))

    pods = runpod_client.list_pods()
    assert pods == [{
        "id": "abc", "name": "qwen", "status": "RUNNING", "gpu": "A40",
        "gpu_count": 1, "cost_per_hr": 0.45, "uptime_seconds": 3600,
    }]


def test_graphql_raises_on_errors(monkeypatch):
    payload = {"errors": [{"message": "bad"}]}
    monkeypatch.setenv("RUNPOD_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(payload))
    try:
        runpod_client.list_pods()
        assert False, "expected RunPodError"
    except runpod_client.RunPodError:
        pass


def test_start_and_stop_send_mutations(monkeypatch):
    sent = {}
    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        sent["query"] = json["query"]; sent["vars"] = json["variables"]
        key = "podResume" if "podResume" in json["query"] else "podStop"
        return _FakeResponse({"data": {key: {"id": "abc", "desiredStatus": "X"}}})
    monkeypatch.setenv("RUNPOD_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", fake_post)

    assert runpod_client.start_pod("abc")["id"] == "abc"
    assert "podResume" in sent["query"] and sent["vars"]["podId"] == "abc"
    assert runpod_client.stop_pod("abc")["id"] == "abc"
    assert "podStop" in sent["query"] and sent["vars"]["podId"] == "abc"
