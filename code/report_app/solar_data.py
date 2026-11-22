"""Versioned solar evidence from statistical releases and machine-readable data."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from hashlib import sha256
from decimal import Decimal
from functools import partial
from html.parser import HTMLParser
import io
import json
import re
import ssl
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .errors import AppError
from . import irena
from . import eurostat
from . import nbs
from . import studies
from .manufacturing import RELEASES as MANUFACTURING_RELEASES, manufacturing_observations
from .policy import POLICIES, parse_policy
from .store import now
from .trade import TRADE, trade_jobs
from .utilization import AREAS as GRID_AREAS, SOURCES as UTILIZATION_SOURCES, utilization_rows
from .provinces import (
    HALF_YEAR_TABLES,
    HTML_QUARTER_TABLES,
    HTML_TABLES,
    REGIONS,
    TABLES,
    html_provincial_rows,
    provincial_rows,
    table_caveat,
)

INDEX = "https://www.nea.gov.cn/sjzz/xny/"
CAPACITY = "https://ourworldindata.org/grapher/installed-solar-pv-capacity"
ENERGY = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"
RELEASES = {
    "2026年前三季度可再生能源并网运行情况": "https://www.nea.gov.cn/20261030/28a6f818b9f843a995952940301590bd/c.html",
    "2026年上半年可再生能源并网运行情况": "https://www.nea.gov.cn/20260730/3ce671c387574eeeb120fc3825be0399/c.html",
    "2025年可再生能源并网运行情况": "https://www.nea.gov.cn/20260212/742b8c6a078347b0b39de676c05c5d58/c.html",
    "2024年可再生能源并网运行情况": "https://www.nea.gov.cn/20250221/e10f363cabe3458aaf78ba4558970054/c.html",
}
NATIONAL_OPERATIONS = {
    (2024, "上半年"): "https://www.nea.gov.cn/2024-08/02/c_1310783697.htm",
    (2024, "前三季度"): "https://www.nea.gov.cn/2024-10/31/c_1212406333.htm",
    (2024, "全年"): RELEASES["2024年可再生能源并网运行情况"],
    (2025, "上半年"): "https://www.nea.gov.cn/20250731/36b5b3b74d344325bb67f38b8e943c18/c.html",
    (2025, "前三季度"): "https://www.nea.gov.cn/20251031/7be6728f6d8a48a4955a24a45013b37f/c.html",
    (2025, "全年"): RELEASES["2025年可再生能源并网运行情况"],
    (2026, "上半年"): RELEASES["2026年上半年可再生能源并网运行情况"],
    (2026, "前三季度"): RELEASES["2026年前三季度可再生能源并网运行情况"],
}
SOURCE_GROUPS = {
    "grid": "国家能源局并网原表",
    "utilization": "光伏发电利用率",
    "manufacturing": "中国光伏制造与贸易发布",
    "trade": "联合国 Comtrade",
    "eurostat": "Eurostat 欧洲进口统计",
    "international": "IRENASTAT 与 OWID",
    "policy": "国家及省级政策原文",
    "releases": "国家能源局运行发布",
    "nbs": "国家统计局规上工业月表",
    "studies": "IEA PVPS 与 IRENA 研究报告",
}
HOSTS = {
    "www.nea.gov.cn",
    "www.miit.gov.cn",
    "wap.miit.gov.cn",
    "www.stats.gov.cn",
    "ourworldindata.org",
    "raw.githubusercontent.com",
    "comtradeapi.un.org",
    "www.ciaps.org.cn",
    "www.cpem.org.cn",
    "www.cccme.org.cn",
    "www.ndrc.gov.cn",
    "zfxxgk.ndrc.gov.cn",
    "zfxxgk.nea.gov.cn",
    "fzggw.jiangsu.gov.cn",
    "zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn",
    "public.solarbe.com",
    "pxweb.irena.org",
    "www.irena.org",
    "iea-pvps.org",
    "ec.europa.eu",
    "szs.mof.gov.cn",
}
METRICS = {
    "solar_electricity": ("太阳能发电量", "TWh"),
    "solar_share_elec": ("太阳能占发电量比重", "%"),
    "solar_elec_per_capita": ("人均太阳能发电量", "kWh/人"),
}
GRAPHER = "https://ourworldindata.org/grapher/"
COSTS = {
    "solar-pv-prices": (
        "光伏组件基准价格",
        "Solar PV module cost",
        "Solar photovoltaic module price",
        "constant 2025 US$ per watt",
        "2025年不变美元/W",
        "2010年起取欧洲市场基准，不含安装成本",
    ),
    "levelized-cost-of-energy": (
        "光伏平准化发电成本",
        "Solar photovoltaic",
        "Solar photovoltaic levelized cost of energy",
        "constant 2025 US$ per kilowatt-hour",
        "2025年不变美元/kWh",
        "新投运公用事业规模项目，加权平均",
    ),
}
CAP_METRIC = ("太阳能累计装机（含光热）", "GW")


def permitted(url):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.hostname in HOSTS
        and parts.port in (443, None)
        and not parts.username
        and not parts.password
    )


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not permitted(newurl):
            raise ValueError("数据源重定向至未登记地址")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, *, data=None):
    if not permitted(url):
        raise ValueError("数据源地址无效")
    headers = {"User-Agent": "PVResearch/1.0 (educational data analysis)"}
    if data is not None:
        parts = urlsplit(url)
        if parts.hostname != "pxweb.irena.org" or not parts.path.startswith("/api/v1/en/IRENASTAT/"):
            raise ValueError("该数据源未登记查询接口")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers)
    try:
        response = build_opener(PublicRedirect()).open(request, timeout=25)
    except URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        try:
            import truststore
        except ImportError:
            raise error from None
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        response = build_opener(PublicRedirect(), HTTPSHandler(context=context)).open(request, timeout=25)
    with response:
        raw = response.read(24_000_001)
    if len(raw) > 24_000_000:
        raise ValueError("下载内容过大")
    return raw


class ReleasePage(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.meta = {}
        self.paragraphs, self.links = [], []
        self.parts, self.anchor = None, None
        self.feed(raw.decode("utf-8-sig"))
        self.close()

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "meta":
            self.meta[(fields.get("name") or "").lower()] = fields.get("content", "")
        if tag == "p":
            self.parts = []
        if tag == "a":
            self.anchor = [fields.get("href", ""), []]

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)
        if self.anchor:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.parts is not None:
            self.paragraphs.append(" ".join("".join(self.parts).split()))
            self.parts = None
        if tag == "a" and self.anchor:
            self.links.append((self.anchor[0], "".join(self.anchor[1]).strip()))
            self.anchor = None


def trend(samples, unit):
    if len(samples) < 2:
        return ""
    (start, a), (end, b) = samples[0], samples[-1]
    first, last = Decimal(a), Decimal(b)
    if unit == "%":
        return f"由首末观测值相减，{start}至{end}年变化{last - first:+.2f}个百分点。"
    if not first:
        return ""
    change = (last / first - 1) * 100
    return f"按（末值÷初值－1）计算，{start}至{end}年累计变化{change:+.1f}%，并非年增速。"


def match_score(text, words):
    return sum(1 for word in words if word and word.lower() in text.lower())


def display_value(raw, places):
    value = Decimal(raw)
    rounded = format(value, f".{places}f")
    if value and Decimal(rounded) == 0:
        return format(value.normalize(), "f")
    return rounded.rstrip("0").rstrip(".") or "0"


class SolarLibrary:
    def __init__(self, store, downloader=fetch):
        self.store, self.download = store, downloader
        with closing(store.connect()) as db, db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS solar_sources(
                 id INTEGER PRIMARY KEY, url TEXT, digest TEXT, title TEXT, publisher TEXT,
                 origin TEXT, fetched TEXT, checked TEXT, UNIQUE(url,digest));
              CREATE TABLE IF NOT EXISTS solar_observations(
                 source INTEGER, region TEXT, year INTEGER, metric TEXT, unit TEXT, value TEXT,
                 PRIMARY KEY(source,region,year,metric));
              CREATE INDEX IF NOT EXISTS solar_by_scope ON solar_observations(region,year,source);
              CREATE TABLE IF NOT EXISTS solar_rate(provider TEXT PRIMARY KEY, next_request REAL, cooldown REAL);
              CREATE TABLE IF NOT EXISTS solar_passages(
                 source INTEGER, locator TEXT, body TEXT, PRIMARY KEY(source,locator));
            """)
            db.execute("BEGIN IMMEDIATE")
            if "raw_digest" not in {row["name"] for row in db.execute("PRAGMA table_info(solar_sources)")}:
                db.execute("ALTER TABLE solar_sources ADD COLUMN raw_digest TEXT")

    def trade_download(self, url):
        with closing(self.store.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT next_request,cooldown FROM solar_rate WHERE provider='comtrade'"
            ).fetchone()
            current = time.time()
            if row and row[1] > current:
                raise ValueError("Comtrade 限流，稍后再更新")
            slot = max(current, row[0]) if row else current
            db.execute("INSERT OR REPLACE INTO solar_rate VALUES('comtrade',?,0)", (slot + 6,))
        time.sleep(max(0, slot - current))
        # Another task may have received a rate limit while we waited for our slot.
        with closing(self.store.connect()) as db:
            cooldown = db.execute("SELECT cooldown FROM solar_rate WHERE provider='comtrade'").fetchone()[0]
        if cooldown > time.time():
            raise ValueError("Comtrade 限流，稍后再更新")
        try:
            return self.download(url)
        except HTTPError as exc:
            if exc.code == 429:
                delay = exc.headers.get("Retry-After", "60")
                try:
                    until = time.time() + max(1, int(delay))
                except ValueError:
                    try:
                        until = parsedate_to_datetime(delay).timestamp()
                    except (TypeError, ValueError):
                        until = time.time() + 60
                with closing(self.store.connect()) as db, db:
                    db.execute(
                        "UPDATE solar_rate SET cooldown=MAX(cooldown,?) WHERE provider='comtrade'", (until,)
                    )
            raise

    def ingest(self, url, title, publisher, origin, parser, schema="", loader=None):
        try:
            if url.startswith(TRADE + "?"):
                with closing(self.store.connect()) as db:
                    recent = db.execute(
                        """SELECT id FROM solar_sources WHERE url=? AND
                                    julianday('now')-julianday(checked)<7 ORDER BY checked DESC,id DESC LIMIT 1""",
                        (url,),
                    ).fetchone()
                if recent:
                    return recent[0], "复用近七日取得的年度贸易数据"
                raw = self.trade_download(url)
            else:
                raw = (loader or self.download)(url)
            raw_digest = sha256(raw).hexdigest()
            digest = sha256(f"{raw_digest}:{schema}".encode()).hexdigest() if schema else raw_digest
            with closing(self.store.connect()) as db, db:
                row = db.execute(
                    "SELECT id FROM solar_sources WHERE url=? AND digest=?", (url, digest)
                ).fetchone()
                if row:
                    db.execute("UPDATE solar_sources SET checked=? WHERE id=?", (now(), row[0]))
                    return row[0], "联网核对，内容未变"
            observations, passages = parser(raw)
            if not observations and not passages:
                raise ValueError("本页无可解析的统计指标或相关原文")
            stamp = now()
            with closing(self.store.connect()) as db, db:
                db.execute(
                    """INSERT OR IGNORE INTO solar_sources
                       (url,digest,title,publisher,origin,fetched,checked,raw_digest) VALUES(?,?,?,?,?,?,?,?)""",
                    (url, digest, title, publisher, origin, stamp, stamp, raw_digest),
                )
                sid = db.execute(
                    "SELECT id FROM solar_sources WHERE url=? AND digest=?", (url, digest)
                ).fetchone()[0]
                db.executemany(
                    "INSERT OR IGNORE INTO solar_observations VALUES(?,?,?,?,?,?)",
                    ((sid, *o) for o in observations),
                )
                db.executemany(
                    "INSERT OR IGNORE INTO solar_passages VALUES(?,?,?)", ((sid, *p) for p in passages)
                )
            return sid, "联网入库"
        except (OSError, ValueError, KeyError, csv.Error) as exc:
            with closing(self.store.connect()) as db:
                cache = db.execute(
                    """SELECT id FROM solar_sources WHERE url=? AND
                       (?='' OR EXISTS(SELECT 1 FROM solar_observations WHERE source=solar_sources.id))
                       ORDER BY checked DESC,id DESC LIMIT 1""",
                    (url, schema),
                ).fetchone()
            return (
                (cache[0], "联网失败，采用已存快照")
                if cache
                else (None, "未取得可用数据：" + str(exc)[:95])
            )

    def collect_manufacturing(self, plan, *, force=False):
        if "China" not in plan["regions"]:
            return []
        intent = plan["title"] + " " + " ".join(plan["keywords"])
        if not force and not any(
            word in intent for word in ("产量", "制造", "多晶硅", "硅片", "组件", "出口", "产业链")
        ):
            return []
        results = []
        for year, (publisher, primary, mirror) in MANUFACTURING_RELEASES.items():
            if not plan["start"] <= year <= plan["end"]:
                continue
            title = f"{year} 年中国光伏制造与贸易统计"
            parser = partial(manufacturing_rows, year=year)
            key, message = self.ingest(primary, title, publisher, primary, parser, "manufacturing-v1")
            if key is None and mirror:
                key, message = self.ingest(mirror, title, publisher, primary, parser, "manufacturing-v1")
                if key is not None:
                    message = "从转载页获取，原发布页无法直连 · " + message
            results.append((key, {"source": title, "result": message, "url": primary}))
        return results

    def collect_irena(self):
        try:
            table = irena.latest_country_table(self.download(irena.DIRECTORY))
            query = irena.capacity_query(self.download(table))
        except (OSError, ValueError, KeyError, TypeError):
            with closing(self.store.connect()) as db:
                saved = db.execute("""SELECT id FROM solar_sources WHERE publisher='IRENASTAT'
                                    ORDER BY checked DESC,id DESC LIMIT 1""").fetchone()
            if saved:
                return saved[0], "数据目录读取失败，采用已存快照"
            return None, "未取得 IRENASTAT 最新装机数据表"
        return self.ingest(
            table,
            "IRENASTAT 年末光伏装机",
            "IRENASTAT",
            irena.LANDING,
            irena.capacity_rows,
            "pv-grid-v1",
            loader=lambda url: fetch(url, data=query),
        )

    def owid_jobs(self):
        jobs = [
            (
                ENERGY,
                "各国太阳能发电年度统计",
                "Our World in Data · Energy Data",
                "https://github.com/owid/energy-data",
                energy_rows,
            ),
            (
                CAPACITY + ".csv",
                "累计太阳能装机",
                "IRENA，经 Our World in Data 整理",
                CAPACITY,
                capacity_rows,
            ),
        ]
        for slug, (title, column, meta_col, expected_unit, unit, note) in COSTS.items():
            chart = GRAPHER + slug

            def parse_cost(
                raw,
                *,
                chart=chart,
                column=column,
                meta_col=meta_col,
                expected_unit=expected_unit,
                unit=unit,
                metric=title + "（" + note + "）",
            ):
                metadata = json.loads(self.download(chart + ".metadata.json"))
                if metadata["columns"][meta_col]["unit"] != expected_unit:
                    raise ValueError("来源的币值或单位已调整，需要核对")
                return grapher_rows(raw, column, metric, unit)

            jobs.append(
                (
                    chart + ".csv?csvType=full&useColumnShortNames=false",
                    title,
                    "IRENA 等，经 OWID 整理",
                    chart,
                    parse_cost,
                )
            )
        return jobs

    def province_jobs(self, plan):
        jobs = []
        half = plan.get("half_year_requested")
        quarter = plan.get("quarter_requested") or (plan["end"] >= 2026 and not half)
        for year, page in HTML_TABLES.items():
            if plan["start"] <= year <= plan["end"]:
                jobs.append(
                    (
                        page,
                        f"{year} 年光伏并网容量分省统计",
                        "国家能源局",
                        page,
                        partial(html_provincial_rows, year=year),
                        "provincial-html-v1",
                    )
                )
        for year, (page, filename, _) in TABLES.items():
            if year == 2026 and not quarter:
                continue
            if plan["start"] <= year <= plan["end"]:
                period = "年前三季度" if year == 2026 else "年"
                jobs.append(
                    (
                        urljoin(page, filename),
                        f"{year} {period}光伏并网容量分省统计",
                        "国家能源局",
                        page,
                        partial(provincial_rows, year=year),
                        "household-columns-v2" if year in (2024, 2025) else "",
                    )
                )
        if quarter:
            for year, page in HTML_QUARTER_TABLES.items():
                if plan["start"] <= year <= plan["end"]:
                    jobs.append(
                        (
                            page,
                            f"{year} 年前三季度光伏并网容量分省统计",
                            "国家能源局",
                            page,
                            partial(html_provincial_rows, year=year, quarter=True),
                            "provincial-html-v1",
                        )
                    )
        if half:
            for year, (page, filename, _) in HALF_YEAR_TABLES.items():
                if plan["start"] <= year <= plan["end"]:
                    jobs.append((
                        urljoin(page, filename), f"{year} 年上半年光伏并网容量分省统计",
                        "国家能源局", page, partial(provincial_rows, year=year, half_year=True),
                    ))
        return jobs

    def release_jobs(self, plan, notices):
        jobs = []
        words = plan["keywords"] + [str(year) for year in range(plan["start"], plan["end"] + 1)]
        links = dict(RELEASES)
        try:
            page = ReleasePage(self.download(INDEX))
            found = []
            for href, title in page.links:
                if not any(t in title for t in ("光伏", "可再生能源并网", "太阳能")) or "报告" in title:
                    continue
                url = urljoin(INDEX, href).replace("http://www.nea.gov.cn/", "https://www.nea.gov.cn/")
                if permitted(url) and urlsplit(url).path.endswith((".htm", ".html")):
                    found.append((title, url))
            eligible = [
                (title, url)
                for title, url in dict(found).items()
                if not re.search(r"20\d{2}", title)
                or any(plan["start"] <= int(y) <= plan["end"] for y in re.findall(r"20\d{2}", title))
            ]
            links.update(sorted(eligible, key=lambda v: -match_score(v[0], words))[:7])
            notices.append(
                {"source": "国家能源局发布目录", "result": f"联网发现 {len(dict(found))} 条相关发布"}
            )
        except (OSError, ValueError):
            notices.append({"source": "国家能源局发布目录", "result": "目录访问失败，尝试已登记的统计发布"})
        structured = set()
        if "China" in plan["regions"]:
            periods = {"全年"}
            if plan.get("half_year_requested"):
                periods.add("上半年")
            if plan.get("quarter_requested") or (plan["end"] >= 2026 and "上半年" not in periods):
                periods.add("前三季度")
            for (year, period), url in NATIONAL_OPERATIONS.items():
                if period in periods and plan["start"] <= year <= plan["end"]:
                    title = f"{year} 年{period}全国光伏发电运行统计"
                    parser = partial(release_rows, operation=(year, period))
                    jobs.append((url, title, "国家能源局", url, parser, "national-operation-v1"))
                    structured.add(url)
        for title, url in links.items():
            if url in {
                *structured,
                *HTML_TABLES.values(),
                *HTML_QUARTER_TABLES.values(),
                *(page for page, _, _ in TABLES.values()),
                *(page for page, _, _ in HALF_YEAR_TABLES.values()),
            }:
                continue
            years = [int(y) for y in re.findall(r"20\d{2}", title)]
            if years and not any(plan["start"] <= y <= plan["end"] for y in years):
                continue
            publisher = "工信部" if "miit.gov.cn" in url else "国家能源局"
            jobs.append((url, title, publisher, url, release_rows))
        return jobs

    def collect(self, plan):
        groups = set(plan.get("source_groups", []))
        auto = not groups
        jobs, notices, keys = [], [], []
        domestic = bool(set(plan["regions"]) & (REGIONS | GRID_AREAS | {"China"}))
        intent = plan["title"] + " " + " ".join([*plan["keywords"], *plan.get("sections", [])])
        if auto or "international" in groups:
            jobs.extend(self.owid_jobs())
        if domestic and (auto or "grid" in groups):
            jobs.extend(self.province_jobs(plan))
        if domestic and (auto or "releases" in groups):
            jobs.extend(self.release_jobs(plan, notices))
        if domestic and (
            "utilization" in groups
            or auto
            and any(word in intent for word in ("利用率", "消纳", "弃光", "限电", "弃电", "受限电量"))
        ):
            for years, publisher, origin, download, digest, loc in UTILIZATION_SOURCES:
                if any(plan["start"] <= year <= plan["end"] for year in years):
                    title = f"{years[-1]} 年光伏并网消纳年度统计"
                    parser = partial(utilization_rows, years=years, fingerprint=digest, location=loc)
                    jobs.append((download, title, publisher, origin, parser))
        if domestic and (auto or "policy" in groups):
            policy_topics = set(plan.get("policy_topics", []))
            for policy in POLICIES:
                if (
                    policy.year <= plan["end"]
                    and policy.region in {*plan["regions"], "China"}
                    and (not policy_topics or policy_topics.intersection(policy.topics))
                    and ("policy" in groups or match_score(intent, policy.topics))
                    and (
                        "出口退税" not in policy.topics or match_score(intent, policy.topics)
                    )
                ):
                    title = f"{policy.year} 年 {policy.title}"
                    jobs.append(
                        (
                            policy.document_url or policy.url,
                            title,
                            policy.issuer,
                            policy.url,
                            partial(parse_policy, policy=policy),
                            "policy-v2",
                        )
                    )
        if "eurostat" in groups or (
            auto and any(word in intent for word in ("进口", "贸易", "出口", "出海"))
        ):
            jobs.extend(eurostat.jobs(plan))
        if "China" in plan["regions"] and plan["end"] >= 2025 and (
            "nbs" in groups
            or auto and plan.get("cell_requested")
            or auto and "发电" in intent and (
                "规上" in intent or "规模以上" in intent or plan.get("monthly_requested")
            )
        ):
            try:
                publications = ReleasePage(self.download(nbs.INDEX)).links
            except (OSError, ValueError):
                publications = []
                notices.append(
                    {"source": "国家统计局数据发布目录", "result": "目录访问失败，尝试已登记的月表"}
                )
            jobs.extend(nbs.jobs(plan, publications))
        if auto or "studies" in groups:
            jobs.extend(studies.jobs(plan, force="studies" in groups))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda job: self.ingest(*job), jobs))
        # Batch partner rows within a reporter, product and year. Keep separate
        # requests sequential to respect the provider's limit.
        if auto or "trade" in groups:
            for trade in trade_jobs(plan):
                jobs.append(trade)
                results.append(self.ingest(*trade))
        for job, (sid, status) in zip(jobs, results):
            notices.append({"source": job[1], "result": status, "url": job[3]})
            if sid is not None:
                keys.append(sid)
        if auto or "manufacturing" in groups:
            for sid, notice in self.collect_manufacturing(plan, force="manufacturing" in groups):
                notices.append(notice)
                if sid is not None:
                    keys.append(sid)
        if (
            "international" in groups
            or auto
            and any(word in intent for word in ("装机", "离网", "接网", "发电容量"))
        ):
            sid, message = self.collect_irena()
            notices.append({"source": "IRENASTAT 年末光伏装机", "result": message, "url": irena.LANDING})
            if sid is not None:
                keys.append(sid)
            if set(plan["regions"]) & irena.REGIONS:
                title = "IRENA 全球及各区光伏年末装机（2026 年 3 月版）"
                sid, message = self.ingest(
                    irena.REGIONAL_REPORT,
                    title,
                    "IRENA",
                    irena.REGIONAL_REPORT,
                    irena.regional_capacity_rows,
                    "world-pv-v1",
                )
                notices.append({"source": title, "result": message, "url": irena.REGIONAL_REPORT})
                if sid is not None:
                    keys.append(sid)
        if domestic and (auto or "releases" in groups):
            active_urls = {n.get("url") for n in notices}
            for src in self.summary()["sources"]:
                years = re.findall(r"20\d{2}", src["title"])
                if (
                    not src["observations"]
                    and src["passages"]
                    and src["publisher"] == "国家能源局"
                    and src["url"].startswith("https://www.nea.gov.cn/")
                    and src["url"] not in active_urls
                    and years
                    and any(plan["start"] <= int(y) <= plan["end"] for y in years)
                    and match_score(src["title"], plan["keywords"])
                    and all(policy.url != src["url"] for policy in POLICIES)
                ):
                    keys.append(src["id"])
                    notices.append(dict(source=src["title"], result="复用历史资料快照", url=src["url"]))
        return self.select(list(dict.fromkeys(keys)), plan), notices

    def select(self, ids, plan):
        evidence = []
        with closing(self.store.connect()) as db:
            for sid in ids:
                src = dict(db.execute("SELECT * FROM solar_sources WHERE id=?", (sid,)).fetchone())

                def add(locator, text, **extra):
                    evidence.append(
                        dict(
                            ref=f"E{len(evidence) + 1}",
                            source=sid,
                            title=src["title"],
                            publisher=src["publisher"],
                            url=src["origin"],
                            data_url=src["url"],
                            digest=src["raw_digest"] or src["digest"],
                            fetched=src["fetched"],
                            locator=locator,
                            text=text,
                            **extra,
                        )
                    )

                for region in plan["regions"]:
                    rows = db.execute(
                        """SELECT year,metric,unit,value FROM solar_observations WHERE source=?
                        AND region=? AND year BETWEEN ? AND ? ORDER BY metric,year""",
                        (sid, region, plan["start"], plan["end"]),
                    ).fetchall()
                    by_metric = {}
                    for year, metric, unit, value in rows:
                        by_metric.setdefault((metric, unit), []).append((year, value))
                    for (metric, unit), series in by_metric.items():
                        if metric.startswith(nbs.CELL_LEVEL) and not plan.get("cell_requested"):
                            continue
                        if (
                            metric.startswith(nbs.LEVEL)
                            and plan.get("cell_requested")
                            and not plan.get("nbs_generation_requested")
                        ):
                            continue
                        euro_month = re.search(r"（Eurostat，(\d+)月）$", metric)
                        if euro_month and (
                            not plan.get("monthly_requested")
                            or plan.get("trade_window_fixed") and int(euro_month[1]) > plan["trade_months"]
                        ):
                            continue
                        if plan.get("trade_window_fixed") and metric.endswith("（Eurostat，全年）"):
                            continue
                        # Keep first, last and evenly spaced interior observations on long horizons.
                        selected = sorted(
                            {
                                round(i * (len(series) - 1) / min(9, max(1, len(series) - 1)))
                                for i in range(min(10, len(series)))
                            }
                        )
                        samples = [series[i] for i in selected]
                        digits = 4 if "美元" in unit or "欧元" in unit or unit in {"GWac", "GWdc"} else 2
                        shown = [(year, display_value(v, digits)) for year, v in samples]
                        data = "；".join(f"{year}年 {value} {unit}" for year, value in shown)
                        note = trend(samples, unit)
                        is_provincial = "光伏并网容量分省统计" in src["title"]
                        if is_provincial:
                            note += table_caveat(
                                region, samples[-1][0],
                                quarter="前三季度" in src["title"], half_year="上半年" in src["title"],
                            )
                        location = "总计" if region == "China" and is_provincial else region
                        add(
                            f"{location} · {metric} · {unit}",
                            f"{region}，{metric}：{data}。" + note,
                            series=shown,
                            raw_series=samples,
                            unit=unit,
                            metric=metric,
                            region=region,
                        )
                passages = list(db.execute(
                    "SELECT locator,body FROM solar_passages WHERE source=? ORDER BY rowid",
                    (sid,),
                ))
                ranked = sorted(passages, key=lambda p: -match_score(p[1], plan["keywords"]))
                if passages and any(policy.url == src["origin"] for policy in POLICIES):
                    # Keep the first substantive clause when narrowing a later section.
                    targets = [p for p in passages if re.search(r"到20\d{2}年.*(?:达到|建成)", p[1])]
                    ranked = list(dict.fromkeys([passages[0], *targets[:2], *ranked]))
                for loc, body in ranked[:8]:
                    add(loc, body)
        return evidence

    def browse(self, region, start, end, *, metric="", publisher=""):
        if not region or len(region) > 100 or not 1900 <= start <= end <= 2100:
            raise AppError("地区或年份范围无效")
        if len(metric) > 100 or len(publisher) > 100:
            raise AppError("指标或发布机构检索词过长")
        ids = [r["id"] for r in self.summary()["sources"] if r["observations"]]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with closing(self.store.connect()) as db:
            return [
                dict(row)
                for row in db.execute(
                    f"""SELECT o.region,o.year,o.metric,o.value,o.unit,s.origin AS url,
                              s.publisher,s.fetched,COALESCE(s.raw_digest,s.digest) AS digest
                FROM solar_observations o JOIN solar_sources s ON s.id=o.source
                WHERE o.source IN ({placeholders}) AND o.region=? COLLATE NOCASE AND o.year BETWEEN ? AND ?
                      AND instr(lower(o.metric),lower(?))>0 AND (?='' OR s.publisher=?)
                ORDER BY o.year DESC,o.metric,s.checked DESC LIMIT 1200""",
                    [*ids, region, start, end, metric.strip(), publisher, publisher],
                )
            ]

    def summary(self):
        with closing(self.store.connect()) as db:
            sources = [
                dict(row)
                for row in db.execute("""SELECT id,title,publisher,origin url,checked,
                (SELECT COUNT(*) FROM solar_observations o WHERE o.source=s.id) observations,
                (SELECT COUNT(*) FROM solar_passages p WHERE p.source=s.id) passages
                FROM solar_sources s WHERE id=(SELECT id FROM solar_sources t WHERE t.url=s.url
                ORDER BY t.checked DESC,t.id DESC LIMIT 1) ORDER BY checked DESC""")
            ]
            regions = [
                r[0] for r in db.execute("SELECT DISTINCT region FROM solar_observations ORDER BY region")
            ]
        return dict(
            sources=sources,
            regions=regions,
            observations=sum(r["observations"] for r in sources),
            passages=sum(r["passages"] for r in sources),
        )


