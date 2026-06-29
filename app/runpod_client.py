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
