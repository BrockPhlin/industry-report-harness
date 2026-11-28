"""Local research sessions. The CLI and the browser share the same report engine."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from hashlib import sha256
import sqlite3
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from uuid import uuid4

from .errors import AppError
from .comparison_input import comparison_scope
from .generator import chat_completion, model_connection
from .pv_evidence import load_inputs
from .reference_catalog import selected_reports
from .service import text_field
from .store import now
from .solar_data import SOURCE_GROUPS, SolarLibrary
from . import long_report


class Research:
    def __init__(self, service):
        self.store = service.store
        self.config = service.config
        self.root = Path(self.store.filename).with_suffix(".research")
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")
        self.lock = Lock()
        self.active = set()
        self.template, self.sources, self.fixture_facts = load_inputs()
        self.library = SolarLibrary(self.store)
        with closing(self.store.connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS research (
                id TEXT PRIMARY KEY, question TEXT, focus TEXT, mode TEXT, model TEXT,
                created TEXT, error TEXT DEFAULT '', answers TEXT DEFAULT '[]')""")

            db.execute("""CREATE TABLE IF NOT EXISTS long_jobs (
                id TEXT PRIMARY KEY, workflow TEXT, scope TEXT, target INTEGER, style TEXT,
                phase TEXT, turns TEXT DEFAULT '[]', progress TEXT DEFAULT '', checkpoint TEXT DEFAULT '{}')""")

            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS comparison_reports (
                id TEXT PRIMARY KEY, signature TEXT NOT NULL UNIQUE,
                calculation TEXT NOT NULL, markdown TEXT NOT NULL)""")
            columns = {r["name"] for r in db.execute("PRAGMA table_info(long_jobs)")}
            if "outline" not in columns:
                db.execute("ALTER TABLE long_jobs ADD COLUMN outline TEXT DEFAULT '[]'")
            if "source_groups" not in columns:
                db.execute("ALTER TABLE long_jobs ADD COLUMN source_groups TEXT DEFAULT '[]'")
            if "comparison_id" not in columns:
                db.execute("ALTER TABLE long_jobs ADD COLUMN comparison_id TEXT")
            if "reference_ids" not in columns:
                db.execute("ALTER TABLE long_jobs ADD COLUMN reference_ids TEXT NOT NULL DEFAULT '[]'")

    def create_comparison(self, selection):
        from .comparison_report import render_comparison
        from .province_comparison import build_comparison

        result = build_comparison(selection)
        markdown = render_comparison(result, "markdown").decode("utf-8")
        bundle = render_comparison(result, "json", markdown=markdown)
        signature = sha256(bundle).hexdigest()
        with closing(self.store.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM comparison_reports WHERE signature=?", (signature,)).fetchone()
            if existing:
                key = existing["id"]
            else:
                key = uuid4().hex
                plan = result["plan"]
                regions = "、".join(plan["regions"][:3])
                if len(plan["regions"]) > 3:
                    regions += f"等{len(plan['regions'])}地"
                title = f"{regions} · {plan['period_label']} · {plan['metric_label']}"
                db.execute("INSERT INTO research(id,question,focus,mode,model,created) VALUES(?,?,?,?,?,?)",
                           (key, title, "[]", "comparison", "", now()))
                db.execute("INSERT INTO comparison_reports(id,signature,calculation,markdown) VALUES(?,?,?,?)",
                           (key, signature, bundle.decode("utf-8"), markdown))
        return self.task(key)

    def saved_comparison(self, key):
        if not isinstance(key, str):
            raise AppError("请选择一份已保存的分省对比报告")
        with closing(self.store.connect()) as db:
            row = db.execute("SELECT calculation,markdown FROM comparison_reports WHERE id=?", (key,)).fetchone()
        if row is None:
            raise AppError("找不到这份分省对比报告", 404)
        return dict(row)

    def comparison_download(self, key, filename):
        saved = self.saved_comparison(key)
        if filename == "calculation.json":
            return saved["calculation"].encode()
        if filename == "report.md":
            return saved["markdown"].encode()
        from .comparison_report import render_comparison
        return render_comparison(json.loads(saved["calculation"]), "pdf", markdown=saved["markdown"])

    @staticmethod
    def source_groups(data):
        groups = data.get("source_groups", [])
        if not isinstance(groups, list) or any(
            not isinstance(x, str) or x not in SOURCE_GROUPS for x in groups
        ):
            raise AppError("请从工作台列出的资料来源中选择")
        return [group for group in SOURCE_GROUPS if group in groups]

    @staticmethod
    def writing_references(data):
        try:
            return selected_reports(data.get("reference_ids", []))
        except ValueError as exc:
            raise AppError(str(exc)) from exc

    @staticmethod
    def outline(data):
        value = data.get("outline", [])
        if (
            not isinstance(value, list)
            or len(value) > 12
            or any(not isinstance(t, str) or not t.strip() or len(t) > 100 or "\n" in t for t in value)
        ):
            raise AppError("提纲最多12章，每章使用一行简短标题")
        titles = [t.strip() for t in value]
        if len(set(titles)) != len(titles):
            raise AppError("提纲中有重名章节")
        return titles

    def spec(self, key, *, checkpoint=False):
        fields = "workflow,scope,target,style,phase,turns,progress,outline,source_groups,comparison_id,reference_ids" + (
            ",checkpoint" if checkpoint else ""
        )
        with closing(self.store.connect()) as db:
            row = db.execute(f"SELECT {fields} FROM long_jobs WHERE id=?", (key,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["turns"] = json.loads(result["turns"])
        result["outline"] = json.loads(result["outline"])
        result["source_groups"] = json.loads(result["source_groups"])
        result["reference_ids"] = json.loads(result["reference_ids"])
        if checkpoint:
            result["checkpoint"] = json.loads(result["checkpoint"])
        return result

    def start_long(self, data):
        question = text_field(data, "question", 2400, True)
        scope = text_field(data, "scope", 1800)
        outline = self.outline(data)
        groups = self.source_groups(data)
        references = self.writing_references(data)
        comparison_id = data.get("comparison_id")
        if comparison_id is not None:
            saved = self.saved_comparison(comparison_id)
            if groups and "grid" not in groups:
                raise AppError("引用分省比较时，请在资料来源中包含国家能源局分省并网原表")
        workflow = data.get("workflow")
        style = data.get("style", "research")
        target = data.get("target")
        if target is None:
            target = long_report.requested_length(question, 3600)
        if (
            workflow not in ("direct", "discuss")
            or not isinstance(style, str)
            or style not in long_report.STYLES
            or type(target) is not int
            or not long_report.MIN_LENGTH <= target <= long_report.MAX_LENGTH
        ):
            raise AppError("请选择写作方式和版式，正文字数须在800至10000之间")
        _, model, _ = model_connection(self.config)
        key = uuid4().hex
        self.root.mkdir(exist_ok=True)
        turns = []
        if workflow == "discuss":
            context = scope or question
            if comparison_id:
                context += "\n已附计算资料：" + comparison_scope(json.loads(saved["calculation"]))
            reply = long_report.discuss(self.config, question, [], context, references=references)
            turns.append(dict(question=question, answer=reply))
        phase = "planning" if workflow == "discuss" else "writing"
        with closing(self.store.connect()) as db, db:
            db.execute(
                "INSERT INTO research(id,question,focus,mode,model,created) VALUES(?,?,?,?,?,?)",
                (key, question, "[]", "live", model, now()),
            )
            db.execute(
                """INSERT INTO long_jobs(id,workflow,scope,target,style,phase,turns,outline,source_groups,comparison_id,reference_ids)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    key,
                    workflow,
                    scope,
                    target,
                    style,
                    phase,
                    json.dumps(turns, ensure_ascii=False),
                    json.dumps(outline, ensure_ascii=False),
                    json.dumps(groups),
                    comparison_id,
                    json.dumps([r["id"] for r in references]),
                ),
            )
        if phase == "writing":
            self.launch(key)
        return self.task(key)

    def plan_turn(self, key, data):
        question = text_field(data, "question", 2400, True)
        with self.lock:
            if key in self.active:
                raise AppError("正在处理上一条消息", 409)
            self.active.add(key)
        try:
            spec = self.spec(key)
            if not spec or spec["phase"] != "planning":
                raise AppError("研究已开始写作", 409)
            turns = spec["turns"]
            reply = long_report.discuss(self.config, self.rows(key)["question"], turns, question,
                                        references=self.writing_references(spec))
            turns.append(dict(question=question, answer=reply))
            target = data.get("target")
            if target is None:
                target = long_report.requested_length(question, spec["target"])
            if type(target) is not int or not long_report.MIN_LENGTH <= target <= long_report.MAX_LENGTH:
                raise AppError("正文字数须在800至10000之间")
            with closing(self.store.connect()) as db, db:
                db.execute(
                    "UPDATE long_jobs SET turns=?,target=? WHERE id=?",
                    (json.dumps(turns, ensure_ascii=False), target, key),
                )
        finally:
            with self.lock:
                self.active.discard(key)
        return self.task(key)

    def revise_scope(self, key, data):
        references_only = data.keys() == {"reference_ids"}
        scope = None if references_only else text_field(data, "scope", 1800)
        target = data.get("target")
        style = data.get("style")
        outline = None if references_only else json.dumps(self.outline(data), ensure_ascii=False)
        groups = json.dumps(self.source_groups(data)) if "source_groups" in data else None
        reference_ids = None
        if "reference_ids" in data:
            reference_ids = json.dumps([r["id"] for r in self.writing_references(data)])
        if groups is not None and data["source_groups"] and "grid" not in data["source_groups"]:
            if (self.spec(key) or {}).get("comparison_id"):
                raise AppError("已附分省比较，请在资料来源中包含国家能源局分省并网原表")
        if not references_only and (
            type(target) is not int
            or not long_report.MIN_LENGTH <= target <= long_report.MAX_LENGTH
            or not isinstance(style, str)
            or style not in long_report.STYLES
        ):
            raise AppError("请检查字数和写作结构")
        with self.lock:
            if key in self.active:
                raise AppError("请等待当前讨论回复后修改", 409)
            with closing(self.store.connect()) as db, db:
                changed = db.execute(
                    """UPDATE long_jobs SET scope=COALESCE(?,scope),target=COALESCE(?,target),
                               style=COALESCE(?,style),outline=COALESCE(?,outline),source_groups=COALESCE(?,source_groups),
                               reference_ids=COALESCE(?,reference_ids)
                               WHERE id=? AND phase='planning'""",
                    (scope, target, style, outline, groups, reference_ids, key),
                ).rowcount
                if not changed:
                    raise AppError("只有确认写作前可以调整范围", 409)
        return self.task(key)

    def begin(self, key):
        with self.lock:
            if key in self.active:
                raise AppError("请等待范围讨论完成", 409)
            with closing(self.store.connect()) as db, db:
                if not db.execute(
                    "UPDATE long_jobs SET phase='writing' WHERE id=? AND phase='planning'", (key,)
                ).rowcount:
                    raise AppError("这份研究已经开始写作", 409)
        self.launch(key)
        return self.task(key)

    def settings(self):
        try:
            _, model, _ = model_connection(self.config)
        except AppError:
            model = None
        return dict(
            model=model,
            styles=long_report.STYLES,
            source_groups=SOURCE_GROUPS,
            sections=[s["title"] for s in self.template["sections"]],
            sources=list(self.sources.values()),
            fixture_facts=[fact for records in self.fixture_facts.values() for fact in records],
        )

    def rows(self, key=None):
        with closing(self.store.connect()) as db:
            if key is None:
                return [
                    dict(row)
                    for row in db.execute("SELECT id,question,created FROM research ORDER BY rowid DESC")
                ]
            row = db.execute("SELECT * FROM research WHERE id=?", (key,)).fetchone()
        if row is None:
            raise AppError("找不到这份研究", 404)
        return dict(row)

    def task(self, key):
        row = self.rows(key)
        out = self.root / key
        row["focus"] = json.loads(row["focus"])
        row["answers"] = json.loads(row["answers"])
        if row["mode"] == "comparison":
            saved = self.saved_comparison(key)
            bundle = json.loads(saved["calculation"])
            row.update(kind="comparison", status="ready", markdown=saved["markdown"],
                       comparison=bundle, revision=bundle["markdown_sha256"])
            return row
        with self.lock:
            active = key in self.active
        spec = self.spec(key)
        if spec:
            row["spec"] = spec
        if spec and spec["phase"] == "planning":
            row["status"] = "planning"
        elif (out / "trace.json").is_file():
            trace = json.loads((out / "trace.json").read_text())
            row["approved"] = (out / "reviewed/brief.pdf").is_file()
            path = out / ("reviewed/brief.md" if row["approved"] else "draft.md")
            if spec and not row["approved"] and (out / "edited.md").is_file():
                path = out / "edited.md"
            row["markdown"] = path.read_text()
            row["revision"] = sha256(row["markdown"].encode()).hexdigest()
            row.update(status="ready", error="", events=trace["events"])
            if spec:
                if (out / "edited.md").is_file():
                    trace["body_length"] = long_report.editorial_revision(
                        (out / "draft.md").read_text(), (out / "edited.md").read_text()
                    )
                row.update(
                    chart=trace.get("chart"),
                    charts=trace.get("charts", [trace["chart"]] if trace.get("chart") else []),
                    operations=trace.get("operations", []),
                    evidence=trace["evidence"],
                    writing_references=trace.get("writing_references", []),
                    writing_notes_offered=trace.get("writing_notes_offered", {}),
                    retrieval=trace["retrieval"],
                    length=trace["body_length"],
                    outline=trace["plan"]["sections"],
                )
        elif active or self.other_worker(key):
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
            if spec:
                row["operations"] = self.spec(key, checkpoint=True)["checkpoint"].get("operations", [])
        return row

    def start(self, data):
        if "workflow" in data:
            return self.start_long(data)
        question = text_field(data, "question", 300, True)
        focus = data.get("focus")
        options = self.settings()
        if (
            not isinstance(focus, list)
            or not focus
            or any(s not in options["sections"] for s in focus)
            or len(set(focus)) != len(focus)
        ):
            raise AppError("请至少选择一个有效的研究重点")
        mode = data.get("mode")
        if mode not in ("live", "fixture"):
            raise AppError("请选择模型或离线演练")
        if mode == "live":
            model_connection(self.config)
        key = uuid4().hex
        self.root.mkdir(exist_ok=True)
        with closing(self.store.connect()) as db, db:
            db.execute(
                "INSERT INTO research(id,question,focus,mode,model,created) VALUES(?,?,?,?,?,?)",
                (key, question, json.dumps(focus), mode, options["model"] if mode == "live" else "", now()),
            )
        self.launch(key)
        return self.task(key)

    def acquire_run(self, key):
        locks = self.root / ".workers"
        locks.mkdir(parents=True, exist_ok=True)
        lease = sqlite3.connect(locks / (key + ".sqlite3"), timeout=0, check_same_thread=False)
        try:
            lease.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            lease.close()
            raise AppError("此任务已有进程正在写作", 409) from None
        return lease

    def other_worker(self, key):
        if not (self.root / ".workers" / (key + ".sqlite3")).exists():
            return False
        try:
            self.acquire_run(key).close()
            return False
        except AppError:
            return True

    def launch(self, key):
        row = self.rows(key)
        if row["mode"] == "comparison":
            raise AppError("这份分省对比已完成，调整选项可生成新的对比报告", 409)
        spec = self.spec(key)
        if spec and spec["phase"] != "writing":
            raise AppError("请先确认范围并开始写作", 409)
        with self.lock:
            if key in self.active or (self.root / key).is_dir():
                raise AppError("任务正在运行或已完成", 409)
            self.active.add(key)
        with closing(self.store.connect()) as db, db:
            db.execute("UPDATE research SET error='' WHERE id=?", (key,))
        try:
            lease = self.acquire_run(key)
            try:
                self.pool.submit(self.generate, row, lease)
            except RuntimeError:
                lease.close()
                raise
        except Exception:
            with self.lock:
                self.active.discard(key)
            raise

    def generate(self, row, lease):
        key = row["id"]
        try:
            spec = self.spec(key, checkpoint=True)
            if spec:
                def progress(message):
                    with closing(self.store.connect()) as db, db:
                        db.execute("UPDATE long_jobs SET progress=? WHERE id=?", (message, key))

                def save(checkpoint):
                    with closing(self.store.connect()) as db, db:
                        db.execute(
                            "UPDATE long_jobs SET checkpoint=? WHERE id=?",
                            (json.dumps(checkpoint, ensure_ascii=False), key),
                        )

                if not spec["comparison_id"] and "evidence" not in spec["checkpoint"]:
                    from .comparison_intent import infer_comparison
                    if not spec["source_groups"] or "grid" in spec["source_groups"]:
                        instructions = "\n".join([spec["scope"], *(t["question"] for t in spec["turns"])])
                        selection = infer_comparison(row["question"], instructions, spec["outline"])
                        if selection:
                            progress("正在按两期原表计算分省变化和排名")
                            with long_report.record_stage(self.config, spec["checkpoint"], save,
                                                          "comparison", "从两期原表计算分省差额和排名"):
                                parent = self.create_comparison(selection)
                                with closing(self.store.connect()) as db, db:
                                    db.execute("UPDATE long_jobs SET comparison_id=? WHERE id=?", (parent["id"], key))
                                spec["comparison_id"] = parent["id"]
                if spec["comparison_id"]:
                    parent = self.task(spec["comparison_id"])
                    spec.update(comparison=parent["comparison"], comparison_created=parent["created"])
                long_report.generate(self.config, self.library, self.root, row, spec, progress, save)
                return
            from pv_brief import create_run

            resume = (self.root / f".{key}.pv-checkpoint/completed.json").is_file()
            args = SimpleNamespace(
                output=self.root / key,
                omit_source=[],
                template=None,
                corpus=None,
                mode=row["mode"],
                request_timeout=90,
                resume=resume,
            )
            create_run(args, config=self.config, focus=json.loads(row["focus"]), question=row["question"])
        except Exception as exc:
            message = (
                str(exc).split("重跑原命令")[0]
                if isinstance(exc, AppError)
                else "生成失败，请检查 Python 环境及任务目录。"
            )
            with closing(self.store.connect()) as db, db:
                db.execute("UPDATE research SET error=? WHERE id=?", (message, key))
        finally:
            lease.close()
            with self.lock:
                self.active.discard(key)

    def edit(self, key, data):
        markdown = text_field(data, "markdown", 90000, True) + "\n"
        if not self.spec(key):
            raise AppError("旧简报保留原件", 409)
        out = self.root / key
        with self.lock:
            original = out / "draft.md"
            edited = out / "edited.md"
            if not original.is_file() or (out / "reviewed").exists():
                raise AppError("只可润色尚未确认的草稿", 409)
            base = edited if edited.is_file() else original
            if data.get("revision") != sha256(base.read_bytes()).hexdigest():
                raise AppError("草稿已更新，请刷新后再修改", 409)
            evidence = json.loads((out / "trace.json").read_text())["evidence"]
            long_report.editorial_revision(original.read_text(), markdown, evidence)
            temporary = out / "edited.md.tmp"
            temporary.write_text(markdown, encoding="utf-8")
            temporary.replace(edited)
        return self.task(key)

    def approve(self, key):
        from pv_brief import approve_run

        row = self.task(key)
        if row["mode"] == "comparison":
            raise AppError("计算报告可从分省对比页面直接下载", 409)
        if row["status"] != "ready":
            raise AppError("请等待草稿生成", 409)
        with self.lock:
            if not (self.root / key / "reviewed/brief.pdf").exists():
                edited = self.root / key / "edited.md"
                approve_run(
                    SimpleNamespace(output=self.root / key, markdown=edited if edited.is_file() else None),
                    confirmation="explicit_web_confirmation",
                )
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
            if row.get("spec"):
                from .followup import grounded_followup
                parent_id = row["spec"].get("comparison_id")
                calculation = json.loads(self.saved_comparison(parent_id)["calculation"]) if parent_id else None
                answer = grounded_followup(self.config, row, question, calculation)
            else:
                answer = self.brief_followup(row, question)
            with closing(self.store.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                previous = json.loads(db.execute("SELECT answers FROM research WHERE id=?", (key,)).fetchone()[0])
                if previous != row["answers"]:
                    raise AppError("另一条追问已完成，请刷新报告后重试", 409)
                turn = dict(question=question, answer=answer.strip(), revision=row["revision"])
                db.execute("UPDATE research SET answers=? WHERE id=?", (json.dumps([*previous, turn], ensure_ascii=False), key))
        finally:
            with self.lock:
                self.active.discard(key)
        return self.task(key)

    def brief_followup(self, row, question):
        messages = [
            {
                "role": "system",
                "content": "你为光伏研究员解读本次简报。仅据以下草稿回答，引用事实时标出草稿中的来源编号。缺少数据就直说，不推测。不要把新增装机与组件产量相加。用简短中文。\n"
                + row["markdown"],
            }
        ]
        for turn in row["answers"][-4:]:
            messages.extend(
                [
                    {"role": "user", "content": turn["question"]},
                    {"role": "assistant", "content": turn["answer"]},
                ]
            )
        messages.append({"role": "user", "content": question})
        result = chat_completion(model_connection(self.config), messages, request_timeout=90)
        answer = result["message"].get("content")
        if result.get("finish_reason") != "stop" or not isinstance(answer, str) or not answer.strip():
            raise AppError("模型未返回完整答复，请重试", 502)
        return answer
