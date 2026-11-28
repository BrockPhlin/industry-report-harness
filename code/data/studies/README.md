# 光伏市场与成本研究数据

三张 CSV 对应固定发布版本。系统联网读取出版者的 PDF，核对文件 SHA-256 后使用已按页核过的数值。原件变动时提示复核页码，之前下载的快照仍可追溯。仓库保留数据和页码，PDF 从原发布方获取。

| 文件 | 页码及口径 |
| --- | --- |
| [pvps-trends-2026.csv](pvps-trends-2026.csv) | IEA PVPS《2026 年光伏应用趋势》附录第 91 页为年末累计，第 92 页为年度新增。按见于该两表的直流侧观测入库，保留全球合计和所选市场。 |
| [pvps-china-2025.csv](pvps-china-2025.csv) | IEA PVPS《2025 年中国光伏应用调查》第 10 页表 1、第 11 页表 3。数值由交流侧 MW 换算为 GW，缺失离网记录未补零。 |
| [irena-cost-2025.csv](irena-cost-2025.csv) | IRENA《2025 年可再生能源发电成本》执行摘要图 S3（PDF 第 8 页）。新投运公用事业级光伏 LCOE 报价使用 2025 年美元/MWh。 |

全球趋势报告的容量使用模块直流侧标称值，个别国家从各自统计口径换算。中国调查按交流侧发布，使用中国国家能源局的统计。两套数值不可直接求差后解释成装机缺口。LCOE 是模型化的发电成本，组件市场报价、上网电价和项目设定需分别查证。

[全球趋势报告](https://iea-pvps.org/trends_reports/trends-2026/) · [中国调查](https://iea-pvps.org/national_survey/nsr-china-2025/) · [发电成本报告](https://www.irena.org/Publications/2026/Jul/Renewable-Power-Generation-Costs-in-2025)
