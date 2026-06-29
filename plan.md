# RunPod Control Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small self-hosted web panel that lists the user's RunPod pods and lets them start/stop them with one click (with cost/uptime), guarded by Google SSO, deployable on their existing Traefik/Docker VPS.

**Architecture:** A stateless FastAPI app (`runpod-panel`) serves a single web page + 4 JSON endpoints and talks to the RunPod GraphQL API with a server-side key. It runs as a Docker container behind the user's existing Traefik, with `oauth2-proxy` (Google login + email allowlist) as a forward-auth gate. No database; nothing stored.

**Tech Stack:** Python 3.12, FastAPI, httpx, pytest; Docker + docker-compose; oauth2-proxy; Traefik (existing).

---

## File Structure

```
runpod-panel/
├── app/
│   ├── __init__.py
│   ├── runpod_client.py     # RunPod GraphQL calls: list_pods/start_pod/stop_pod
│   ├── main.py              # FastAPI app: routes, auth-header check, static serving
│   └── static/
│       └── index.html       # the UI (HTML + inline CSS/JS)
├── tests/
│   ├── __init__.py
│   ├── test_runpod_client.py
│   └── test_api.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml       # runpod-panel + oauth2-proxy (+ Traefik labels)
├── .env.example
└── DEPLOY.md                # step-by-step deploy guide for the VPS web terminal
```

Responsibilities: `runpod_client.py` = all RunPod API I/O (the only file that knows GraphQL). `main.py` = HTTP surface + auth + audit logging. `index.html` = presentation. Config/deploy files are infra-only.

---

## Task 0: Project scaffold

**Files:**
- Create: `runpod-panel/requirements.txt`, `runpod-panel/app/__init__.py`, `runpod-panel/tests/__init__.py`

- [ ] **Step 1: Create the folder + git repo**

Run:
```bash
mkdir -p runpod-panel/app/static runpod-panel/tests
cd runpod-panel && git init
```

- [ ] **Step 2: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
pytest==8.3.3
```

- [ ] **Step 3: Create empty package markers**

```bash
touch app/__init__.py tests/__init__.py
```

- [ ] **Step 4: Create a venv and install**

Run:
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```
Expected: installs without error; `pytest --version` works.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "chore: scaffold runpod-panel project"
```

---

## Task 1: RunPod client — list_pods

**Files:**
- Create: `runpod-panel/app/runpod_client.py`
- Test: `runpod-panel/tests/test_runpod_client.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `. .venv/bin/activate && pytest tests/test_runpod_client.py -v`
Expected: FAIL (`ModuleNotFoundError: app.runpod_client` / attribute errors).

- [ ] **Step 3: Write minimal implementation**

```python
# app/runpod_client.py
import os
import httpx

RUNPOD_API_URL = "https://api.runpod.io/graphql"


class RunPodError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise RunPodError("RUNPOD_API_KEY not set")
    return key


def _graphql(query: str, variables: dict | None = None) -> dict:
    resp = httpx.post(
        RUNPOD_API_URL,
        params={"api_key": _api_key()},
        json={"query": query, "variables": variables or {}},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RunPodError(data["errors"][0].get("message", "RunPod API error"))
    return data["data"]


def _normalize(p: dict) -> dict:
    runtime = p.get("runtime") or {}
    machine = p.get("machine") or {}
    return {
        "id": p["id"],
        "name": p.get("name") or p["id"],
        "status": p.get("desiredStatus", "UNKNOWN"),
        "gpu": machine.get("gpuDisplayName") or "?",
        "gpu_count": p.get("gpuCount") or 1,
        "cost_per_hr": p.get("costPerHr") or 0.0,
        "uptime_seconds": (runtime.get("uptimeInSeconds") or 0),
    }


_LIST_QUERY = """
query Pods {
  myself {
    pods {
      id name desiredStatus costPerHr gpuCount
      machine { gpuDisplayName }
      runtime { uptimeInSeconds }
    }
  }
}
"""


def list_pods() -> list[dict]:
    data = _graphql(_LIST_QUERY)
    pods = (data.get("myself") or {}).get("pods") or []
    return [_normalize(p) for p in pods]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_runpod_client.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/runpod_client.py tests/test_runpod_client.py && git commit -m "feat: runpod list_pods with normalization"
```

