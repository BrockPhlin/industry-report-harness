"""Check DeepSeek Harness SDK → read-only MCP → tool result on loopback.

Only deterministic fixture responses are used. The isolated SDK subprocess
receives a synthetic credential and a localhost endpoint.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
TOOL = "mcp__pv__search_evidence"


def json_line(value):
    return json.dumps(value, ensure_ascii=False)


def mcp():
    sys.path.insert(0, str(ROOT / "code"))
    from report_app.pv_evidence import load_inputs, search_evidence

    _, sources, facts = load_inputs()
    for raw in sys.stdin:
        request = json.loads(raw)
        if "id" not in request:
            continue
        params = request.get("params", {})
        method = request["method"]
        reply = {"jsonrpc": "2.0", "id": request["id"]}
        if method == "initialize":
            reply["result"] = {
                "protocolVersion": params["protocolVersion"], "capabilities": {"tools": {}},
                "serverInfo": {"name": "pv-probe", "version": "1"},
            }
        elif method == "tools/list":
            reply["result"] = {"tools": [{
                "name": "search_evidence", "description": "按编号查询固定样例指标。",
                "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}},
                                "required": ["key"], "additionalProperties": False},
            }]}
        elif method == "tools/call" and params["name"] == "search_evidence":
            key = params["arguments"]["key"]
            result = search_evidence([key], sources, facts).get(key)
            reply["result"] = {"content": [{"type": "text", "text": json_line(result)}]}
        else:
            reply["error"] = {"code": -32601, "message": "Method not found"}
        print(json_line(reply), flush=True)


class FixtureEndpoint(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        names = [tool["name"] for tool in request.get("tools", []) if "name" in tool]
        tool_results = [
            block for message in request["messages"] for block in message["content"]
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        self.server.observations.append({"path": self.path, "tools": names, "tool_results": tool_results})
        if not tool_results:
            block = {"type": "tool_use", "id": "toolu_pv", "name": TOOL, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": '{"key":"pv-new-capacity"}'}
            reason = "tool_use"
        else:
            block = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": "已收到并读取光伏新增装机证据。"}
            reason = "end_turn"
        usage = {"input_tokens": 10, "output_tokens": 1}
        events = [
            {"type": "message_start", "message": {
                "id": "msg_pv", "type": "message", "role": "assistant", "content": [],
                "model": request["model"], "stop_reason": None, "stop_sequence": None, "usage": usage}},
            {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": reason, "stop_sequence": None}, "usage": usage},
            {"type": "message_stop"},
        ]
        body = "".join(f"event: {event['type']}\ndata: {json_line(event)}\n\n" for event in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def probe(dsh):
    with TemporaryDirectory() as tmp, HTTPServer(("127.0.0.1", 0), FixtureEndpoint) as server:
        directory = Path(tmp)
        patch = directory / "probe.json"
        disabled = ["persistent-bash", "persistent-pwsh", "tool-fs", "tool-working-directory", "llm-retry"]
        patch.write_text(json_line([*({"id": item, "disabled": True} for item in disabled),
                                   {"insert": [{"id": "mcp-pv", "name": "@deepseek-ai/dsh-mcp-client",
                                       "config": {"serverName": "pv", "transport": "stdio", "command": sys.executable,
                                                  "args": [str(Path(__file__).resolve()), "--mcp"],
                                                  "startupTimeoutMs": 5000}}]}]), encoding="utf-8")
        server.observations = []
        daemon = Thread(target=server.serve_forever, daemon=True)
        daemon.start()
        env = {"PATH": os.environ["PATH"], "DSH_HOME": str(directory / "harness-home"),
               "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{server.server_port}",
               "DEEPSEEK_API_KEY": "fixture-only"}
        log_path = directory / "stderr.txt"
        version = subprocess.check_output([dsh, "--version"], text=True, cwd=directory, env=env).strip()
        with log_path.open("w+", encoding="utf-8") as log, subprocess.Popen(
            [dsh, "--profile", "sdk-minimal", "--patch", str(patch)], cwd=directory, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8",
        ) as process:
            output = Queue()

            def read_events():
                for line in process.stdout:
                    output.put(json.loads(line))
                output.put(None)

            Thread(target=read_events, daemon=True).start()
            events = []

            def rpc(number, method, params=None):
                request = {"jsonrpc": "2.0", "id": number, "method": method}
                if params is not None:
                    request["params"] = params
                process.stdin.write(json_line(request) + "\n")
                process.stdin.flush()
                while True:
                    reply = output.get(timeout=15)
                    if reply is None:
                        raise RuntimeError("SDK exited")
                    if reply.get("id") == number:
                        if "error" in reply:
                            raise RuntimeError(reply["error"])
                        return reply.get("result")
                    events.append(reply)

            try:
                identity = rpc(1, "initialize", {"cwd": tmp, "provider": "deepseek-official",
                                                "model": "deepseek-v4-flash", "maxTokens": 512})
                rpc(2, "session/prompt", {"sessionId": "pv-probe", "contentBlocks": [
                    {"type": "text", "text": "查找全国光伏发电新增装机证据。"}]})
                rpc(3, "session/wait", {"sessionId": "pv-probe"})
                rpc(4, "shutdown")
                process.wait(timeout=8)
            except Exception:
                process.kill()
                process.wait()
                log.seek(0)
                sys.stderr.write(log.read())
                raise
            finally:
                server.shutdown()
                daemon.join(timeout=3)

        timeline = server.observations
        allowed = {TOOL, "list_mcp_resource_templates", "list_mcp_resources", "read_mcp_resource"}
        if (len(timeline) != 2 or TOOL not in timeline[0]["tools"] or
                not set(timeline[0]["tools"]) <= allowed or
                len(timeline[1]["tool_results"]) != 1):
            raise RuntimeError(f"SDK 工具结果未回到模型端点: {timeline}")
        result = timeline[1]["tool_results"][0]
        row = json.loads(result["content"][0]["text"])
        if (result["is_error"] or row["id"] != "pv-new-capacity" or row["value"] != "2.78"
                or row["origin"]["id"] != "NEA"):
            raise RuntimeError("SDK 工具回复与光伏证据不一致")
        print(json.dumps({
            "harness_version": version, "provider": "loopback fixture",
            "server_identity": identity["serverInfo"]["name"],
            "tool": TOOL, "request_count": len(timeline),
            "tool_result_reentered": True,
            "tool_results": timeline[1]["tool_results"],
            "session_event_count": sum(event.get("method") == "session.event" for event in events),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: dsh_probe.py <absolute path to dsh>")
    if sys.argv[1] == "--mcp":
        mcp()
    else:
        probe(str(Path(sys.argv[1]).resolve()))
