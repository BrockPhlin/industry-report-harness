"""Counterexamples around evidence provenance, length, and the two entry paths."""

from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_app.errors import AppError
from report_app import irena
from report_app.manufacturing import manufacturing_observations
from report_app.policy import Policy, parse_policy
from report_app import long_report as report
from report_app.research import Research
from report_app.server import observations_csv
from report_app.provinces import provincial_rows, region_name
from report_app.service import Service
from report_app.solar_data import (
    SolarLibrary,
    capacity_rows,
    display_value,
    permitted,
    release_rows,
    trend,
)
from report_app.store import Store
from report_app.trade import trade_jobs, trade_rows


def csv_source(value):
    return f"Entity,Code,Year,Solar\nChina,CHN,2020,10\nChina,CHN,2021,{value}\n".encode()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "data.sqlite3")
        self.library = SolarLibrary(self.store, lambda url: csv_source("20"))

    def ingest(self):
        return self.library.ingest(
            "https://ourworldindata.org/solar.csv",
            "装机",
            "IRENA",
            "https://ourworldindata.org/chart",
            capacity_rows,
        )

    def test_snapshot_dedup_revision_and_cached_failure(self):
        one, _ = self.ingest()
        self.assertEqual(self.ingest()[0], one)
        self.library.download = lambda url: csv_source("30")
        two, _ = self.ingest()
        self.assertNotEqual(one, two)
        with patch.object(self.library, "download", side_effect=OSError("offline")):
            key, status = self.ingest()
        self.assertEqual(key, two)
        self.assertIn("快照", status)
        self.assertEqual(self.library.summary()["observations"], 2)
        self.assertEqual(self.library.browse("China", 2021, 2021)[0]["value"], "30")
        plan = dict(regions=["China"], start=2021, end=2021, keywords=[])
        self.assertEqual(self.library.select([one], plan)[0]["raw_series"], [(2021, "20")])

    def test_parser_schema_creates_a_new_snapshot_with_the_same_public_fingerprint(self):
        old, _ = self.ingest()
        args = (
            "https://ourworldindata.org/solar.csv",
            "装机",
            "IRENA",
            "https://ourworldindata.org/chart",
            capacity_rows,
        )
        new, _ = self.library.ingest(*args, schema="add-column")
        self.assertNotEqual(old, new)
        self.assertEqual(self.library.ingest(*args, schema="add-column")[0], new)
        plan = dict(regions=["China"], start=2021, end=2021, keywords=[])
        snapshots = self.library.select([old, new], plan)
        self.assertEqual(snapshots[0]["digest"], snapshots[1]["digest"])

    def test_same_source_fetched_concurrently(self):
        with ThreadPoolExecutor(2) as pool:
            ids = list(pool.map(lambda _: self.ingest()[0], range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(self.library.summary()["observations"], 2)

    def test_public_csv_filter_preserves_historical_snapshot_identity(self):
        self.ingest()
        found = self.library.browse("China", 2020, 2021, metric="累计", publisher="IRENA")
        self.assertEqual(len(found), 2)
        self.assertFalse(self.library.browse("China", 2020, 2021, publisher="其他发布方"))
        line = dict(found[0], value="-122.8", metric="=malformed value")
        self.assertIn(",'=malformed value,-122.8,", observations_csv([line]).decode("utf-8-sig"))
        self.assertEqual(len(line["digest"]), 64)

    def test_unrelated_web_content_cannot_become_evidence(self):
        raw = "<p>登录导航新闻报告声明联系我们</p><p>2024年光伏组件产量达到588GW，同比增长13.5%。</p>".encode()
        self.assertEqual(
            release_rows(raw)[1], [("网页第2段", "2024年光伏组件产量达到588GW，同比增长13.5%。")]
        )
        for address in (
            "http://www.nea.gov.cn/x",
            "https://www.nea.gov.cn.example.net/x",
            "https://localhost/x",
        ):
            self.assertFalse(permitted(address))

    def test_trade_classification_and_flow(self):
        plan = dict(regions=["China"], title="组件出口", keywords=["出口"], start=2020, end=2023)
        jobs = trade_jobs(plan)
        self.assertEqual(len(jobs), 2)
        record = dict(
            period=2023,
            reporterCode=156,
            cmdCode="854143",
            flowCode="X",
            partnerCode=0,
            partner2Code=0,
            motCode=0,
            customsCode="C00",
            primaryValue=123000000,
        )

        def parse(row):
            return trade_rows(
                json.dumps({"data": [row]}), year=2023, region="China", flow="X", label="出口"
            )

        self.assertEqual(parse(record)[0][0][-1], "1.23")
        with self.assertRaises(ValueError):
            parse(dict(record, flowCode="M"))

    def test_change_in_percentages_is_a_difference_in_points(self):
        self.assertEqual(display_value("0.00091", 2), "0.00091")
        self.assertEqual(display_value("1000", 2), "1000")
        self.assertEqual(display_value("0", 2), "0")
        self.assertIn("2.00个百分点", trend([(2020, "2"), (2022, "4")], "%"))
        self.assertIn("100.0%", trend([(2020, "2"), (2022, "4")], "GW"))
        self.assertEqual(trend([(2020, "0"), (2022, "4")], "GW"), "")

    def test_trade_limits_apply_across_sessions_and_only_to_selected_exporter(self):
        plan = dict(
            regions=["China", "Germany"],
            trade_regions=["China"],
            title="组件出口",
            keywords=[],
            start=2023,
            end=2024,
        )
        jobs = trade_jobs(plan)
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all("reporterCode=156" in job[0] for job in jobs))
        error = HTTPError(jobs[0][0], 429, "Too Many Requests", {"Retry-After": "90"}, None)
        with patch.object(self.library, "download", side_effect=error) as download:
            self.assertIsNone(self.library.ingest(*jobs[0])[0])
            other = SolarLibrary(self.store, download)
            key, reason = other.ingest(*jobs[1])
            self.assertIsNone(key)
            self.assertIn("限流", reason)
            download.assert_called_once()

    def test_trade_batch_uses_the_same_product_and_flow_as_share_denominator(self):
        common = dict(
            period=2025, reporterCode=156, flowCode="X", partner2Code=0, motCode=0, customsCode="C00"
        )
        rows = [
            dict(common, cmdCode="854143", partnerCode=0, primaryValue=1000000000),
            dict(common, cmdCode="854143", partnerCode=528, primaryValue=300000000),
            dict(common, cmdCode="854142", partnerCode=0, primaryValue=2000000000),
            dict(common, cmdCode="854142", partnerCode=528, primaryValue=None),
        ]
        values, notes = trade_rows(
            json.dumps({"data": rows}),
            year=2025,
            region="China",
            flow="X",
            label="出口",
            products=("854143", "854142"),
            partners=(0, 528),
        )
        self.assertEqual(len(values), 3)
        self.assertIn("30.00%", notes[0][1])
        self.assertIn("未组装光伏电池片对荷兰", notes[-1][1])
        self.assertIn("没有返回记录", notes[-1][1])

    def test_provincial_inputs_are_tied_to_verified_images(self):
        self.assertEqual(region_name("浙江省"), "浙江")
        self.assertEqual(region_name("Inner Mongolia"), "内蒙古")
        self.assertEqual(region_name("广西壮族自治区"), "广西")
        with self.assertRaisesRegex(ValueError, "更换原表"):
            provincial_rows(b"replacement", year=2025)

    def test_manufacturing_parser_keeps_publisher_and_lower_bound(self):
        data = [
            "多晶硅环节，1—12月全国产量超过143万吨。",
            "硅片环节，1—12月全国产量超过622GW。",
            "电池环节，1—12月全国晶硅电池产量超过545GW。",
            "组件环节，1—12月全国晶硅组件产量超过499GW。",
        ]
        manufacturing = manufacturing_observations(data, 2023)
        self.assertEqual(
            manufacturing[-1], ("China", 2023, "光伏组件产量（工信部，晶硅，发布下限）", "GW", "499")
        )
        with self.assertRaisesRegex(ValueError, "组件产量段"):
            manufacturing_observations(data[:-1], 2023)

    def test_policy_handles_official_div_with_breaks(self):
        policy = Policy(
            2025, "China", "市场化政策", "发文机关", "https://www.ndrc.gov.cn/test", ("上网电价",), "136号"
        )
        html = (
            '<div class="TRS_Editor"><div>通知</div><span>136号</span><br/>'
            "<span>新能源项目需要按上网电量参与市场交易。各地根据市场规则确定结算方式，分开公布项目申报流程和适用日期。</span><br/>"
            "<script>never evaluate source markup</script></div>"
        )
        self.assertIn("上网电量", parse_policy(html.encode(), policy=policy)[1][0][1])
        with self.assertRaisesRegex(ValueError, "政策文号"):
            parse_policy(html.replace("136号", "135号").encode(), policy=policy)

    def test_irena_keeps_connection_types_and_nulls_distinct(self):
        categories = [
            ["USA"],
            ["Solar photovoltaic"],
            ["Electrical Installed Capacity (MW)"],
            ["All", "On-grid", "Off-grid"],
            ["2025"],
        ]
        dimensions = {}
        for name, labels in zip(irena.DIMENSIONS, categories):
            dimensions[name] = {
                "category": {
                    "index": {str(i): i for i in range(len(labels))},
                    "label": {str(i): label for i, label in enumerate(labels)},
                }
            }
        payload = {
            "source": "IRENA",
            "id": list(irena.DIMENSIONS),
            "dimension": dimensions,
            "value": [2400, 2300, None],
        }
        rows, _ = irena.capacity_rows(json.dumps(payload))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ("United States", 2025, irena.METRICS["All"], "GW", "2.4"))
        self.assertEqual(rows[1], ("United States", 2025, irena.METRICS["On-grid"], "GW", "2.3"))


