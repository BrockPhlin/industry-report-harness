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
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import AppError
from .manufacturing import RELEASES as MANUFACTURING_RELEASES, manufacturing_observations
from .policy import POLICIES, parse_policy
from .store import now
from .trade import TRADE, trade_jobs
from .provinces import (
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


def fetch(url):
    if not permitted(url):
        raise ValueError("数据源地址无效")
    request = Request(url, headers={"User-Agent": "PVResearch/1.0 (educational data analysis)"})
    with build_opener(PublicRedirect()).open(request, timeout=25) as response:
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

    def ingest(self, url, title, publisher, origin, parser, schema=""):
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
                raw = self.download(url)
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

    def collect_manufacturing(self, plan):
        if "China" not in plan["regions"]:
            return []
        intent = plan["title"] + " " + " ".join(plan["keywords"])
        if not any(word in intent for word in ("产量", "制造", "多晶硅", "硅片", "组件", "出口", "产业链")):
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

    def collect(self, plan):
        words = plan["keywords"] + [str(y) for y in range(plan["start"], plan["end"] + 1)]
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
        domestic = bool(set(plan["regions"]) & (REGIONS | {"China"}))
        if domestic:
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
            if plan.get("quarter_requested") or plan["end"] >= 2026:
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
        notices = []
        if domestic:
            intent = plan["title"] + " " + " ".join([*plan["keywords"], *plan.get("sections", [])])
            policy_scope = {*plan["regions"], "China"}
            for policy in POLICIES:
                if (
                    policy.year <= plan["end"]
                    and policy.region in policy_scope
                    and match_score(intent, policy.topics)
                ):
                    title = f"{policy.year} 年 {policy.title}"
                    jobs.append(
                        (policy.url, title, policy.issuer, policy.url, partial(parse_policy, policy=policy))
                    )
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
                notices.append(
                    {"source": "国家能源局发布目录", "result": "目录访问失败，尝试已登记的统计发布"}
                )
            for title, url in links.items():
                if url in {
                    *HTML_TABLES.values(),
                    *HTML_QUARTER_TABLES.values(),
                    *(page for page, _, _ in TABLES.values()),
                }:
                    continue
                years = [int(y) for y in re.findall(r"20\d{2}", title)]
                if years and not any(plan["start"] <= y <= plan["end"] for y in years):
                    continue
                publisher = "工信部" if "miit.gov.cn" in url else "国家能源局"
                jobs.append((url, title, publisher, url, release_rows))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda job: self.ingest(*job), jobs))
        # Query one reporter and year at a time, batching product/partner rows.
        # Process those requests sequentially to respect the provider's limit.
        for trade in trade_jobs(plan):
            jobs.append(trade)
            results.append(self.ingest(*trade))
        keys = []
        for job, (sid, status) in zip(jobs, results):
            notices.append({"source": job[1], "result": status, "url": job[3]})
            if sid is not None and sid not in keys:
                keys.append(sid)
        for sid, notice in self.collect_manufacturing(plan):
            notices.append(notice)
            if sid is not None and sid not in keys:
                keys.append(sid)
        if domestic:
            active_urls = {j[3] for j in jobs}
            for src in self.summary()["sources"]:
                years = re.findall(r"20\d{2}", src["title"])
                if (
                    src["passages"]
                    and src["url"] not in active_urls
                    and years
                    and any(plan["start"] <= int(y) <= plan["end"] for y in years)
                    and match_score(src["title"], plan["keywords"])
                ):
                    keys.append(src["id"])
                    notices.append(dict(source=src["title"], result="复用历史资料快照", url=src["url"]))
        return self.select(keys, plan), notices

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
                        # Keep first, last and evenly spaced interior observations on long horizons.
                        selected = sorted(
                            {
                                round(i * (len(series) - 1) / min(9, max(1, len(series) - 1)))
                                for i in range(min(10, len(series)))
                            }
                        )
                        samples = [series[i] for i in selected]
                        digits = 4 if "美元" in unit else 2
                        shown = [(year, display_value(v, digits)) for year, v in samples]
                        data = "；".join(f"{year}年 {value} {unit}" for year, value in shown)
                        note = trend(samples, unit)
                        is_provincial = "光伏并网容量分省统计" in src["title"]
                        if is_provincial:
                            note += table_caveat(region, samples[-1][0], quarter="前三季度" in src["title"])
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
                passages = db.execute(
                    "SELECT locator,body FROM solar_passages WHERE source=? ORDER BY rowid", (sid,)
                )
                for loc, body in sorted(passages, key=lambda p: -match_score(p[1], plan["keywords"]))[:8]:
                    add(loc, body)
        return evidence

    def browse(self, region, start, end):
        if not region or len(region) > 100 or not 1900 <= start <= end <= 2100:
            raise AppError("地区或年份范围无效")
        ids = [r["id"] for r in self.summary()["sources"] if r["observations"]]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with closing(self.store.connect()) as db:
            return [
                dict(row)
                for row in db.execute(
                    f"""SELECT o.region,o.year,o.metric,o.value,o.unit,s.origin AS url
                FROM solar_observations o JOIN solar_sources s ON s.id=o.source
                WHERE o.source IN ({placeholders}) AND o.region=? COLLATE NOCASE AND o.year BETWEEN ? AND ?
                ORDER BY o.year DESC,o.metric LIMIT 1200""",
                    [*ids, region, start, end],
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


def release_rows(raw):
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
    return [], passages


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
