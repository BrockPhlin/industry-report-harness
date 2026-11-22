"""Start the local research workspace, optionally serving a second loopback address."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from report_app.generator import read_config
from report_app.server import make_server
from report_app.service import Service
from report_app.store import Store

ROOT = Path(__file__).resolve().parent


def redirect_server(port, destination):
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path)
            suffix = path.path + ("?" + path.query if path.query else "")
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination}" + suffix)
            self.end_headers()

    return ThreadingHTTPServer(("127.0.0.1", port), Redirect)


def main():
    parser = argparse.ArgumentParser(description="光伏产业研究工作台，本地运行")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--alias-port", type=int, help="将另一旧地址转到同一服务，可选")
    parser.add_argument("--database", type=Path, default=ROOT / "runtime/app.sqlite3")
    args = parser.parse_args()
    service = Service(Store(args.database), read_config(ROOT / ".env"))
    with make_server(service, port=args.port) as server:
        alias = redirect_server(args.alias_port, server.server_port) if args.alias_port else None
        try:
            if alias:
                Thread(target=alias.serve_forever, daemon=True).start()
            print(f"光伏研究工作台：http://127.0.0.1:{server.server_port}")
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if alias:
                alias.shutdown()
                alias.server_close()


if __name__ == "__main__":
    main()
