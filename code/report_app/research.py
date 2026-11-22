"""Local research sessions. The CLI and the browser share the same report engine."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from uuid import uuid4

from .errors import AppError
from .generator import chat_completion, model_connection
from .pv_evidence import load_inputs
from .service import text_field
from .store import now


class Research:
    def __init__(self, service):
        self.store = service.store
        self.config = service.config
        self.root = Path(self.store.filename).with_suffix(".research")
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")
        self.lock = Lock()
        self.active = set()
        self.template, self.sources, _ = load_inputs()
        with closing(self.store.connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS research (
                id TEXT PRIMARY KEY, question TEXT, focus TEXT, mode TEXT, model TEXT,
                created TEXT, error TEXT DEFAULT '', answers TEXT DEFAULT '[]')""")

    def settings(self):
        try:
            _, model, _ = model_connection(self.config)
        except AppError:
            model = None
        return dict(model=model, sections=[s["title"] for s in self.template["sections"]],
                    sources=list(self.sources.values()))

    def rows(self, key=None):
        with closing(self.store.connect()) as db:
            if key is None:
                return [dict(row) for row in db.execute("SELECT id,question,created FROM research ORDER BY rowid DESC")]
            row = db.execute("SELECT * FROM research WHERE id=?", (key,)).fetchone()
        if row is None:
            raise AppError("找不到这份研究", 404)
        return dict(row)

    def task(self, key):
        row = self.rows(key)
        out = self.root / key
        row["focus"] = json.loads(row["focus"])
        row["answers"] = json.loads(row["answers"])
        with self.lock:
            active = key in self.active
        if (out / "trace.json").is_file():
            trace = json.loads((out / "trace.json").read_text())
            row["approved"] = (out / "reviewed/brief.pdf").is_file()
            row["markdown"] = (out / ("reviewed/brief.md" if row["approved"] else "draft.md")).read_text()
            row.update(status="ready", events=trace["events"])
        elif active:
            row["status"] = "running"
            checkpoint = self.root / f".{key}.pv-checkpoint/completed.json"
            try:
                completed = json.loads(checkpoint.read_text())["completed"]
            except FileNotFoundError:
                completed = []
            row["completed"] = [c["section"]["title"] for c in completed]
        else:
            row["status"] = "failed"
            row["error"] = row["error"] or "上次运行中断，可从已完成的章节继续。"
        return row

    def start(self, data):
        question = text_field(data, "question", 300, True)
        focus = data.get("focus")
        options = self.settings()
        if (not isinstance(focus, list) or not focus or
                any(s not in options["sections"] for s in focus) or len(set(focus)) != len(focus)):
            raise AppError("请至少选择一个有效的研究重点")
        mode = data.get("mode")
        if mode not in ("live", "fixture"):
            raise AppError("请选择模型或离线演练")
        if mode == "live":
            model_connection(self.config)
        key = uuid4().hex
        self.root.mkdir(exist_ok=True)
        with closing(self.store.connect()) as db, db:
            db.execute("INSERT INTO research(id,question,focus,mode,model,created) VALUES(?,?,?,?,?,?)",
                       (key, question, json.dumps(focus), mode, options["model"] if mode == "live" else "", now()))
        self.launch(key)
        return self.task(key)

    def launch(self, key):
        row = self.rows(key)
        with self.lock:
            if key in self.active or (self.root / key).is_dir():
                raise AppError("任务正在运行或已完成", 409)
            self.active.add(key)
        self.pool.submit(self.generate, row)

    def generate(self, row):
        key = row["id"]
        try:
            from pv_brief import create_run
            resume = (self.root / f".{key}.pv-checkpoint/completed.json").is_file()
            args = SimpleNamespace(output=self.root / key, omit_source=[], template=None, corpus=None,
                                   mode=row["mode"], request_timeout=90, resume=resume)
            create_run(args, config=self.config, focus=json.loads(row["focus"]), question=row["question"])
        except Exception as exc:
            message = str(exc).split("重跑原命令")[0] if isinstance(exc, AppError) else "生成失败，请检查 Python 环境及任务目录。"
            with closing(self.store.connect()) as db, db:
                db.execute("UPDATE research SET error=? WHERE id=?", (message, key))
        finally:
            with self.lock:
                self.active.discard(key)

    def approve(self, key):
        from pv_brief import approve_run
        row = self.task(key)
        if row["status"] != "ready":
            raise AppError("请等待草稿生成", 409)
        with self.lock:
            if not (self.root / key / "reviewed/brief.pdf").exists():
                approve_run(SimpleNamespace(output=self.root / key, markdown=None), confirmation="explicit_web_confirmation")
        return self.task(key)

    def ask(self, key, data):
        question = text_field(data, "question", 300, True)
        self.rows(key)
        with self.lock:
            if key in self.active:
                raise AppError("上一条提问仍在处理", 409)
            self.active.add(key)
        try:
            row = self.task(key)
            if row["status"] != "ready" or row["mode"] != "live":
                raise AppError("请先用真实模型生成草稿，再就这份报告追问", 409)
            messages = [{"role": "system", "content": "你为光伏研究员解读本次简报。仅据以下草稿回答，引用事实时标出草稿中的来源编号。缺少数据就直说，不推测。不要把新增装机与组件产量相加。用简短中文。\n" + row["markdown"]}]
            for turn in row["answers"][-4:]:
                messages.extend([{"role": "user", "content": turn["question"]},
                                 {"role": "assistant", "content": turn["answer"]}])
            messages.append({"role": "user", "content": question})
            result = chat_completion(model_connection(self.config), messages, request_timeout=90)
            answer = result["message"].get("content")
            if result.get("finish_reason") != "stop" or not isinstance(answer, str) or not answer.strip():
                raise AppError("模型未返回完整答复，请重试", 502)
            turns = [*row["answers"], dict(question=question, answer=answer.strip())]
            with closing(self.store.connect()) as db, db:
                db.execute("UPDATE research SET answers=? WHERE id=?", (json.dumps(turns, ensure_ascii=False), key))
        finally:
            with self.lock:
                self.active.discard(key)
        return self.task(key)
