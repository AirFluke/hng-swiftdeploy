#!/usr/bin/env python3
"""SwiftDeploy API Service - stable/canary mode HTTP server."""

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

# Chaos state
chaos_lock = threading.Lock()
chaos_state = {"mode": None, "duration": None, "rate": None}


def get_chaos():
    with chaos_lock:
        return dict(chaos_state)


def set_chaos(state):
    with chaos_lock:
        chaos_state.update(state)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging; nginx handles access logs
        pass

    def send_json(self, code, body, extra_headers=None):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Deployed-By", "swiftdeploy")
        if MODE == "canary":
            self.send_header("X-Mode", "canary")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        chaos = get_chaos()

        # Apply chaos if canary
        if MODE == "canary" and chaos["mode"] == "slow" and chaos["duration"]:
            time.sleep(chaos["duration"])
        if MODE == "canary" and chaos["mode"] == "error" and chaos["rate"]:
            if random.random() < chaos["rate"]:
                self.send_json(500, {"error": "chaos-induced error", "mode": chaos["mode"]})
                return

        if self.path == "/":
            self.send_json(200, {
                "message": f"Welcome to SwiftDeploy API",
                "mode": MODE,
                "version": APP_VERSION,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })

        elif self.path == "/healthz":
            uptime = round(time.time() - START_TIME, 2)
            self.send_json(200, {
                "status": "ok",
                "mode": MODE,
                "version": APP_VERSION,
                "uptime_seconds": uptime,
            })

        else:
            self.send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self):
        if self.path == "/chaos":
            if MODE != "canary":
                self.send_json(403, {"error": "chaos endpoint only available in canary mode"})
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "invalid JSON"})
                return

            mode = data.get("mode")
            if mode == "slow":
                set_chaos({"mode": "slow", "duration": data.get("duration", 2), "rate": None})
                self.send_json(200, {"status": "chaos activated", "mode": "slow", "duration": data.get("duration", 2)})
            elif mode == "error":
                set_chaos({"mode": "error", "duration": None, "rate": data.get("rate", 0.5)})
                self.send_json(200, {"status": "chaos activated", "mode": "error", "rate": data.get("rate", 0.5)})
            elif mode == "recover":
                set_chaos({"mode": None, "duration": None, "rate": None})
                self.send_json(200, {"status": "chaos cleared", "mode": "recover"})
            else:
                self.send_json(400, {"error": f"unknown chaos mode: {mode}"})
        else:
            self.send_json(404, {"error": "not found", "path": self.path})


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", APP_PORT), Handler)
    print(f"[swiftdeploy] Starting in {MODE} mode on port {APP_PORT} (v{APP_VERSION})", flush=True)
    server.serve_forever()
