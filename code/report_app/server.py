"""Local research HTTP service with an explicit route and file allowlist."""
import csv
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit

from .errors import AppError
from .research import Research

WEB = Path(__file__).resolve().parents[1] / "web"


def observations_csv(rows):
    stream = StringIO()
    columns = ("region","year","metric","value","unit","publisher","url","fetched","digest")
    writer = csv.writer(stream,lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        fields = []
        for column in columns:
            value = row[column]
            is_number = column=="value" and isinstance(value,str) and re.fullmatch(r"[+-]?\d+(?:\.\d+)?",value)
            if isinstance(value,str) and not is_number and re.match(r"^\s*[=+@-]",value):
                value = "'"+value
            fields.append(value)
        writer.writerow(fields)
    return stream.getvalue().encode("utf-8-sig")


def export_markdown(markdown):
    # Older local drafts stored blank lines between table rows.
    return re.sub(r"(?m)^(\|[^\n]*\|)\n\n(?=\|)",r"\1\n",markdown).encode()


def make_server(service, host="127.0.0.1", port=8000):
    research = Research(service)

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
                task = re.fullmatch(r"/api/research/([a-f0-9]{32})(?:/(approve|pdf|ask|retry|plan|write|edit|scope|markdown|evidence\.json))?", path)
                if method == "GET":
                    if path in {"/api/research/observations", "/api/research/observations.csv"}:
                        params = parse_qs(urlsplit(self.path).query)
                        try:
                            start = int(params.get("start",["2000"])[0])
                            end = int(params.get("end",["2100"])[0])
                        except ValueError:
                            raise AppError("年份格式无效") from None
                        rows = research.library.browse(params.get("region",["China"])[0],start,end,
                            metric=params.get("metric",[""])[0],publisher=params.get("publisher",[""])[0])
                        if path.endswith(".csv"):
                            return self.respond(200,observations_csv(rows),"text/csv; charset=utf-8","pv-observations.csv")
                        return self.respond(200,rows)
                    if path == "/api/research/library":
                        return self.respond(200, research.library.summary())
                    if path == "/api/research/settings":
                        return self.respond(200, research.settings())
                    if path == "/api/research":
                        return self.respond(200, research.rows())
                    if task and task[2] in (None, "pdf", "markdown", "evidence.json"):
                        row = research.task(task[1])
                        if task[2] == "evidence.json":
                            if row["status"] != "ready" or "evidence" not in row:
                                raise AppError("联网报告草稿完成后可以导出证据",409)
                            fields = ("id","question","revision","length","outline","approved","evidence","retrieval","operations")
                            bundle = {field:row[field] for field in fields if field in row}
                            bundle["markdown_sha256"] = sha256(export_markdown(row["markdown"])).hexdigest()
                            body = json.dumps(bundle,ensure_ascii=False,indent=2)+"\n"
                            return self.respond(200,body.encode(),"application/json; charset=utf-8","pv-evidence.json")
                        if task[2] == "markdown":
                            if row["status"] != "ready":
                                raise AppError("草稿尚未完成", 409)
                            return self.respond(200, export_markdown(row["markdown"]), "text/markdown; charset=utf-8", "solar-report.md")
                        if task[2] == "pdf":
                            if not row.get("approved"):
                                raise AppError("核对草稿并确认后才可下载", 409)
                            return self.respond(200, (research.root / task[1] / "reviewed/brief.pdf").read_bytes(),
                                                "application/pdf", "pv-brief.pdf")
                        return self.respond(200, row)
                    if path == "/api/health":
                        return self.respond(200, {"status": "ok", "stage": "research", "harness": True})
                    static = {"/": ("research.html", "text/html"), "/research.js": ("research.js", "text/javascript"),
                              "/research.css": ("research.css", "text/css")}
                    if path in static:
                        name, kind = static[path]
                        return self.respond(200, (WEB / name).read_bytes(), kind + "; charset=utf-8")
                    raise AppError("页面或接口不存在", 404, "not_found")
                if path != "/api/research" and not (task and task[2] in ("approve", "ask", "retry", "plan", "write", "edit", "scope")):
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
                if path == "/api/research":
                    return self.respond(202, research.start(data))
                if task[2] == "scope":
                    return self.respond(200, research.revise_scope(task[1], data))
                if task[2] == "edit":
                    return self.respond(200, research.edit(task[1], data))
                if task[2] == "plan":
                    return self.respond(200, research.plan_turn(task[1], data))
                if task[2] == "write":
                    return self.respond(202, research.begin(task[1]))
                if task[2] == "approve":
                    if data.get("confirm") is not True:
                        raise AppError("请先确认已核对草稿")
                    return self.respond(200, research.approve(task[1]))
                if task[2] == "ask":
                    return self.respond(200, research.ask(task[1], data))
                research.launch(task[1])
                return self.respond(202, research.task(task[1]))
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
