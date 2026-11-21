"""Save completed chapters independently of the final report directory."""
from contextlib import closing, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from .errors import AppError


def input_fingerprint(template, sources, facts, mode, model_route):
    # Preserve order because it affects fixture queries and displayed sources.
    # The model route includes the endpoint and model name, never the key.
    if all(len(rows) == 1 for rows in facts.values()):
        # A single claim per metric still uses the midterm checkpoint format.
        inputs = [2, template, sources, {key: rows[0] for key, rows in facts.items()}, mode, model_route]
    else:
        inputs = [3, template, sources, facts, mode, model_route]
    return sha256(json.dumps(inputs, ensure_ascii=False).encode("utf-8")).hexdigest()


class RunCheckpoint:
    def __init__(self, output):
        self.path = output.with_name(f".{output.name}.pv-checkpoint")
        self.record = self.path / "completed.json"

    @contextmanager
    def open(self, fingerprint, resume):
        if resume:
            if not self.path.is_dir():
                raise AppError("找不到此任务的检查点，请先开始生成")
        else:
            try:
                self.path.mkdir()
            except FileExistsError:
                raise AppError("此任务已有检查点，请使用 --resume 继续或换新目录") from None

        # Hold a transaction on a separate lock database. Section JSON is
        # published independently, so a crash releases the lock and keeps progress.
        with closing(sqlite3.connect(self.path / "lock.sqlite3", timeout=0)) as lock:
            try:
                lock.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                raise AppError("此任务正在另一个进程中运行") from None
            self.fingerprint = fingerprint
            self.completed = []
            self.in_progress = False
            self.interruptions = []
            if resume:
                try:
                    data = json.loads(self.record.read_text(encoding="utf-8"))
                    previous = data["fingerprint"]
                    self.completed = data["completed"]
                    self.in_progress = data["in_progress"]
                    self.interruptions = data["interruptions"]
                    if (not isinstance(self.completed, list) or
                            not isinstance(self.in_progress, bool) or
                            not isinstance(self.interruptions, list) or
                            any(type(index) is not int or not 0 <= index <= len(self.completed)
                                for index in self.interruptions)):
                        raise ValueError("invalid checkpoint state")
                except (OSError, KeyError, TypeError, ValueError):
                    raise AppError("检查点无法读取，请保留原记录并换新任务目录") from None
                if previous != fingerprint:
                    raise AppError("检查点与当前资料、模板或模型配置不一致，请换新任务目录")
            else:
                self._store()
            yield self

    def start_section(self):
        if self.in_progress:
            self.interruptions.append(len(self.completed))
        self.in_progress = True
        self._store()

    def save_section(self, result):
        self.completed.append(result)
        self.in_progress = False
        self._store()

    def _store(self):
        output = NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path,
                                    suffix=".tmp", delete=False)
        temp = Path(output.name)
        try:
            with output:
                json.dump({"fingerprint": self.fingerprint, "completed": self.completed,
                           "in_progress": self.in_progress, "interruptions": self.interruptions},
                          output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            temp.replace(self.record)
        finally:
            temp.unlink(missing_ok=True)
