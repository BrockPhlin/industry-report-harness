"""Run from any directory: python code/run.py --port 8000."""
import argparse
from pathlib import Path

from report_app.generator import read_config
from report_app.server import make_server
from report_app.service import Service
from report_app.store import Store

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="第11组产业报告基线，本地运行")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", type=Path, default=ROOT / "runtime/app.sqlite3")
    args = parser.parse_args()
    service = Service(Store(args.database), read_config(ROOT / ".env"))
    server = make_server(service, port=args.port)
    print(f"第11组基线：http://127.0.0.1:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
