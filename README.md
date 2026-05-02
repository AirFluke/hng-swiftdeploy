# SwiftDeploy

> Declarative infrastructure manager — the manifest is the single source of truth.

SwiftDeploy reads `manifest.yaml` and generates your entire stack configuration. No handwritten Nginx configs, no manual Docker Compose files. Edit the manifest, run the CLI, done.

---

## Architecture

```
manifest.yaml
     │
     ▼
swiftdeploy (CLI)
     │
     ├── templates/nginx.conf.tmpl  ──►  nginx.conf
     └── templates/docker-compose.yml.tmpl  ──►  docker-compose.yml
                                                        │
                                          ┌─────────────┴─────────────┐
                                          │                           │
                                    [nginx:8080]              [app:3000 (internal)]
                                          │                           │
                                          └──── reverse proxy ────────┘
```

All external traffic enters through Nginx on port `8080`. The app container is never exposed directly.

---

## Prerequisites

- Docker + Docker Compose v2
- Python 3.8+
- `pyyaml` (auto-installed by the CLI if missing)

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/swiftdeploy
cd swiftdeploy
```

### 2. Build the Docker image

```bash
docker build -t swift-deploy-1-node:latest .
```

### 3. Deploy

```bash
./swiftdeploy deploy
```

That's it. Your stack is live at `http://localhost:8080`.

---

## Subcommand Reference

### `init`

Parses `manifest.yaml` and generates `nginx.conf` and `docker-compose.yml` from templates.

```bash
./swiftdeploy init
```

The grader will delete generated files and re-run this — everything regenerates correctly from the manifest.

---

### `validate`

Runs 5 pre-flight checks. Exits non-zero on any failure.

```bash
./swiftdeploy validate
```

Checks:
1. `manifest.yaml` exists and is valid YAML
2. All required fields are present and non-empty
3. The Docker image referenced in the manifest exists locally
4. The Nginx port is not already bound on the host
5. The generated `nginx.conf` is syntactically valid (via `nginx -t`)

Example output:
```
──────────────────────────────────────────────────
  swiftdeploy validate
──────────────────────────────────────────────────

[1/5] manifest.yaml exists and is valid YAML
  ✔ manifest.yaml found and parsed successfully

[2/5] Required fields are present and non-empty
  ✔ services.image = swift-deploy-1-node:latest
  ✔ services.port = 3000
  ...

ALL CHECKS PASSED ✔
```

---

### `deploy`

Runs `init`, brings up the full stack, and blocks until `/healthz` returns `ok` or 60 seconds elapse.

```bash
./swiftdeploy deploy
```

---

### `promote`

Switches the deployment mode between `stable` and `canary` with a rolling restart of the app container only.

```bash
./swiftdeploy promote canary
./swiftdeploy promote stable
```

What it does:
1. Updates `mode` in `manifest.yaml` in-place
2. Regenerates `docker-compose.yml` with the new `MODE` env var
3. Restarts the `app` container only (nginx stays up)
4. Confirms the new mode by polling `/healthz`

---

### `teardown`

Stops and removes all containers, networks, and volumes.

```bash
./swiftdeploy teardown

# Also delete generated config files:
./swiftdeploy teardown --clean
```

---

## API Endpoints

| Method | Path      | Description                                      |
|--------|-----------|--------------------------------------------------|
| GET    | `/`       | Welcome message with mode, version, timestamp    |
| GET    | `/healthz`| Liveness check — returns status and uptime (s)   |
| POST   | `/chaos`  | Simulate degraded behaviour (canary mode only)   |

### Chaos Modes (canary only)

```bash
# Slow: sleep N seconds before responding
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "slow", "duration": 3}'

# Error: return 500 on ~50% of requests
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "error", "rate": 0.5}'

# Recover: cancel active chaos
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "recover"}'
```

Canary mode adds `X-Mode: canary` to every response. Nginx forwards this header downstream.

---

## Nginx Access Log Format

```
$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
```

Example:
```
2026-05-01T14:23:01+00:00 | 200 | 0.002s | 172.18.0.3:3000 | GET / HTTP/1.1
```

---

## Manifest Reference

```yaml
services:
  image: swift-deploy-1-node:latest   # Docker image to run
  port: 3000                          # Internal app port
  mode: stable                        # stable | canary
  version: "1.0.0"                    # Injected as APP_VERSION
  restart_policy: unless-stopped      # Docker restart policy
  log_volume: swiftdeploy-logs        # Named volume for logs

nginx:
  image: nginx:latest
  port: 8080                          # Host-facing port
  proxy_timeout: 30                   # Proxy timeout in seconds

network:
  name: swiftdeploy-net
  driver_type: bridge

contact: "ops@swiftdeploy.local"     # Used in error response bodies
```

---

## Security

- App container runs as non-root user (`appuser`)
- All Linux capabilities dropped (`cap_drop: ALL`), only `NET_BIND_SERVICE` re-added
- Service port (`3000`) is never exposed to the host — only Nginx is
- Images use Alpine base, keeping size well under 300MB

---

## Project Structure

```
swiftdeploy/
├── manifest.yaml               # ← Edit only this
├── swiftdeploy                 # CLI executable
├── Dockerfile                  # App image definition
├── app/
│   └── main.py                 # Python HTTP service
├── templates/
│   ├── nginx.conf.tmpl         # Nginx template
│   └── docker-compose.yml.tmpl # Compose template
├── nginx.conf                  # Generated by init (gitignored)
├── docker-compose.yml          # Generated by init (gitignored)
└── README.md
```

---

## Author

Built for HNG DevOps Track — Stage 4A (SwiftDeploy)
