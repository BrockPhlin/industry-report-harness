"""Build the editable XeLaTeX manuscript and PDF from the course report Markdown.

Run from the repository root: python3 tools/midterm/build_design_report.py
Set SOFFICE to a LibreOffice executable when it is not on PATH.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import quote
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "presentations/02-midterm/report"
TITLE = "第11组_系统设计报告_v1.0"
IMAGE = re.compile(r"!\[([^]]+)\]\(([^)]+)\)\{width=(\d+)%\}")
LINK = re.compile(r"\[([^]]+)\]\((https://[^)]+)\)")
META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"


def escape(text):
    replace = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}"}
    return "".join(replace.get(c, c) for c in text).replace("--", "{-}{-}")


def inline(line):
    parts, start = [], 0
    for match in LINK.finditer(line):
        parts += [escape(line[start:match.start()]), r"\href{" + escape(quote(match[2], safe=":/?#[]@!$&'()*+,;=%")) + "}{" + escape(match[1]) + "}"]
        start = match.end()
    return "".join(parts) + escape(line[start:])


def cells(line):
    return [s.strip() for s in line.strip("|").split("|")]


def blocks(page):
    lines = iter(page.strip().splitlines())
    table = []
    for line in [*lines, ""]:
        line = line.strip()
        if line.startswith("|"):
            if not re.fullmatch(r"[- :|]+", line):
                table.append(cells(line))
            continue
        if table:
            yield "table", table
            table = []
        if not line:
            continue
        image = IMAGE.fullmatch(line)
        if image:
            yield "image", image.groups()
        elif line.startswith("## "):
            yield "subhead", line[3:]
        elif line.startswith("# "):
            yield "head", line[2:]
        else:
            yield "text", line


def plain_text(pages):
    fields = []
    for page in pages:
        for kind, content in blocks(page):
            if kind == "table":
                fields.extend(" ".join(row) for row in content)
            elif kind == "image":
                fields.append(content[0])
            else:
                fields.append(LINK.sub(lambda m: m[1], content))
    return "\n".join(fields)


def editor_count(text, tmp):
    bundled = (Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice")
    writer = os.environ.get("SOFFICE") or (str(bundled) if bundled.is_file() else shutil.which("soffice"))
    if not writer:
        raise SystemExit("需要 LibreOffice Writer 统计正文；请提供 SOFFICE 可执行文件。")
    source = tmp / "body.txt"
    source.write_text(text, encoding="utf-8")
    subprocess.run([writer, "-env:UserInstallation=" + (tmp / "office-profile").as_uri(), "--headless",
                    "--infilter=Text (encoded):UTF8", "--convert-to", "odt", "--outdir", str(tmp), str(source)],
                   capture_output=True, check=True, timeout=90)
    with ZipFile(tmp / "body.odt") as book:
        meta = ET.fromstring(book.read("meta.xml"))
    stats = meta.find(".//" + META + "document-statistic")
    generator = meta.find(".//" + META + "generator").text.split("/")[1].split("$")[0]
    return int(stats.get(META + "word-count")), generator


PREAMBLE = r"""% 从本目录执行 xelatex -halt-on-error -interaction=nonstopmode 第11组_系统设计报告_v1.0.tex 两次。
% 编写与重建入口见 tools/midterm/build_design_report.py。图片和字体的相对路径以本目录为准。
\documentclass[UTF8,12pt,fontset=none]{ctexart}
\usepackage[a4paper,left=23mm,right=23mm,top=26mm,bottom=25mm,headheight=16pt,headsep=7mm,footskip=11mm]{geometry}
\usepackage[table]{xcolor}
\usepackage{graphicx,tabularx,array,fancyhdr,hyperref,fontspec}
\setCJKmainfont[Path=../../../assets/fonts/,BoldFont=LXGWWenKai-Medium.ttf]{LXGWWenKai-Regular.ttf}
\setCJKsansfont[Path=../../../assets/fonts/,BoldFont=LXGWWenKai-Medium.ttf]{LXGWWenKai-Regular.ttf}
\definecolor{zblue}{HTML}{003F88}\definecolor{ink}{HTML}{243448}\definecolor{muted}{HTML}{506581}
\definecolor{pale}{HTML}{E9F1F9}\definecolor{hair}{HTML}{BED0E2}
\hypersetup{colorlinks=true,linkcolor=zblue,urlcolor=zblue,pdftitle={第11组 系统设计报告 v1.0},pdfauthor={软件工程管理第11组},bookmarksnumbered=true}
\linespread{1.0}\setlength{\parindent}{0pt}\setlength{\parskip}{4pt plus 1pt}
\setlength{\tabcolsep}{5pt}\setlength{\emergencystretch}{18pt}
\newcommand{\chaptertitle}[1]{\vspace*{0pt}{\color{zblue}\fontsize{22}{26}\selectfont\bfseries #1\par}\vspace{3pt}{\color{hair}\hrule height .8pt}\vspace{6pt}}
\newcommand{\subhead}[1]{\par\addvspace{8pt}{\color{zblue}\fontsize{14}{18}\selectfont\bfseries #1\par}\vspace{1pt}}
\newcolumntype{Y}{>{\raggedright\arraybackslash}X}
\newcommand{\capline}[1]{{\color{muted}\fontsize{10}{12}\selectfont #1\par}}
\pagestyle{fancy}\fancyhf{}\fancyhead[L]{\small\color{muted}《软件工程管理》\quad 第11组}
\fancyhead[R]{\small\color{muted}产业智能报告生成系统 \quad 系统设计报告 v1.0}
\fancyfoot[R]{\small\color{muted}\thepage}
\renewcommand{\headrulewidth}{.45pt}\renewcommand{\headrule}{\hbox to\headwidth{\color{hair}\leaders\hrule height\headrulewidth\hfill}}
\begin{document}
\color{ink}\fontsize{12}{16}\selectfont
\pagenumbering{Roman}\thispagestyle{empty}
"""


def table_latex(rows):
    # Give the identification columns only the width they need. Reserve more room for evidence and exceptions.
    if rows[0][0] in ("接口与模块", "实体", "参照与验证", "阶段目标", "人员", "同一栏核对项"):
        first, second = ".20", ".34"
    elif rows[0][0] in ("编号", "需求"):
        first, second = ".13", ".32"
    elif rows[0][0] == "时间":
        first, second = ".14", ".23"
    else:
        first, second = ".23", ".31"
    cols = r">{\raggedright\arraybackslash}p{" + first + r"\linewidth}>{\raggedright\arraybackslash}p{" + second + r"\linewidth}Y"
    lines = [r"\par\begingroup\fontsize{10.5}{13.5}\selectfont\renewcommand{\arraystretch}{1.12}",
             r"\arrayrulecolor{hair}\begin{tabularx}{\linewidth}{" + cols + r"}\hline"]
    for i, row in enumerate(rows):
        if len(row) != 3:
            raise ValueError("报告表格需要三列")
        strings = [inline(cell) for cell in row]
        if i == 0:
            strings = [r"\bfseries\color{zblue} " + string for string in strings]
            lines.append(r"\rowcolor{pale}")
        lines.append(" & ".join(strings) + r"\\ \hline")
    return "\n".join([*lines, r"\end{tabularx}\endgroup\par"])


def cover(page, headings):
    lines = [line.strip() for line in page.splitlines() if line.strip()]
    title, subtitle, course, date, roles, group, summary = lines
    out = [r"\noindent\includegraphics[width=39mm]{../../../assets/brand/logo_blue.png}\par\vspace{7mm}",
           r"{\fontsize{29}{36}\selectfont\bfseries\color{zblue}" + escape(title[2:]) + r"\par}",
           r"{\fontsize{20}{25}\selectfont\color{zblue}" + escape(subtitle[3:]) + r"\par}\vspace{4mm}",
           r"{\large " + escape(course) + r"\par}\vspace{3mm}"]
    out.extend(escape(s.replace("**", "")) + r"\par" for s in (date, roles, group))
    out += [r"\vspace{3mm}\noindent\colorbox{pale}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{\vspace{3pt}" +
            escape(summary) + r"\vspace{3pt}}}\par", r"\subhead{目录}\begingroup\setlength{\parskip}{3pt}"]
    for i, name in enumerate(headings, 1):
        label = str(i) if i < len(headings) else "附录"
        out.append(r"\hyperlink{reportpart" + str(i) + "}{" + escape(name) + r"\dotfill " + label + r"}\par")
    return "\n".join([*out, r"\endgroup"])


def render(markdown, tmp):
    pages = [p.strip() for p in markdown.split("<!-- pagebreak -->")]
    body_count = len(pages) - 2
    count, editor = editor_count(plain_text(pages[1:-1]), tmp)
    if body_count > 15 or count > 10000:
        raise ValueError("报告超过系统设计报告篇幅上限")
    headings = [p.splitlines()[0].removeprefix("# ") for p in pages[1:]]
    tex = [PREAMBLE, cover(pages[0], headings)]
    for i, page in enumerate(pages[1:], 1):
        tex.append(r"\clearpage")
        if i == 1:
            tex.append(r"\pagenumbering{arabic}")
        elif i == len(headings):
            tex.append(r"\fancyfoot[R]{\small\color{muted}参考资料}")
        tex.append(r"\hypertarget{reportpart" + str(i) + r"}{}")
        for kind, item in blocks(page):
            if kind == "head":
                tex += [r"\pdfbookmark[1]{" + escape(item) + r"}{outline" + str(i) + "}", r"\chaptertitle{" + escape(item) + "}"]
            elif kind == "subhead":
                tex.append(r"\subhead{" + escape(item) + "}")
            elif kind == "table":
                tex.append(table_latex(item))
            elif kind == "image":
                label, path, width = item
                if not (FOLDER / path).is_file():
                    raise FileNotFoundError(path)
                tex.append(r"{\centering\includegraphics[width=" + str(int(width)/100) +
                           r"\linewidth]{\detokenize{" + path + r"}}\par}\capline{" + escape(label) + "}")
            else:
                tex.append(inline(item) + r"\par")
    tex += [r"\subhead{篇幅统计}",
            f"正文第1至{body_count}页，LibreOffice Writer {escape(editor)} 字数统计为 {count} 字。"
            "统计包含正文标题、段落、表格、图注与 AI 使用说明；封面目录、参考资料及图内文字不计入。",
            r"\end{document}"]
    return "\n".join(tex) + "\n", body_count + 2


def main():
    build = ROOT / ".build/midterm/design-report"
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=build) as directory:
        tmp = Path(directory)
        source, expected = render((FOLDER / "report.md").read_text(encoding="utf-8"), tmp)
        tex = tmp / (TITLE + ".tex")
        tex.write_text(source, encoding="utf-8")
        for _ in range(2):
            result = subprocess.run(["xelatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                                     "-output-directory=" + str(tmp), str(tex)],
                                    cwd=FOLDER, text=True, capture_output=True)
            if result.returncode:
                raise SystemExit(result.stdout[-5500:])
        log = (tmp / (TITLE + ".log")).read_text(errors="replace")
        match = re.search(r"Output written on [\s\S]+? \((\d+) pages?", log)
        if not match or int(match[1]) != expected or "Overfull \\hbox" in log or "Missing character" in log:
            shutil.copyfile(tmp / (TITLE + ".pdf"), build / "preview.pdf")
            raise SystemExit("请检查排版、缺字与实际分页：" + "\n".join(l for l in log.splitlines() if
                             any(k in l for k in ("Overfull", "Missing character", "pages)"))))
        shutil.copyfile(tex, FOLDER / tex.name)
        pdf = tmp / (TITLE + ".pdf")
        shutil.copyfile(pdf, FOLDER / pdf.name)
        print(f"{pdf.name}：{expected} 个物理页，含首末页各一页。")


if __name__ == "__main__":
    main()
