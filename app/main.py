#!/usr/bin/env python3
"""SwiftDeploy API Service - stable/canary mode HTTP server with Prometheus metrics."""

import os
import time
import random
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

MODE = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "3000"))
START_TIME = time.time()

# ─── Chaos State ──────────────────────────────────────────────────────────────
chaos_lock = threading.Lock()
chaos_state = {"mode": None, "duration": None, "rate": None}

def get_chaos():
    with chaos_lock:
        return dict(chaos_state)

def set_chaos(state):
    with chaos_lock:
        chaos_state.update(state)

# ─── Metrics State ────────────────────────────────────────────────────────────
metrics_lock = threading.Lock()
request_counts = {}   # {(method, path, status_code): count}
HISTOGRAM_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
request_durations = {}  # {path: {buckets, sum, count}}

def record_request(method, path, status_code, duration_seconds):
    with metrics_lock:
        key = (method, path, str(status_code))
        request_counts[key] = request_counts.get(key, 0) + 1
        if path not in request_durations:
            request_durations[path] = {
                "buckets": {str(le): 0 for le in HISTOGRAM_BUCKETS},
                "sum": 0.0,
                "count": 0,
            }
        hist = request_durations[path]
        hist["sum"] += duration_seconds
        hist["count"] += 1
        for le in HISTOGRAM_BUCKETS:
            if duration_seconds <= le:
                hist["buckets"][str(le)] += 1

def build_metrics_output():
    lines = []
    chaos = get_chaos()
    uptime = time.time() - START_TIME

    with metrics_lock:
        counts_snapshot = dict(request_counts)
        durations_snapshot = {k: {
            "buckets": dict(v["buckets"]),
            "sum": v["sum"],
            "count": v["count"]
        } for k, v in request_durations.items()}

    lines.append("# HELP http_requests_total Total number of HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    for (method, path, status_code), count in sorted(counts_snapshot.items()):
        lines.append(f'http_requests_total{{method="{method}",path="{path}",status_code="{status_code}"}} {count}')

    lines.append("# HELP http_request_duration_seconds HTTP request latency in seconds")
    lines.append("# TYPE http_request_duration_seconds histogram")
    for path, hist in sorted(durations_snapshot.items()):
        for le in HISTOGRAM_BUCKETS:
            bucket_count = hist["buckets"].get(str(le), 0)
            lines.append(f'http_request_duration_seconds_bucket{{path="{path}",le="{le}"}} {bucket_count}')
        lines.append(f'http_request_duration_seconds_bucket{{path="{path}",le="+Inf"}} {hist["count"]}')
        lines.append(f'http_request_duration_seconds_sum{{path="{path}"}} {hist["sum"]:.6f}')
        lines.append(f'http_request_duration_seconds_count{{path="{path}"}} {hist["count"]}')

    lines.append("# HELP app_uptime_seconds Seconds since the app started")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {uptime:.2f}")

    lines.append("# HELP app_mode Current deployment mode (0=stable, 1=canary)")
    lines.append("# TYPE app_mode gauge")
    lines.append(f"app_mode {1 if MODE == 'canary' else 0}")

    lines.append("# HELP chaos_active Current chaos state (0=none, 1=slow, 2=error)")
    lines.append("# TYPE chaos_active gauge")
    chaos_val = {"slow": 1, "error": 2}.get(chaos.get("mode") or "", 0)
    lines.append(f"chaos_active {chaos_val}")

    return "\n".join(lines) + "\n"

# ─── Handler ──────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, code, body):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Deployed-By", "swiftdeploy")
        if MODE == "canary":
            self.send_header("X-Mode", "canary")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        start = time.time()
        path = self.path.split("?")[0]
        status = self._handle_get()
        record_request("GET", path, status, time.time() - start)

    def do_POST(self):
        start = time.time()
        path = self.path.split("?")[0]
        status = self._handle_post()
        record_request("POST", path, status, time.time() - start)

    def _handle_get(self):
        chaos = get_chaos()
        if MODE == "canary" and chaos["mode"] == "slow" and chaos["duration"]:
            time.sleep(chaos["duration"])
        if MODE == "canary" and chaos["mode"] == "error" and chaos["rate"]:
            if random.random() < chaos["rate"]:
                self.send_json(500, {"error": "chaos-induced error", "mode": chaos["mode"]})
                return 500

        if self.path == "/":
            self.send_json(200, {
                "message": "Welcome to SwiftDeploy API",
                "mode": MODE,
                "version": APP_VERSION,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            return 200
        elif self.path == "/healthz":
            self.send_json(200, {
                "status": "ok",
                "mode": MODE,
                "version": APP_VERSION,
                "uptime_seconds": round(time.time() - START_TIME, 2),
            })
            return 200
        elif self.path == "/metrics":
            output = build_metrics_output().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
            return 200
        else:
            self.send_json(404, {"error": "not found", "path": self.path})
            return 404

    def _handle_post(self):
        if self.path == "/chaos":
            if MODE != "canary":
                self.send_json(403, {"error": "chaos endpoint only available in canary mode"})
                return 403
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self.send_json(400, {"error": "invalid JSON"})
                return 400
            mode = data.get("mode")
            if mode == "slow":
                set_chaos({"mode": "slow", "duration": data.get("duration", 2), "rate": None})
                self.send_json(200, {"status": "chaos activated", "mode": "slow", "duration": data.get("duration", 2)})
                return 200
            elif mode == "error":
                set_chaos({"mode": "error", "duration": None, "rate": data.get("rate", 0.5)})
                self.send_json(200, {"status": "chaos activated", "mode": "error", "rate": data.get("rate", 0.5)})
                return 200
            elif mode == "recover":
                set_chaos({"mode": None, "duration": None, "rate": None})
                self.send_json(200, {"status": "chaos cleared", "mode": "recover"})
                return 200
            else:
                self.send_json(400, {"error": f"unknown chaos mode: {mode}"})
                return 400
        else:
            self.send_json(404, {"error": "not found", "path": self.path})
            return 404

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", APP_PORT), Handler)
    print(f"[swiftdeploy] Starting in {MODE} mode on port {APP_PORT} (v{APP_VERSION})", flush=True)
    server.serve_forever()
