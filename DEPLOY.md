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
