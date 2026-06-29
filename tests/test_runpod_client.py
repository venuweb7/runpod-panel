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
