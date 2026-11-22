"""Counterexamples around evidence provenance, length, and the two entry paths."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.error import HTTPError
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_app.errors import AppError
from report_app import eurostat, irena, nbs
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

    def test_nbs_keeps_month_ytd_and_published_yoy_separate(self):
        raw = (
            '<meta name="ArticleTitle" content="2026年1—4月份规模以上工业增加值增长5.6%">'
            '<table><tr><th>指标</th><th>4月</th><th>1—4月</th></tr>'
            '<tr><th>绝对量</th><th>同比增长（%）</th><th>绝对量</th><th>同比增长（%）</th></tr>'
            '<tr><td>太阳能发电量（亿千瓦时）</td><td>571</td><td>7.1</td><td>2045</td><td>9.8</td></tr>'
            '<tr><td>太阳能电池（光伏电池）（万千瓦）</td><td>6494</td><td>-25.6</td><td>24150</td><td>-15.3</td></tr>'
            '</table>'
        ).encode()
        rows, notes = nbs.rows(raw, year=2026, month=4)
        self.assertEqual(rows[0], ("China", 2026, nbs.LEVEL + "（4月）", "亿千瓦时", "571"))
        self.assertEqual(rows[3], ("China", 2026, nbs.GROWTH + "（1—4月）", "%", "9.8"))
        self.assertEqual(rows[-1], ("China", 2026, nbs.CELL_GROWTH + "（1—4月）", "%", "-15.3"))
        self.assertIn("同比为原表", notes[0][1])
        with self.assertRaises(ValueError):
            nbs.rows(raw, year=2025, month=4)
        intake = raw[raw.index(b"<table>"):]
        with self.assertRaises(ValueError):
            nbs.rows(raw + intake.replace(b"2045", b"2222"), year=2026, month=4)

    def test_national_release_distinguishes_pv_generation_and_wind_solar_total(self):
        raw = (
            '<meta name="PubDate" content="2026-07-30 13:53:27">'
            '<p>今年上半年，全国风光发电量合计1.25万亿千瓦时。'
            '今年上半年，全国光伏累计发电量6555亿千瓦时，全国光伏发电利用率91.4%。</p>'
        ).encode()
        records, _ = release_rows(raw, operation=(2026, "上半年"))
        self.assertEqual(records, [
            ("China", 2026, "全国光伏发电量（国家能源局，上半年）", "亿千瓦时", "6555"),
            ("China", 2026, "全国光伏发电利用率（国家能源局，上半年）", "%", "91.4"),
        ])
        with self.assertRaises(ValueError):
            release_rows(raw, operation=(2025, "前三季度"))

    def test_monthly_table_sorts_joint_period_before_march_and_excludes_it_from_chart(self):
        def source(month, val, ref):
            return dict(
                ref=ref, metric=f"{nbs.LEVEL}（{month}月）", region="China", unit="亿千瓦时",
                series=[(2026, val)],
            )

        records = [
            source("3", "547", "E1"), source("1—2", "920", "E2"), source("4", "571", "E3"),
        ]
        table = report.nbs_table(records, 1)
        self.assertEqual(table[4], "| 2026年1—2月 | 920 | — |")
        self.assertEqual([p["value"] for p in report.chart_data(table)["points"]], ["547", "571"])

    def test_explicit_month_gets_the_matching_absolute_value_and_published_growth(self):
        def source(year, period, metric, value, unit, ref):
            return dict(
                ref=ref, metric=f"{metric}（{period}月）", region="China", unit=unit,
                series=[(year, value)], text=f"{year}年为{value}{unit}。", title="官方原表",
                locator="China", publisher="国家统计局", source=year * 100 + int(period.split("—")[-1]),
            )

        records = [
            source(2025, "10", nbs.LEVEL, "394", "亿千瓦时", "E1"),
            source(2026, "1—10", nbs.LEVEL, "6105", "亿千瓦时", "E2"),
            source(2026, "10", nbs.LEVEL, "594", "亿千瓦时", "E3"),
            source(2026, "10", nbs.GROWTH, "31", "%", "E4"),
            source(2026, "1—10", nbs.GROWTH, "14.3", "%", "E5"),
        ]
        title = "2026年10月和1—10月太阳能发电量"
        self.assertEqual(report.calendar_periods("2026年8—10月"), {"8月", "9月", "10月"})
        self.assertIn(report.choose_evidence(records, title)[0]["ref"], {"E2", "E3"})
        outline = report.ensure_nbs_measurements(title, [], records)
        self.assertTrue(any("594亿千瓦时" in p and "31%" in p for p in outline))
        self.assertTrue(any("6105亿千瓦时" in p and "14.3%" in p for p in outline))
        self.assertFalse(any("394" in p for p in outline))
        self.assertEqual(report.ensure_nbs_measurements(title, outline, records), outline)

    def test_explicit_source_scope_never_reuses_other_catalogs(self):
        self.ingest()
        plan = dict(
            title="比较装机与出口",
            regions=["China"],
            keywords=["装机", "出口"],
            start=2020,
            end=2021,
            source_groups=["grid"],
        )
        with (
            patch.object(self.library, "province_jobs", return_value=[]),
            patch.object(self.library, "release_jobs") as release,
            patch.object(self.library, "collect_irena") as published,
            patch.object(self.library, "owid_jobs") as owid,
        ):
            rows, trace = self.library.collect(plan)
        self.assertEqual((rows, trace), ([], []))
        release.assert_not_called()
        owid.assert_not_called()
        published.assert_not_called()

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

    def test_eurostat_never_sums_an_incomplete_month_window(self):
        dimensions = dict(
            zip(
                eurostat.DIMENSIONS,
                [
                    ["M"],
                    ["EU27_2020"],
                    ["CN"],
                    ["85414300"],
                    ["1"],
                    ["VALUE_IN_EUROS"],
                    ["2025-01", "2025-02", "2026-01", "2026-02"],
                ],
            )
        )
        payload = {
            "source": "ESTAT",
            "id": list(dimensions),
            "size": [len(v) for v in dimensions.values()],
            "value": {"0": 100000000, "1": 200000000, "3": 700000000},
            "dimension": {
                key: {"category": {"index": {value: i for i, value in enumerate(values)}}}
                for key, values in dimensions.items()
            },
        }
        result, _ = eurostat.rows(
            json.dumps(payload),
            expected_reporters={"EU27_2020": "European Union"},
            code="85414300",
            start_year=2025,
            through=date(2026, 2, 28),
            months=2,
        )
        combined = [
            (year, amount)
            for _, year, metric, unit, amount in result
            if "1—2月" in metric and unit == "亿欧元"
        ]
        self.assertEqual(combined, [(2025, "3")])

    def test_comtrade_uses_one_product_per_preview(self):
        jobs = trade_jobs(
            dict(
                title="光伏出口",
                keywords=["组件", "电池片"],
                start=2024,
                end=2024,
                regions=["China"],
                trade_partners=["India", "Brazil"],
                trade_products=["854143", "854142"],
            )
        )
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all("partnerCode=0%2C76%2C699" in job[0] for job in jobs))
        self.assertEqual([job[0].split("cmdCode=")[1].split("&")[0] for job in jobs], ["854143", "854142"])


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
        with patch.object(report, "answer", return_value=plan):
            limited = report.make_plan({}, "只用国家能源局分省原表", "", [], 2000)
        self.assertEqual(limited["source_groups"], ["grid"])

    def test_excluding_generation_does_not_request_its_monthly_table(self):
        plan = dict(
            title="全国光伏电池生产", regions=["China"], start=2025, end=2026,
            keywords=["光伏电池", "产量", "月表"], sections=["光伏电池产量"],
        )
        with patch.object(report, "answer", return_value=plan):
            actual = report.make_plan(
                {}, "比较光伏电池产量，不讨论发电量。", "", [], 1200,
                ["两年10月光伏电池产量"], ["nbs"],
            )
        self.assertTrue(actual["cell_requested"])
        self.assertFalse(actual["nbs_generation_requested"])

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

    def test_observation_gate_detects_swapped_year_values_in_the_same_reference(self):
        catalog = {
            "E1": dict(
                region="浙江", metric="分布式光伏新增并网容量", unit="万千瓦",
                series=[(2024, "1204"), (2025, "1390.5")], title="浙江年度原表",
                text="2024年为1204万千瓦，2025年为1390.5万千瓦。",
            )
        }
        valid = {"text": "2025年浙江的分布式光伏新增并网容量为1390.5万千瓦。", "refs": ["E1"]}
        self.assertIn("1390.5万千瓦", report.validate_paragraphs({"paragraphs": [valid]}, catalog, 0, 50)[0])
        invalid = dict(valid, text=valid["text"].replace("1390.5", "1204"))
        with self.assertRaisesRegex(ValueError, "地区或年度"):
            report.validate_paragraphs({"paragraphs": [invalid]}, catalog, 0, 50)

    def test_trade_fallback_uses_the_years_named_in_the_chapter(self):
        row = dict(
            ref="E1", region="European Union", unit="亿欧元",
            metric="自中国进口光伏组件额（Eurostat，1—9月）",
            series=[(2022, "150.9124"), (2025, "58.524"), (2026, "61.9405")],
        )
        years = report.section_years("欧盟2025及2026年1—9月自中国进口组件")
        self.assertEqual(years, {2025, 2026})
        _, sentence = report.anchors_for([row], years)["K1"]
        self.assertIn("58.524", sentence)
        self.assertIn("61.9405", sentence)
        self.assertNotIn("2022", sentence)
        self.assertEqual(report.section_years("2021—2025年连续数据"), set(range(2021, 2026)))

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
        self.assertIn("| 年份 | 中国 |\n| --- | ---: |\n| 2020 | 1 |\n| 2021 | 2 |", md)
        self.assertIn("| 2021 | 2 |", trace["protected_lines"])

    def test_summary_can_only_select_existing_measurements(self):
        first = "官方分省表记录浙江年末累计装机为20 GW，这只能用来说明装机规模。 [E1]"
        second = "浙江的全年新增与九月底累计各有时间口径，需要单独解读。 [E2]"
        chapters = [[first], [second]]
        with patch.object(report, "answer", return_value={"selected": [777]}):
            published = report.summarize_report({}, {}, ["统计", "口径"], chapters, 120)
        self.assertEqual(published, [first, second])

    def test_summary_drops_repeated_numeric_finding_and_keeps_main_finding(self):
        schedule = "自2027年4月1日起，对光伏电池按照2%税率征收消费税。 [E1]"
        duplicate = "公告规定自2027年4月1日起对光伏电池按照2%税率征收消费税。 [E2]"
        exception = "享受减免的产品应符合对应国家标准，首次申报前还需取得检测报告。 [E3]"
        chapters = [[schedule], [duplicate, exception]]
        with patch.object(report, "answer", return_value={"selected": [1, 2]}):
            result = report.summarize_report({}, {}, ["实施日期", "检测条件"], chapters, 120)
        self.assertEqual(result, [schedule, exception])

    def test_tax_schedule_keeps_the_rates_with_both_effective_dates(self):
        statute = (
            "二、自2027年4月1日起，对光伏电池（又称太阳能电池）按照2%税率征收消费税；"
            "自2028年4月1日起，对光伏电池按照4%税率征收消费税。"
        )
        evidence = [{"title": "光伏电池消费税公告", "ref": "E1", "text": statute}]
        self.assertEqual(report.anchors_for(evidence)["K1"][1], statute.rstrip("。"))
        chapter = ["自2028年4月1日起，对光伏电池按照4%税率征收消费税。 [E1]"]
        title = "光伏电池消费税税率"
        revised = report.ensure_pv_excise_schedule(title, chapter, evidence)
        self.assertIn("2027年4月1日起按2%", revised[0])
        self.assertIn("2028年4月1日起按4%", revised[0])
        self.assertEqual(report.ensure_pv_excise_schedule(title, revised, evidence), revised)

    def test_stage_trace_records_usage_and_resume_failure_without_prompts(self):
        checkpoint = {}
        saved = []
        original = {"MODEL_API_KEY": "fake"}
        with (
            self.assertRaises(AppError),
            report.record_stage(
                original, checkpoint, lambda data: saved.append(json.loads(json.dumps(data))), "draft", "并网"
            ) as cfg,
        ):
            cfg["_research_observer"]({"total_tokens": 40})
            cfg["_research_observer"](None)
            raise AppError("中断")
        self.assertEqual(saved[0]["pending_stage"]["label"], "并网")
        stage = saved[-1]["operations"][0]
        self.assertEqual(
            (stage["status"], stage["model_requests"], stage["reported_tokens"]["total_tokens"]),
            ("interrupted", 2, 40),
        )
        self.assertNotIn("fake", json.dumps(saved))
        report.record_worker_restart(saved[0])
        interrupted = saved[0]["operations"][0]
        self.assertEqual(interrupted["error_code"], "worker_restart")
        self.assertNotIn("pending_stage", saved[0])
        self.assertNotIn("model_requests", interrupted)

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
