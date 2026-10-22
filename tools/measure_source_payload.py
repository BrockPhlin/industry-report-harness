"""Compare serialized library payloads on constructed data, not runtime speed."""
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from report_app.service import Service
from report_app.store import Store


def main():
    # Temporary data never enters the team's real source library.
    with tempfile.TemporaryDirectory() as directory:
        service = Service(Store(Path(directory) / "measure.sqlite3"), {})
        for index in range(10):
            service.add_source({"title": f"构造资料{index}", "body": "测" * 50000})
        with closing(service.store.connect()) as connection:
            original = [dict(row) for row in connection.execute(
                "SELECT * FROM sources ORDER BY created_at, rowid")]
        summaries = service.store.list_sources()
        original_bytes = len(json.dumps(original, ensure_ascii=False).encode("utf-8"))
        summary_bytes = len(json.dumps(summaries, ensure_ascii=False).encode("utf-8"))
        print(json.dumps({
            "constructed_sources": 10,
            "body_characters_each": 50000,
            "original_json_bytes": original_bytes,
            "summary_json_bytes": summary_bytes,
            "payload_reduction_percent": round(100 * (1 - summary_bytes / original_bytes), 2),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
