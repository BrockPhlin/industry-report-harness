"""Small SQLite store. Each operation owns/closes its connection.

Sources are append-only. Reports persist source snapshots, so evidence remains
viewable even if a future version adds edits/deletes to the source library.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .errors import AppError


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, filename):
        self.filename = str(filename)
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    publisher TEXT NOT NULL, published_at TEXT NOT NULL,
                    url TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, mode TEXT NOT NULL,
                    markdown TEXT NOT NULL, sources_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    def connect(self):
        conn = sqlite3.connect(self.filename, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def add_source(self, data):
        row = dict(id=uuid4().hex, created_at=now(), **data)
        with closing(self.connect()) as conn, conn:
            conn.execute("INSERT INTO sources VALUES (:id,:title,:publisher,:published_at,:url,:body,:created_at)", row)
        return row

    def list_sources(self):
        """Return library metadata; load full bodies only for detail/generation."""
        with closing(self.connect()) as conn:
            return [dict(r) for r in conn.execute("""
                SELECT id, title, publisher, published_at, url, created_at,
                       length(body) AS body_length
                FROM sources ORDER BY created_at, rowid
            """)]

    def get_source(self, source_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise AppError("资料不存在", 404, "source_not_found")
        return dict(row)

    def add_report(self, topic, mode, markdown, sources, warnings):
        row = dict(id=uuid4().hex, topic=topic, mode=mode, markdown=markdown,
                   sources_json=json.dumps(sources, ensure_ascii=False),
                   warnings_json=json.dumps(warnings, ensure_ascii=False), created_at=now())
        with closing(self.connect()) as conn, conn:
            conn.execute("INSERT INTO reports VALUES (:id,:topic,:mode,:markdown,:sources_json,:warnings_json,:created_at)", row)
        return self.get_report(row["id"])

    def get_report(self, report_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise AppError("报告不存在", 404, "report_not_found")
        result = dict(row)
        result["sources"] = json.loads(result.pop("sources_json"))
        result["warnings"] = json.loads(result.pop("warnings_json"))
        return result

    def list_reports(self):
        with closing(self.connect()) as conn:
            return [dict(r) for r in conn.execute("SELECT id,topic,mode,created_at FROM reports ORDER BY created_at DESC, rowid DESC")]
