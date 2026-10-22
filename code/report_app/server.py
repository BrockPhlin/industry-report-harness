"""Local-only baseline HTTP service with static allowlist and bounded JSON."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from .errors import AppError

WEB = Path(__file__).resolve().parents[1] / "web"


def make_server(service, host="127.0.0.1", port=8000):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Log only status line, not request body or provider configuration.
            super().log_message(fmt, *args)

        def respond(self, status, data, kind="application/json; charset=utf-8", filename=None):
            body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

        def handle_request(self, method):
            try:
                # A cross-origin browser request must not create model calls.
                if method == "POST" and self.headers.get("Sec-Fetch-Site") == "cross-site":
                    raise AppError("拒绝跨站写请求", 403, "cross_site_request")
                origin = self.headers.get("Origin")
                expected = f"http://{self.headers.get('Host', '')}"
                if method == "POST" and origin and origin != expected:
                    raise AppError("请求来源与本地服务不一致", 403, "origin_mismatch")
                path = urlsplit(self.path).path
                if method == "GET":
                    if path == "/api/health":
                        return self.respond(200, {"status": "ok", "stage": "baseline", "harness": False})
                    if path == "/api/sources":
                        return self.respond(200, service.store.list_sources())
                    if path.startswith("/api/sources/"):
                        parts = path.split("/")
                        if len(parts) != 4 or not parts[3]:
                            raise AppError("接口不存在", 404, "not_found")
                        return self.respond(200, service.store.get_source(parts[3]))
                    if path == "/api/reports":
                        return self.respond(200, service.store.list_reports())
                    if path.startswith("/api/reports/"):
                        parts = path.strip("/").split("/")
                        if len(parts) not in {3, 4} or (len(parts) == 4 and parts[3] != "download"):
                            raise AppError("接口不存在", 404)
                        report = service.store.get_report(parts[2])
                        if len(parts) == 4:
                            return self.respond(200, report["markdown"].encode(), "text/markdown; charset=utf-8", f"report-{report['id']}.md")
                        return self.respond(200, report)
                    static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
                    if path in static:
                        name, kind = static[path]
                        return self.respond(200, (WEB / name).read_bytes(), kind + "; charset=utf-8")
                    raise AppError("页面或接口不存在", 404, "not_found")
                if path not in {"/api/sources", "/api/reports"}:
                    raise AppError("接口不存在", 404, "not_found")
                if self.headers.get_content_type() != "application/json":
                    raise AppError("请求须为application/json", 415)
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise AppError("Content-Length无效") from None
                if not 0 < length <= 1_000_000:
                    raise AppError("请求体为空或超过1MB", 413)
                self.connection.settimeout(10)
                try:
                    data = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError, TimeoutError):
                    raise AppError("请求不是完整有效的UTF-8 JSON") from None
                if not isinstance(data, dict):
                    raise AppError("请求JSON必须为对象")
                result = service.add_source(data) if path == "/api/sources" else service.generate(data)
                self.respond(201, result)
            except AppError as exc:
                self.respond(exc.status, {"error": {"code": exc.code, "message": str(exc)}})
            except sqlite3.Error:
                self.respond(500, {"error": {"code": "storage_error", "message": "本地存储失败，请检查磁盘、权限或锁占用"}})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.respond(500, {"error": {"code": "internal_error", "message": "内部处理失败，请在本地检查代码与运行环境"}})

    # Reuse helps local reruns, but no authentication or remote deployment here.
    ThreadingHTTPServer.daemon_threads = True
    return ThreadingHTTPServer((host, port), Handler)
