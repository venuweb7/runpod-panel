# tests/test_api.py
from fastapi.testclient import TestClient
from app import main, runpod_client


def _client(): return TestClient(main.app)


def test_healthz_is_cheap_liveness(monkeypatch):
    def boom(): raise runpod_client.RunPodError("no key")
    monkeypatch.setattr(runpod_client, "list_pods", boom)
    r = _client().get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_pods_requires_allowed_email(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED", {"me@x.com"})
    monkeypatch.setattr(runpod_client, "list_pods", lambda: [])
    c = _client()
    assert c.get("/api/pods").status_code == 403  # no header
    assert c.get("/api/pods", headers={"X-Auth-Request-Email": "evil@y.com", "X-Auth-Request-User": "evil"}).status_code == 403
    assert c.get("/api/pods", headers={"X-Auth-Request-Email": "me@x.com"}).status_code == 403  # missing X-Auth-Request-User
    assert c.get("/api/pods", headers={"X-Auth-Request-Email": "me@x.com", "X-Auth-Request-User": "me"}).status_code == 200


def test_pods_502_on_runpod_error(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED", {"me@x.com"})
    def boom(): raise runpod_client.RunPodError("down")
    monkeypatch.setattr(runpod_client, "list_pods", boom)
    r = _client().get("/api/pods", headers={"X-Auth-Request-Email": "me@x.com", "X-Auth-Request-User": "me"})
    assert r.status_code == 502


def test_start_and_stop_call_client_and_audit(monkeypatch, capsys):
    monkeypatch.setattr(main, "ALLOWED", {"me@x.com"})
    calls = {}
    monkeypatch.setattr(runpod_client, "start_pod", lambda pid: calls.setdefault("start", pid) or {"id": pid})
    monkeypatch.setattr(runpod_client, "stop_pod", lambda pid: calls.setdefault("stop", pid) or {"id": pid})
    h = {"X-Auth-Request-Email": "me@x.com", "X-Auth-Request-User": "me"}
    c = _client()
    assert c.post("/api/pods/abc/start", headers=h).status_code == 200
    assert c.post("/api/pods/abc/stop", headers=h).status_code == 200
    assert calls == {"start": "abc", "stop": "abc"}
    out = capsys.readouterr().out
    assert "AUDIT start pod=abc by=me@x.com" in out
    assert "AUDIT stop pod=abc by=me@x.com" in out
