# ashare_watchlist

A 股观察名单与复盘量化工具。用于维护「观察名单」、盘前/盘后复盘、持仓风控追踪与配对指标分析。

## 功能

- **观察名单管理**（生产目录 `data/watchlist_*.json`）：每日盘前产出的候选股票名单，含买点/止损/目标位；canonical 字段为 `candidates` / `trigger`。
- **盘前复盘**（`scripts/preopen_review.py`）：开盘前回顾观察名单与持仓。
- **盘后/午盘复盘**（`scripts/review_after.py`）：复盘前一交易日观察名单与持仓股走势、风控信号。数据源为腾讯行情快照 `qt.gtimg.cn`（GBK）。
- **表现追踪**（`scripts/track_perf.py` + `data/perf_tracker.json`）：按稳定 `signal_id` 把选股事件沉淀为可统计的胜率/盈亏比数据。
- **配对指标**（`scripts/index_pairs.py` + `scripts/pairs_module.py` + `data/index_pairs.json`）：指数/个股配对比值分析。
- **持仓清单**（`data/positions.json`）：持仓股及成本/止损信息，由系统维护。

## 目录结构

```
.
├── scripts/                # Python 脚本
│   ├── preopen_review.py   # 盘前复盘
│   ├── review_after.py     # 盘后/午盘复盘
│   ├── track_perf.py       # 表现追踪器
│   ├── index_pairs.py      # 配对指标（指数）
│   └── pairs_module.py     # 配对指标公共模块
├── data/                   # 名单与持仓数据（可由 ASHARE_DATA_ROOT 覆盖）
│   ├── watchlist_*.json    # 每日观察名单
│   ├── legacy_invalid/     # 隔离的历史/非法名单，不参与生产扫描
│   ├── positions.json      # 持仓清单
│   ├── index_pairs.json    # 配对数据
│   └── perf_tracker.json   # 表现统计
└── 资产库使用指南.pdf        # 使用说明
```

## 环境依赖

- Python 3.11 或 3.12
- 依赖与版本见 `pyproject.toml`；XSHG 真实交易日历是核心运行依赖

```bash
python -m pip install -e ".[test]"
```

## 用法

脚本默认数据目录为仓库内的 `data/`。部署时统一设置 `ASHARE_DATA_ROOT`，所有脚本通过同一个 resolver 读写名单、持仓、配对数据、跟踪库和报告。

```bash
# 盘后复盘（自动取前一交易日）
python3.11 scripts/review_after.py --mode close

# 午盘复盘
python3.11 scripts/review_after.py --mode midday

# 指定名单/list 日期复盘；行情仍取运行当日，不是历史行情 as-of
python3.11 scripts/review_after.py --mode close --date 20260821

# 表现追踪 / 配对指标
python3.11 scripts/track_perf.py
python3.11 scripts/index_pairs.py
```

观察名单必须使用 `watchlist_YYYYMMDD.json` 文件名，payload 必须包含 `date`、`mode`、`market_env`、`sectors`、`candidates`；旧的 `items` / `trig` 结构会直接报错，不会静默转换。生产扫描只读取 `data/` 根目录下的 canonical 文件；`data/legacy_invalid/` 中的历史/非法文件保留供审计但不会参与 ingest。

`review_after.py --date` 仅表示名单/list date。报告会同时显示名单日期与行情日期；当前行情日期始终是运行当日，尚未实现 historical replay。

## 说明

- 数据含个人持仓信息，建议仓库保持**私有**。
- 行情数据为第三方公开快照，仅供学习研究，不构成投资建议。