---

## Task 2: RunPod client — start_pod & stop_pod

**Files:**
- Modify: `runpod-panel/app/runpod_client.py`
- Test: `runpod-panel/tests/test_runpod_client.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def test_start_and_stop_send_mutations(monkeypatch):
    sent = {}
    def fake_post(url, params=None, json=None, timeout=None):
        sent["query"] = json["query"]; sent["vars"] = json["variables"]
        key = "podResume" if "podResume" in json["query"] else "podStop"
        return _FakeResponse({"data": {key: {"id": "abc", "desiredStatus": "X"}}})
    monkeypatch.setenv("RUNPOD_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", fake_post)

    assert runpod_client.start_pod("abc")["id"] == "abc"
    assert "podResume" in sent["query"] and sent["vars"]["podId"] == "abc"
    assert runpod_client.stop_pod("abc")["id"] == "abc"
    assert "podStop" in sent["query"] and sent["vars"]["podId"] == "abc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runpod_client.py::test_start_and_stop_send_mutations -v`
Expected: FAIL (`AttributeError: start_pod`).

- [ ] **Step 3: Write minimal implementation (append to `runpod_client.py`)**

```python
_START_MUTATION = """
mutation Resume($podId: String!, $gpuCount: Int!) {
  podResume(input: {podId: $podId, gpuCount: $gpuCount}) { id desiredStatus }
}
"""

_STOP_MUTATION = """
mutation Stop($podId: String!) {
  podStop(input: {podId: $podId}) { id desiredStatus }
}
"""


def start_pod(pod_id: str, gpu_count: int = 1) -> dict:
    data = _graphql(_START_MUTATION, {"podId": pod_id, "gpuCount": gpu_count})
    return data["podResume"]


def stop_pod(pod_id: str) -> dict:
    data = _graphql(_STOP_MUTATION, {"podId": pod_id})
    return data["podStop"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_runpod_client.py -v`
Expected: PASS (3 tests).

> NOTE for the engineer: the GraphQL field names (`podResume`, `podStop`, `desiredStatus`, `costPerHr`, `gpuDisplayName`, `uptimeInSeconds`) match RunPod's current GraphQL schema. If a live call returns a schema error during deploy testing (Task 11), check RunPod's API docs and adjust only the query strings here — the tests mock the transport so they stay green.

- [ ] **Step 5: Commit**

```bash
git add app/runpod_client.py tests/test_runpod_client.py && git commit -m "feat: runpod start_pod/stop_pod mutations"
```

---

## Task 3: FastAPI app — auth gate + /healthz

**Files:**
- Create: `runpod-panel/app/main.py`
- Test: `runpod-panel/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from app import main, runpod_client


def _client(): return TestClient(main.app)


def test_healthz_ok(monkeypatch):
    monkeypatch.setattr(runpod_client, "list_pods", lambda: [])
    r = _client().get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_healthz_reports_upstream_failure(monkeypatch):
    def boom(): raise runpod_client.RunPodError("no key")
    monkeypatch.setattr(runpod_client, "list_pods", boom)
    r = _client().get("/healthz")
    assert r.status_code == 503 and r.json()["ok"] is False


def test_pods_requires_allowed_email(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED", {"me@x.com"})
    monkeypatch.setattr(runpod_client, "list_pods", lambda: [])
    c = _client()
    assert c.get("/api/pods").status_code == 403  # no header
    assert c.get("/api/pods", headers={"X-Auth-Request-Email": "evil@y.com"}).status_code == 403
    assert c.get("/api/pods", headers={"X-Auth-Request-Email": "me@x.com"}).status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL (`ModuleNotFoundError: app.main`).

- [ ] **Step 3: Write minimal implementation**

```python
# app/main.py
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, FileResponse
from app import runpod_client

