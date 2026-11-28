"""Open connections to the local research database."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, filename):
        self.filename = str(filename)
        Path(filename).parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        conn = sqlite3.connect(self.filename, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