class WritingTests(unittest.TestCase):
    sample = {"E1": {"text": "2024年，累计装机为20 GW。", "title": "年度统计"}}

    def test_named_interim_chapter_extends_the_annual_retrieval_window(self):
        plan = dict(
            title="浙苏光伏",
            regions=["浙江", "江苏"],
            start=2021,
            end=2025,
            keywords=["光伏", "并网"],
            sections=["模型的提纲"],
        )
        with patch.object(report, "answer", return_value=plan):
            actual = report.make_plan(
                {}, "比较浙江和江苏", "", [], 2000, ["2021—2025 年比较", "2026 年前三季度更新"]
            )
        self.assertEqual((actual["start"], actual["end"]), (2021, 2026))
        self.assertTrue(actual["quarter_requested"])

    def test_chinese_lengths_and_revisions(self):
        for prompt, expected in [
            ("计划一万字", 10000),
            ("先写3000字，改为四千五百字", 4500),
            ("大约 1.6 千字", 1600),
            ("看2025年的数据", 3600),
        ]:
            self.assertEqual(report.requested_length(prompt, 3600), expected)

    def test_rounding_requires_unique_measurement_and_matching_unit(self):
        self.assertIn("1174.96 TWh", report.restore_rounded_values("约1175 TWh", "全年1174.96 TWh"))
        for facts in ("1174.96 GW", "1174.96 TWh，1175.08 TWh"):
            self.assertEqual(report.restore_rounded_values("1175 TWh", facts), "1175 TWh")

    def test_scope_review_keeps_other_paragraphs_and_checks_replacement(self):
        evidence = [dict(ref="E1", title="年度装机", locator="总计", text="2024 年累计装机为20 GW。")]
        original = [
            "公布的累计装机为20 GW，规划时还需要核对各地的并网容量。 [E1]",
            "这个数字表明全省生产效率已经提高。 [E1]",
        ]
        replacement = {
            "paragraph": 2,
            "remove": [1],
            "note": "要比较生产效率，还需要核对同期产量、投入和统计口径。",
        }
        wrong = dict(replacement, note="统计资料显示2024年并网容量合计为30 GW。")
        with patch.object(report, "answer", return_value={"edits": [wrong]}):
            self.assertEqual(
                report.review_scope({}, "比较效率", "统计口径", original, evidence, []), original[:1]
            )
        with patch.object(report, "answer", return_value={"edits": [replacement]}):
            updated = report.review_scope({}, "比较效率", "统计口径", original, evidence, [])
        self.assertEqual(updated[0], original[0])
        self.assertEqual(updated[1], replacement["note"] + " [E1]")

    def test_markdown_export_has_one_contiguous_table(self):
        row = dict(
            ref="E1",
            title="累计装机",
            metric="累计装机",
            unit="GW",
            region="China",
            digest="a" * 64,
            publisher="发布方",
            url="https://example.org",
            locator="China",
            series=[[2020, "1"], [2021, "2"]],
        )
        plan = dict(
            title="装机", sections=["变化"], regions=["China"], keywords=["装机"], start=2020, end=2021
        )
        md, trace = report.assemble(plan, [row], [], [["章节 [E1]"]], ["摘要 [E1]"], [], 800, "research")
        self.assertIn("| 年份 | China |\n| --- | ---: |\n| 2020 | 1 |\n| 2021 | 2 |", md)
        self.assertIn("| 2021 | 2 |", trace["protected_lines"])

    def test_summary_can_only_select_existing_measurements(self):
        first = "官方分省表记录浙江年末累计装机为20 GW，这只能用来说明装机规模。 [E1]"
        second = "浙江的全年新增与九月底累计各有时间口径，需要单独解读。 [E2]"
        chapters = [[first], [second]]
        with patch.object(report, "answer", return_value={"selected": [777]}):
            published = report.summarize_report({}, {}, ["统计", "口径"], chapters, 120)
        self.assertEqual(published, [first, second])

    def test_stage_trace_records_usage_and_resume_failure_without_prompts(self):
        checkpoint = {}
        saved = []
        original = {"MODEL_API_KEY": "fake"}
        with (
            self.assertRaises(AppError),
            report.record_stage(original, checkpoint, saved.append, "draft", "并网") as cfg,
        ):
            cfg["_research_observer"]({"total_tokens": 40})
            cfg["_research_observer"](None)
            raise AppError("中断")
        stage = saved[0]["operations"][0]
        self.assertEqual(
            (stage["status"], stage["model_requests"], stage["reported_tokens"]["total_tokens"]),
            ("interrupted", 2, 40),
        )
        self.assertNotIn("fake", json.dumps(saved))

    def test_annual_cohort_keeps_latest_source_and_excludes_quarter(self):
        rows = []
        for region in ("浙江", "江苏", "江西"):
            for year in range(2021, 2026):
                rows.append(
                    dict(
                        ref=f"E{len(rows) + 1}",
                        title=f"{year} 年原表",
                        locator=region,
                        metric="分布式光伏年末累计并网容量",
                        unit="万千瓦",
                        region=region,
                        series=[(year, "14")],
                    )
                )
        rows.append(
            dict(
                ref="E99",
                title="2026年前三季度",
                locator="江苏",
                metric="分布式光伏截至九月底累计并网容量",
                unit="万千瓦",
                region="江苏",
                series=[(2026, "15")],
            )
        )
        chosen = report.choose_evidence(rows, "浙江和江苏的年度分布式光伏比较")
        self.assertEqual(
            {(r["region"], r["series"][0][0]) for r in chosen},
            {(region, year) for region in ("浙江", "江苏") for year in range(2021, 2026)},
        )

    def test_tables_keep_trade_products_separate(self):
        records = [
            dict(
                ref=f"E{i}",
                metric=f"{label}出口额（HS {product}，对{market}，现价）",
                unit="亿美元",
                region="China",
                series=[(2025, value)],
            )
            for i, (product, label, market, value) in enumerate(
                [
                    ("854143", "光伏组件", "世界", "4"),
                    ("854143", "光伏组件", "荷兰", "1"),
                    ("854142", "未组装光伏电池片", "世界", "10"),
                    ("854142", "未组装光伏电池片", "荷兰", "3"),
                ],
                1,
            )
        ]
        plan = dict(trade_products=["854143", "854142"], trade_partners=["Netherlands"], sections=[])
        tables = report.report_tables(plan, records, set(), 2500)
        self.assertIn("| 年份 | 世界 | 荷兰 |", tables[0])
        self.assertIn("| 2025 | 4 | 1 |", tables[0])
        self.assertIn("| 2025 | 10 | 3 |", tables[1])
        self.assertEqual(report.chart_data(tables[1])["table_number"], 2)

    def test_quarterly_revision_cannot_lose_its_negative_sign(self):
        catalog = {
            "E1": {"text": "2026年前三季度，江西集中式新增并网容量为-122.8 万千瓦。", "title": "原表"}
        }
        submitted = {
            "paragraphs": [{"text": "原表记录江西的集中式新增并网容量为122.8万千瓦。", "refs": ["E1"]}]
        }
        with self.assertRaisesRegex(ValueError, "数值和单位"):
            report.validate_paragraphs(submitted, catalog, 1, 120)

    def test_citations_and_quantities_must_match(self):
        for text, refs in [
            ("按年度统计，累计装机已经达到20 TWh，值得核对。", ["E1"]),
            ("按年度统计，累计装机已经达到30 GW，值得核对。", ["E1"]),
            ("按年度统计，累计装机已经达到20 GW，值得核对。", ["E9"]),
        ]:
            with self.subTest(text=text, refs=refs), self.assertRaises(ValueError):
                report.validate_paragraphs(
                    {"paragraphs": [dict(text=text, refs=refs)]}, self.sample, 1, 120
                )

    def test_editor_preserves_citations_numbers_units_and_table(self):
        md = "# 题目\n\n在原始数据中，累计装机达到20 GW，年度统计给出了原文出处。 [E1]\n\n| 年份 | 指标 |\n"
        self.assertGreater(report.editorial_revision(md, md.replace("在原始数据中", "按公布口径")), 15)
        for replacement in (
            md.replace("20 GW", "20 TWh"),
            md.replace("[E1]", "[E9]"),
            md.replace("| 年份", "| 地区"),
        ):
            with self.assertRaises(AppError):
                report.editorial_revision(md, replacement)

    def test_comparison_table_preserves_gaps(self):
        rows = [
            dict(ref="E1", metric="发电量", unit="TWh", region="China", series=[[2020, "1"], [2021, "2"]]),
            dict(ref="E2", metric="发电量", unit="TWh", region="Germany", series=[[2021, "3"]]),
        ]
        lines = report.study_table(
            dict(title="发电量", regions=["China", "Germany"], keywords=[]), rows, {"E1", "E2"}
        )
        self.assertIn("| 2020 | 1 | — |", lines)
        self.assertIn("| 2021 | 2 | 3 |", lines)
        chart = report.chart_data(lines)
        self.assertIn("2021 年", chart["title"])
        self.assertEqual([p["value"] for p in chart["points"]], ["2", "3"])
        self.assertIsNone(report.chart_data(lines[:-1]))

    def test_planning_never_launches_before_confirmation(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = Service(
            Store(Path(tmp.name) / "test.db"),
            dict(MODEL_NAME="test", MODEL_API_KEY="dummy", MODEL_ENDPOINT="https://example.org/chat"),
        )
        app = Research(service)
        self.addCleanup(app.pool.shutdown)
        with (
            patch.object(report, "discuss", return_value="讨论地区和期限"),
            patch.object(app, "launch") as launch,
        ):
            task = app.start({"workflow": "discuss", "question": "比较中国与德国", "target": 1600})
            self.assertEqual(task["status"], "planning")
            task = app.plan_turn(task["id"], {"question": "正文改为2200字", "target": None})
            self.assertEqual(task["spec"]["target"], 2200)
            task = app.revise_scope(
                task["id"], dict(scope="浙江和江苏", target=2100, style="market", outline=["新增", "存量"])
            )
            self.assertEqual(task["spec"]["outline"], ["新增", "存量"])
            launch.assert_not_called()
            app.begin(task["id"])
            launch.assert_called_once_with(task["id"])
            with self.assertRaises(AppError):
                app.begin(task["id"])
            with self.assertRaises(AppError):
                app.revise_scope(task["id"], dict(scope="其他地区", target=2100, style="market"))

    def test_second_worker_detects_lease_and_recovers_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = Service(Store(Path(tmp) / "test.db"), {})
            first, second = Research(service), Research(service)
            self.addCleanup(first.pool.shutdown)
            self.addCleanup(second.pool.shutdown)
            lease = first.acquire_run("task")
            try:
                self.assertTrue(second.other_worker("task"))
                with self.assertRaises(AppError):
                    second.acquire_run("task")
            finally:
                lease.close()
            self.assertFalse(second.other_worker("task"))

    def test_direct_mode_accepts_free_scope_and_explicit_length(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = Research(
            Service(
                Store(Path(tmp.name) / "test.db"),
                dict(MODEL_NAME="test", MODEL_API_KEY="dummy", MODEL_ENDPOINT="https://example.org/chat"),
            )
        )
        self.addCleanup(app.pool.shutdown)
        with patch.object(app, "launch") as launch:
            job = app.start({"workflow": "direct", "question": "给园区写10000字", "scope": "供需与并网"})
            self.assertEqual(job["spec"]["target"], 10000)
            self.assertEqual(job["spec"]["scope"], "供需与并网")
            launch.assert_called_once()
            with self.assertRaises(AppError):
                app.start({"workflow": "direct", "question": "测试", "target": 10001})
