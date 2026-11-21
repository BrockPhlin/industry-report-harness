"""Exercise Pi's JSON mode and custom evidence tool against a loopback fixture."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
TOOL = "search_evidence"


class FixtureEndpoint(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        names = [tool["function"]["name"] for tool in payload.get("tools", [])]
        results = [message["content"] for message in payload["messages"] if message["role"] == "tool"]
        self.server.requests.append({"tools": names, "results": results})
        if not results:
            delta = {"tool_calls": [{"index": 0, "id": "pv_lookup", "type": "function",
                                    "function": {"name": TOOL, "arguments": '{"key":"pv-new-capacity"}'}}]}
            finish = "tool_calls"
        else:
            delta = {"content": "已收到带原始出处的光伏新增装机证据。"}
            finish = "stop"
        frames = [{"delta": {"role": "assistant", **delta}, "finish_reason": None, "index": 0},
                  {"delta": {}, "finish_reason": finish, "index": 0}]
        body = "".join(f"data: {json.dumps({'id': 'pv_probe', 'object': 'chat.completion.chunk', 'created': 0, 'model': 'pv-fixture', 'choices': [frame]})}\n\n"
                       for frame in frames).encode() + b"data: [DONE]\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def probe(pi):
    # Put the extension next to the installed node_modules so TypeBox is resolved.
    npm_root = Path(pi).resolve().parents[4]
    with TemporaryDirectory(dir=npm_root) as tmp, HTTPServer(("127.0.0.1", 0), FixtureEndpoint) as server:
        directory = Path(tmp)
        agent_dir = directory / "agent"
        agent_dir.mkdir()
        (agent_dir / "models.json").write_text(json.dumps({"providers": {"pv-local": {
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "api": "openai-completions", "apiKey": "fixture-only",
            "models": [{"id": "pv-fixture"}],
        }}}), encoding="utf-8")
        extension = directory / "pi_evidence.mjs"
        shutil.copyfile(Path(__file__).with_name("pi_evidence.mjs"), extension)
        env = {"PATH": os.environ["PATH"], "PI_CODING_AGENT_DIR": str(agent_dir),
               "G11_PYTHON": sys.executable, "G11_PV_CLI": str(ROOT / "code/pv_brief.py")}
        server.requests = []
        daemon = Thread(target=server.serve_forever, daemon=True)
        daemon.start()
        try:
            version = subprocess.check_output([pi, "--version"], cwd=directory, env=env, text=True).strip()
            result = subprocess.run([pi, "--offline", "--no-approve", "--no-session", "--no-mcp",
                                     "--no-builtin-tools", "--no-extensions", "--no-skills", "--no-context-files",
                                     "--extension", str(extension), "--provider", "pv-local", "--model", "pv-fixture",
                                     "--mode", "json", "-p", "查找全国光伏发电新增装机证据。"],
                                    cwd=directory, env=env, capture_output=True, text=True, timeout=25)
        finally:
            server.shutdown()
            daemon.join(timeout=3)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        calls = server.requests
        if (len(calls) != 2 or calls[0]["tools"] != [TOOL] or
                len(calls[1]["results"]) != 1 or
                not any(event.get("type") == "tool_execution_end" and not event.get("isError") for event in events) or
                not any(event.get("type") == "agent_end" for event in events)):
            raise RuntimeError(f"Pi 未完成工具调用：{calls}，CLI 错误：{result.stderr}")
        row = json.loads(calls[1]["results"][0])["pv-new-capacity"]
        if row["value"] != "2.78" or row["origin"]["id"] != "NEA":
            raise RuntimeError("Pi 工具回复与光伏证据不一致")
        print(json.dumps({
            "pi_version": version, "provider": "loopback fixture", "cli_mode": "json",
            "tool": TOOL, "request_count": len(calls), "tool_result_reentered": True,
            "events": [event["type"] for event in events], "tool_results": calls[1]["results"],
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: pi_probe.py <absolute path to pi npm binary>")
    probe(str(Path(sys.argv[1]).absolute()))
