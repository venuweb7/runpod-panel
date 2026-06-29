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


@app.get("/api/pods")
def api_pods(user: str = Depends(require_user)):
    try:
        return {"pods": runpod_client.list_pods()}
    except runpod_client.RunPodError:
        raise HTTPException(status_code=502, detail="Couldn't reach RunPod")


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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
