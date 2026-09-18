"""Dependency-free HTTP server for the Saarthi-MG teacher application."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(__file__))
    from api import router
else:
    from .api import router


FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))


class RequestHandler(SimpleHTTPRequestHandler):
    server_version = "SaarthiMG/2.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def log_message(self, format_string, *args):
        sys.stdout.write("[saarthi] " + (format_string % args) + "\n")

    @property
    def route(self) -> str:
        return unquote(urlparse(self.path).path).rstrip("/") or "/"

    def _json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _send_json(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self.route.startswith("/api"):
            return super().do_GET()
        try:
            if self.route == "/api/health":
                result = {"status": "ok"}
            elif self.route == "/api/bootstrap":
                result = router.get_bootstrap()
            elif self.route == "/api/metrics":
                result = router.get_metrics()
            elif self.route == "/api/analytics":
                result = router.get_analytics()
            elif self.route.startswith("/api/students/") and self.route.endswith("/mastery"):
                student_id = self.route.split("/")[3]
                result = router.get_student_mastery(student_id)
            else:
                return self._send_json(404, {"error": "route not found"})
            self._send_json(200, result)
        except KeyError as exc:
            self._send_json(404, {"error": str(exc).strip("'")})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._send_json(500, {"error": "unexpected server error"})

    def do_POST(self):
        if not self.route.startswith("/api"):
            return self._send_json(404, {"error": "route not found"})
        try:
            payload = self._json_body()
            parts = self.route.split("/")
            if self.route == "/api/reset-demo":
                result = router.post_reset_demo()
            elif self.route == "/api/classrooms":
                result = router.post_classrooms(payload)
            elif self.route == "/api/students":
                result = router.post_students(payload)
            elif self.route == "/api/attendance":
                result = router.post_attendance(payload)
            elif self.route == "/api/groups/generate":
                result = router.post_groups_generate(payload)
            elif self.route == "/api/groups/override":
                result = router.post_groups_override(payload)
            elif self.route == "/api/schedule/generate":
                result = router.post_schedule_generate(payload)
            elif self.route == "/api/activities/generate":
                result = router.post_activities_generate(payload)
            elif len(parts) == 5 and parts[2] == "activities" and parts[4] == "update":
                result = router.post_activity_update(parts[3], payload)
            elif len(parts) == 5 and parts[2] == "activities" and parts[4] == "regenerate":
                result = router.post_activity_regenerate(parts[3], payload)
            elif len(parts) == 5 and parts[2] == "plans" and parts[4] == "approval":
                result = router.post_plan_approval(parts[3], payload)
            elif self.route == "/api/exit-ticket":
                result = router.post_exit_ticket(payload)
            elif self.route == "/api/observations":
                result = router.post_observations(payload)
            elif self.route == "/api/mastery/update":
                result = router.post_mastery_update(payload)
            elif self.route == "/api/next-plan":
                result = router.post_next_plan(payload)
            else:
                return self._send_json(404, {"error": "route not found"})
            self._send_json(200, result)
        except KeyError as exc:
            self._send_json(404, {"error": str(exc).strip("'")})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            self._send_json(500, {"error": "unexpected server error"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Saarthi-MG prototype")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("SAARTHI_PORT", "8000")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    print(f"Saarthi-MG is ready at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
