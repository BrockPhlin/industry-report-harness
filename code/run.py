"""Start the local photovoltaic research workspace."""
import argparse
from pathlib import Path

from report_app.generator import read_config
from report_app.server import make_server
from report_app.service import Service
from report_app.store import Store

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="光伏产业研究工作台，本地运行")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", type=Path, default=ROOT / "runtime/app.sqlite3")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env",
                        help="本机模型配置文件，默认读取 code/.env")
    args = parser.parse_args()
    service = Service(Store(args.database), read_config(args.env_file))
    with make_server(service, port=args.port) as server:
        try:
            print(f"光伏研究工作台：http://127.0.0.1:{server.server_port}")
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