def energy_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not set(METRICS) <= set(reader.fieldnames or []):
        raise ValueError("能源数据字段已更改")
    return (
        [
            (r["country"], int(r["year"]), name, unit, r[field])
            for r in reader
            for field, (name, unit) in METRICS.items()
            if r[field]
        ],
        [],
    )


def grapher_rows(raw, column, metric, unit):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not {"Entity", "Year", column} <= set(reader.fieldnames or []):
        raise ValueError("统计数据字段已更改")
    return ([(r["Entity"], int(r["Year"]), metric, unit, r[column]) for r in reader if r[column]], [])


def capacity_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    values = [f for f in reader.fieldnames or [] if f not in ("Entity", "Code", "Year")]
    if len(values) != 1 or values[0] not in ("Solar", "Solar capacity (total) (GW)"):
        raise ValueError("装机数据字段已更改")
    return ([(r["Entity"], int(r["Year"]), *CAP_METRIC, r[values[0]]) for r in reader if r[values[0]]], [])


def release_rows(raw, *, operation=None):
    page = ReleasePage(raw)
    passages = []
    for i, line in enumerate(page.paragraphs, 1):
        if (
            not line.startswith(("附件", "责任编辑", "国家能源局网站"))
            and 18 <= len(line) <= 1800
            and any(
                w in line
                for w in ("光伏", "太阳能", "硅片", "多晶硅", "硅料", "组件", "分布式", "集中式光伏")
            )
        ):
            passages.append((f"网页第{i}段", line))
    if not operation:
        return [], passages
    year, period = operation
    published = (page.meta.get("pubdate") or page.meta.get("publishdate") or "")[:4]
    allowed_years = {str(year), str(year + 1)} if period == "全年" else {str(year)}
    if published not in allowed_years or (
        period != "全年" and not any(period in text for _, text in passages)
    ):
        raise ValueError("国家能源局原文发布时间或统计窗口不匹配")
    generation = set()
    utilization = set()
    growth = set()
    for _, line in passages:
        clean = re.sub(r"\s+", "", line)
        for vol, unit, yoy in re.findall(
            r"全国光伏(?:累计)?发电量(?:达(?:到)?|为)?(\d+(?:\.\d+)?)(万亿|亿)千瓦时"
            r"(?:，同比增长(\d+(?:\.\d+)?)%)?",
            clean,
        ):
            generation.add(Decimal(vol) * (10000 if unit == "万亿" else 1))
            if yoy:
                growth.add(yoy)
        utilization.update(re.findall(r"全国光伏发电(?:平均)?利用率(?:为)?(\d+(?:\.\d+)?)%", clean))
    if len(generation) != 1 or len(utilization) != 1 or len(growth) > 1:
        raise ValueError("国家能源局原文的全国光伏发电量或利用率未能唯一核对")
    suffix = f"（国家能源局，{period}）"
    records = [
        ("China", year, "全国光伏发电量" + suffix, "亿千瓦时", format(generation.pop().normalize(), "f")),
        ("China", year, "全国光伏发电利用率" + suffix, "%", utilization.pop()),
    ]
    if growth:
        records.append(("China", year, "全国光伏发电量发布同比" + suffix, "%", growth.pop()))
    return records, [
        ("指标口径", "采用国家能源局原文中的全国光伏发电统计，发电量统一为亿千瓦时。"
         "国家统计局规模以上工业太阳能发电量使用独立统计范围，两个口径分别展示。"),
        *passages,
    ]


def manufacturing_rows(raw, *, year):
    page = ReleasePage(raw)
    observations = manufacturing_observations(page.paragraphs, year)
    # Retain adjacent conditions, rates and the export passage as context.
    passages = [
        (f"网页第{i}段", line)
        for i, line in enumerate(page.paragraphs, 1)
        if 24 <= len(line) <= 1400
        and (
            ("产量" in line and "同比" in line)
            or ("组件出口" in line and "出口量" in line)
            or ("全年主要光伏产品" in line and "价格" in line)
        )
    ]
    return observations, passages