ALLOWED = {e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RunPod Panel")


def require_user(request: Request) -> str:
    email = (request.headers.get("X-Auth-Request-Email") or "").lower()
    if not ALLOWED or email not in ALLOWED:
        raise HTTPException(status_code=403, detail="forbidden")
    return email


@app.get("/healthz")
def healthz():
    try:
        runpod_client.list_pods()
        return {"ok": True}
    except Exception:
        return JSONResponse(status_code=503, content={"ok": False, "error": "api_key_or_upstream"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py::test_healthz_ok tests/test_api.py::test_healthz_reports_upstream_failure -v`
Expected: PASS (2 tests). (The `test_pods_requires_allowed_email` test still fails — `/api/pods` not added yet; that's Task 4.)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api.py && git commit -m "feat: FastAPI app skeleton with auth gate and healthz"
```

---

## Task 4: FastAPI app — GET /api/pods

**Files:**
- Modify: `runpod-panel/app/main.py`

- [ ] **Step 1: Add the endpoint (implementation)**

Append to `app/main.py`:
```python
@app.get("/api/pods")
def api_pods(user: str = Depends(require_user)):
    try:
        return {"pods": runpod_client.list_pods()}
    except runpod_client.RunPodError:
        raise HTTPException(status_code=502, detail="Couldn't reach RunPod")
```

- [ ] **Step 2: Run the auth test (already written in Task 3) to verify it passes**

Run: `pytest tests/test_api.py::test_pods_requires_allowed_email -v`
Expected: PASS.

- [ ] **Step 3: Add a 502 test**

Append to `tests/test_api.py`:
```python
def test_pods_502_on_runpod_error(monkeypatch):
    monkeypatch.setattr(main, "ALLOWED", {"me@x.com"})
    def boom(): raise runpod_client.RunPodError("down")
    monkeypatch.setattr(runpod_client, "list_pods", boom)
    r = _client().get("/api/pods", headers={"X-Auth-Request-Email": "me@x.com"})
    assert r.status_code == 502
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api.py && git commit -m "feat: GET /api/pods endpoint"
```

---

## Task 5: FastAPI app — start/stop endpoints + audit log

**Files:**
- Modify: `runpod-panel/app/main.py`

- [ ] **Step 1: Write the failing test (append to `tests/test_api.py`)**

```python
def test_start_and_stop_call_client_and_audit(monkeypatch, capsys):
    monkeypatch.setattr(main, "ALLOWED", {"me@x.com"})
    calls = {}
    monkeypatch.setattr(runpod_client, "start_pod", lambda pid: calls.setdefault("start", pid) or {"id": pid})
    monkeypatch.setattr(runpod_client, "stop_pod", lambda pid: calls.setdefault("stop", pid) or {"id": pid})
    h = {"X-Auth-Request-Email": "me@x.com"}
    c = _client()
    assert c.post("/api/pods/abc/start", headers=h).status_code == 200
    assert c.post("/api/pods/abc/stop", headers=h).status_code == 200
    assert calls == {"start": "abc", "stop": "abc"}
    out = capsys.readouterr().out
    assert "AUDIT start pod=abc by=me@x.com" in out
    assert "AUDIT stop pod=abc by=me@x.com" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_api.py::test_start_and_stop_call_client_and_audit -v`
Expected: FAIL (404 — routes not defined).

- [ ] **Step 3: Add the endpoints (append to `app/main.py`)**

```python
@app.post("/api/pods/{pod_id}/start")
def api_start(pod_id: str, user: str = Depends(require_user)):
    try:
        result = runpod_client.start_pod(pod_id)
        print(f"AUDIT start pod={pod_id} by={user}", flush=True)
        return result
    except runpod_client.RunPodError:
        raise HTTPException(status_code=502, detail="start failed")


@app.post("/api/pods/{pod_id}/stop")
def api_stop(pod_id: str, user: str = Depends(require_user)):
    try:
        result = runpod_client.stop_pod(pod_id)
        print(f"AUDIT stop pod={pod_id} by={user}", flush=True)
        return result
    except runpod_client.RunPodError:
        raise HTTPException(status_code=502, detail="stop failed")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/ -v`
Expected: PASS (all tests across both files).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api.py && git commit -m "feat: start/stop endpoints with audit logging"
```

---

## Task 6: Serve the UI page

**Files:**
- Modify: `runpod-panel/app/main.py`
- Create: `runpod-panel/app/static/index.html`

- [ ] **Step 1: Add the index route (append to `app/main.py`)**

```python
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
```

- [ ] **Step 2: Create `app/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>My RunPods</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0f1115;color:#e6e6e6;margin:0;padding:24px}
  h1{font-size:20px} .row{display:flex;align-items:center;gap:12px;padding:12px;border:1px solid #272b33;border-radius:10px;margin:8px 0}
  .dot{width:10px;height:10px;border-radius:50%} .run{background:#37d67a}.stop{background:#555}
  .name{font-weight:600;min-width:160px}.muted{color:#9aa0a8}.spacer{flex:1}
  button{padding:8px 14px;border-radius:8px;border:0;cursor:pointer;font-weight:600}
  .start{background:#37d67a;color:#06210f}.stopbtn{background:#e0564b;color:#2a0b08}
  button[disabled]{opacity:.5;cursor:default}.warn{color:#f5b53d}
  .total{margin-top:16px;color:#9aa0a8}.err{background:#3a1d1d;color:#ffb4b4;padding:10px;border-radius:8px;display:none}
</style>
</head>
<body>
  <h1>My RunPods</h1>
  <div id="err" class="err"></div>
  <div id="list">Loading…</div>
  <div class="total" id="total"></div>
<script>
function fmtUptime(s){if(!s)return "—";const h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return h+"h "+m+"m";}
async function api(path,method){const r=await fetch(path,{method:method||"GET"});if(!r.ok)throw new Error(await r.text());return r.json();}
function showErr(msg){const e=document.getElementById("err");e.textContent=msg;e.style.display="block";}
function hideErr(){document.getElementById("err").style.display="none";}
async function act(id,action,name,cost){
  if(action==="start" && !confirm("Start "+name+" at $"+cost+"/hr?"))return;
  try{await api("/api/pods/"+id+"/"+action,"POST");setTimeout(load,1500);}catch(e){showErr(action+" failed");}
}
async function load(){
  try{
    const d=await api("/api/pods");hideErr();
    const list=document.getElementById("list");list.innerHTML="";let total=0;
    d.pods.forEach(p=>{
      const running=p.status==="RUNNING";if(running)total+=p.cost_per_hr;
      const warn=(running && (p.cost_per_hr>=10 || p.uptime_seconds>=6*3600))?' <span class="warn">⚠️</span>':'';
      const div=document.createElement("div");div.className="row";
      div.innerHTML=`<span class="dot ${running?'run':'stop'}"></span>
        <span class="name">${p.name}</span>
        <span class="muted">${p.gpu_count>1?p.gpu_count+"× ":""}${p.gpu}</span>
        <span class="muted">${running?'$'+p.cost_per_hr+'/hr':'—'}</span>
        <span class="muted">${running?fmtUptime(p.uptime_seconds):'—'}</span>${warn}
        <span class="spacer"></span>`;
      const btn=document.createElement("button");
      btn.textContent=running?"Stop":"Start";btn.className=running?"stopbtn":"start";
      btn.onclick=()=>act(p.id,running?"stop":"start",p.name,p.cost_per_hr);
      div.appendChild(btn);list.appendChild(div);
    });
    document.getElementById("total").textContent="Total running cost: ~$"+total.toFixed(2)+"/hr";
  }catch(e){showErr("Couldn't reach RunPod, retrying…");}
}
load();setInterval(load,15000);
</script>
</body>
</html>
```

- [ ] **Step 3: Manual smoke test**

Run:
```bash
RUNPOD_API_KEY=dummy ALLOWED_EMAILS=me@x.com . .venv/bin/activate; \
python -m uvicorn app.main:app --port 8000 &
sleep 2; curl -s localhost:8000/ | grep -q "My RunPods" && echo "UI OK"; kill %1
```
Expected: prints `UI OK`.

- [ ] **Step 4: Commit**

```bash
git add app/main.py app/static/index.html && git commit -m "feat: serve single-page UI"
```

---

## Task 7: Dockerfile

**Files:**
- Create: `runpod-panel/Dockerfile`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Build to verify**

Run: `cd runpod-panel && docker build -t runpod-panel:test .`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile && git commit -m "build: Dockerfile for runpod-panel"
```

---

## Task 8: docker-compose (panel + oauth2-proxy + Traefik labels)

**Files:**
- Create: `runpod-panel/docker-compose.yml`
- Create: `runpod-panel/.env.example`

> Assumes the existing Traefik network is external and named `traefik` (the engineer/user confirms the real network name via `docker network ls` during deploy and edits the one marked spot). Replace `<yourdomain>` and certresolver name to match the user's existing services.

- [ ] **Step 1: Create `.env.example`**

```
# --- RunPod ---
RUNPOD_API_KEY=rp_xxx_your_key
ALLOWED_EMAILS=you@gmail.com

# --- Google OAuth (create at console.cloud.google.com) ---
OAUTH2_PROXY_CLIENT_ID=xxxx.apps.googleusercontent.com
OAUTH2_PROXY_CLIENT_SECRET=xxxx
# generate: python3 -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
OAUTH2_PROXY_COOKIE_SECRET=xxxx

# --- Public host ---
PANEL_HOST=pods.yourdomain.com
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  runpod-panel:
    build: .
    container_name: runpod-panel
    restart: unless-stopped
    environment:
      RUNPOD_API_KEY: ${RUNPOD_API_KEY}
      ALLOWED_EMAILS: ${ALLOWED_EMAILS}
    networks: [traefik]
    # NOT publishing any port: only oauth2-proxy/Traefik reach it on the internal network.

  oauth2-proxy:
    image: quay.io/oauth2-proxy/oauth2-proxy:v7.6.0
    container_name: runpod-panel-auth
    restart: unless-stopped
    command:
      - --provider=google
      - --email-domain=*
      - --authenticated-emails-file=/etc/oauth2/emails
      - --upstream=http://runpod-panel:8000
      - --http-address=0.0.0.0:4180
      - --reverse-proxy=true
      - --cookie-secure=true
      - --set-xauthrequest=true       # passes X-Auth-Request-Email to the panel
      - --pass-access-token=false
    environment:
      OAUTH2_PROXY_CLIENT_ID: ${OAUTH2_PROXY_CLIENT_ID}
      OAUTH2_PROXY_CLIENT_SECRET: ${OAUTH2_PROXY_CLIENT_SECRET}
      OAUTH2_PROXY_COOKIE_SECRET: ${OAUTH2_PROXY_COOKIE_SECRET}
      OAUTH2_PROXY_REDIRECT_URL: https://${PANEL_HOST}/oauth2/callback
    volumes:
      - ./emails:/etc/oauth2/emails:ro
    networks: [traefik]
    labels:
      - traefik.enable=true
      - traefik.http.routers.runpodpanel.rule=Host(`${PANEL_HOST}`)
      - traefik.http.routers.runpodpanel.entrypoints=websecure
      - traefik.http.routers.runpodpanel.tls.certresolver=letsencrypt
      - traefik.http.services.runpodpanel.loadbalancer.server.port=4180

networks:
  traefik:
    external: true   # <-- set to the real existing Traefik network name (docker network ls)
```

- [ ] **Step 3: Create the allowlist file**

Run:
```bash
echo "you@gmail.com" > runpod-panel/emails   # the real allowed Google address(es), one per line
```

- [ ] **Step 4: Validate compose syntax**

Run: `cd runpod-panel && cp .env.example .env && docker compose config >/dev/null && echo "compose OK"`
Expected: prints `compose OK`.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example && git commit -m "build: compose with oauth2-proxy google sso + traefik labels"
```
(Do NOT commit the real `.env` or `emails` — add them to `.gitignore`.)

- [ ] **Step 6: Add `.gitignore`**

```
.venv/
.env
emails
__pycache__/
```
Commit: `git add .gitignore && git commit -m "chore: gitignore secrets and venv"`

---

## Task 9: DEPLOY.md (operator guide for the VPS web terminal)

**Files:**
- Create: `runpod-panel/DEPLOY.md`

- [ ] **Step 1: Write `DEPLOY.md`** with these exact sections:

```markdown
# Deploying the RunPod Panel (on the Hostinger VPS web terminal)

## Prerequisites (gather first)
1. **RunPod API key** — RunPod console → Settings → API Keys → create (read/write). Copy it.
2. **Google OAuth client** — https://console.cloud.google.com → APIs & Services → Credentials →
   Create OAuth client ID → type "Web application".
   - Authorized redirect URI: `https://pods.<yourdomain>/oauth2/callback`
   - Copy the Client ID + Client Secret.
3. **DNS:** add an A record `pods.<yourdomain>` → your VPS IP (so Traefik can get a cert).
4. Confirm your Traefik network name: `docker network ls` (look for the one your Open WebUI /
   LiteLLM use). Confirm your certresolver name in Traefik (e.g. `letsencrypt`).

## Install
1. Put this folder at `/docker/runpod-panel/` (upload, or `git clone`).
2. `cd /docker/runpod-panel`
3. `cp .env.example .env` and fill in every value. `chmod 600 .env`
4. Generate the cookie secret:
   `python3 -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`
   → paste into `OAUTH2_PROXY_COOKIE_SECRET`.
5. Put your Google address in the allowlist: `echo "you@gmail.com" > emails`
6. Edit `docker-compose.yml`: set the `networks: traefik: external` name + the
   `certresolver` label to match your existing Traefik setup.
7. `docker compose up -d --build`

## Verify
- `docker compose logs -f` → oauth2-proxy and panel start cleanly.
- Browse to `https://pods.<yourdomain>` → Google login appears → sign in with the allowed
  account → pod list loads.
- Sign in with a DIFFERENT Google account → must be REJECTED.
- View page source / network tab → the RunPod key must NOT appear anywhere.
- Start a stopped pod and stop a running one → confirm state flips in the RunPod console.

## Update later
`cd /docker/runpod-panel && git pull && docker compose up -d --build`

## Stop / remove
`docker compose down`
```

- [ ] **Step 2: Commit**

```bash
git add DEPLOY.md && git commit -m "docs: deployment guide for VPS web terminal"
```

---

## Task 10: Full local test pass

- [ ] **Step 1: Run the whole suite**

Run: `cd runpod-panel && . .venv/bin/activate && pytest -v`
Expected: ALL tests pass (runpod_client + api).

- [ ] **Step 2: Confirm read-only safety by inspection**

Grep the client for forbidden ops:
```bash
grep -Ei "podTerminate|create|delete|podRentInterruptable|podFindAndDeploy" app/runpod_client.py && echo "FOUND FORBIDDEN OP (remove it)" || echo "read/start/stop only — OK"
```
Expected: prints `read/start/stop only — OK`.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A && git commit -m "test: full suite green; verified no create/destroy ops" || echo "nothing to commit"
```

---

## Self-Review notes (coverage vs spec)
- Spec §3 endpoints → Tasks 3–6. Spec §4 security: API key server-side (Task 1 `_api_key` from env, never returned to client), Google SSO + allowlist (Task 8 oauth2-proxy + `emails`), network isolation (Task 8 — panel not published), defense-in-depth email re-check (Task 3 `require_user`), limited blast radius (Task 10 grep), confirm-on-start + audit (Tasks 5–6). Spec §5 error handling → Tasks 4/5 (502) + Task 6 UI banner + Task 3 healthz. Spec §6 testing → Task 9 DEPLOY verify + Task 10. Spec §7 ops → Tasks 7–9.
- No create/destroy code path exists anywhere (Task 10 asserts it).
