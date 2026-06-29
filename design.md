# RunPod Control Panel — Design Spec

**Date:** 2026-06-29
**Status:** Approved design → ready for implementation plan

> 🔒 Identifiers redacted with `<...>` placeholders — each marks something the user has; only the value is hidden.
> `<yourdomain>` the panel's HTTPS host (e.g. `pods.example.com`) · `<allowed-email>` the Google account(s) allowed in · `<docker-dir>` the compose folder under `/docker/`.

---

## 1. Purpose & scope

A small self-hosted web panel to **see all RunPod pods and start/stop them with one click**, usable from **any browser**, with **security as the top priority**.

**In scope (chosen capabilities):**
- List pods + status (name, GPU, running/stopped)
- Start / Stop a pod (one click, with confirm on Start)
- Show cost ($/hr) & uptime, flag expensive/long-running pods

**Explicitly OUT of scope (for safety / limited blast radius):**
- Create or destroy pods
- Editing pod config, volumes, templates
- Multiple RunPod accounts (assume ONE account / one API key; revisit later if needed)

**Success criteria:**
- From any browser, after Google login, the user sees live pod status and can start/stop in one click.
- An unauthenticated visitor (or wrong Google account) is fully blocked.
- The RunPod API key never reaches the browser.

---

## 2. Architecture

```
   You (browser, anywhere)
      │  HTTPS (Traefik + Let's Encrypt — existing)
      ▼
   Traefik  ──route  <yourdomain>──►  oauth2-proxy  (Google SSO + email allowlist)
      │                                   │  only <allowed-email> passes
      │                                   ▼
      └──────────────────────────►  runpod-panel  (new container)
                                        │  holds RUNPOD_API_KEY (server-side only)
                                        │  scope: list · start · stop · cost
                                        ▼
                                     RunPod GraphQL API
```

**Three components:**
1. **`runpod-panel`** — new small stateless container. Serves the web page + 4 backend endpoints; calls the RunPod API with the secret key. Suggested stack: Python + FastAPI (single small service). No database.
2. **`oauth2-proxy`** — standard container doing Google OAuth login + email allowlist. Wired as Traefik forward-auth in front of the panel.
3. **Traefik** (existing) — one new router for `<yourdomain>` + the oauth2-proxy middleware.

**Deployment:** a `docker-compose` project under `<docker-dir>/runpod-panel/`, same pattern as Open WebUI / LiteLLM. `docker compose up -d`.

---

## 3. The app

**UI** — one auto-refreshing page, one row per pod:
```
My RunPods                                     signed in: <user> ▾
─────────────────────────────────────────────────────────────────
● runpod-qwen     A40 48GB    RUNNING   $0.45/hr  3h 12m   [Stop]
○ runpod-dolphin  A40 48GB    STOPPED      —        —      [Start]
● big-rig         8×B200      RUNNING   $44/hr    0h 18m ⚠️ [Stop]
─────────────────────────────────────────────────────────────────
Total running cost: ~$44.45/hr
```
- ⚠️ flags expensive / long-running pods (forgotten-pod guard).

**Backend endpoints (the ONLY things it can do):**
| Endpoint | Action |
|---|---|
| `GET /api/pods` | list pods: name, GPU, status, $/hr, uptime |
| `POST /api/pods/{id}/start` | resume a stopped pod |
| `POST /api/pods/{id}/stop` | stop a running pod |
| `GET /healthz` | health + API-key validity |

- Talks to the **RunPod GraphQL API** for exactly these operations. Stateless — reads live status each call, stores nothing.

---

## 4. Security model (layered)

1. **Front door — Google SSO:** `oauth2-proxy` enforces Google login + an **email allowlist** of only `<allowed-email>`. Random 32-byte cookie secret; encrypted session.
2. **API key isolation:** `RUNPOD_API_KEY` lives only in the panel container env (`<docker-dir>/runpod-panel/.env`, `chmod 600`). Never sent to the browser.
3. **Network isolation:** panel binds to the **internal Docker network only** — never a public port (respects the "Docker bypasses UFW" gotcha). Traefik (post-auth) is the only path in.
4. **Defense in depth:** panel re-verifies the `X-Auth-Request-Email` header from oauth2-proxy against its own allowlist.
5. **Limited blast radius:** key used for only 4 read/start/stop ops. No create/destroy. Worst case = toggling existing pods.
6. **Action safety + audit:** Start shows a confirm ("Start big-rig at $44/hr?"). Every start/stop logged with auth email + timestamp.
7. **Transport:** all HTTPS via existing Traefik + Let's Encrypt; internal hop stays on the private Docker network.

---

## 5. Error handling

- RunPod API down/slow → friendly banner ("Couldn't reach RunPod, retrying…"), keep last-known state, never leak raw errors.
- Pod in transitional state (starting/stopping) → spinner + disabled button until it settles (prevents double/conflicting commands).
- Invalid/expired API key → `/healthz` red + "API key problem — check server config" (no secrets shown).
- After Start/Stop → poll status until it flips to RUNNING/STOPPED (real confirmation).

---

## 6. Testing

1. **Auth wall:** signed out / wrong Google account → blocked by oauth2-proxy. (Primary test.)
2. **Key isolation:** page source + network tab → API key appears nowhere.
3. **Functionality:** start a stopped pod, stop a running one → verify state change in RunPod console.
4. **Read-only safety:** confirm no code path can create/destroy a pod.
5. **Health:** `/healthz` reflects API-key validity.

---

## 7. Ops / deployment

- `docker-compose` project under `<docker-dir>/runpod-panel/`; `docker compose up -d`; `restart: unless-stopped`.
- Secrets in `<docker-dir>/runpod-panel/.env` (`chmod 600`): `RUNPOD_API_KEY`, Google OAuth client id/secret, oauth2-proxy cookie secret, `ALLOWED_EMAILS`.
- One new Traefik router (`<yourdomain>`) + oauth2-proxy middleware (labels provided in implementation).
- Stateless → nothing to back up except `.env`.
- Logs (start/stop + auth email) via `docker logs`.
- **Note:** deployment is performed by the user on the Hostinger VPS via its web terminal (no external SSH). Implementation delivers the code + compose + a step-by-step deploy guide (mirrors the existing `self-hosted-ai/setup-guide.md` pattern).

---

## 8. Open items / prerequisites (user provides at deploy time)
- A Google OAuth client (id + secret) — created once in Google Cloud console (steps in deploy guide).
- A RunPod API key (read/start/stop) from RunPod settings.
- A DNS record `<yourdomain>` pointing at the VPS (for Traefik/Let's Encrypt).
- The exact `<allowed-email>` Google account(s) to allow.
