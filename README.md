# ashare_watchlist

A 股观察名单与复盘量化工具。用于维护「观察名单」、盘前/盘后复盘、持仓风控追踪与配对指标分析。

## 功能

- **观察名单管理**（`data/watchlist_*.json`）：每日盘前产出的候选股票名单，含买点/止损/目标位。
- **盘前复盘**（`scripts/preopen_review.py`）：开盘前回顾观察名单与持仓。
- **盘后/午盘复盘**（`scripts/review_after.py`）：复盘前一交易日观察名单与持仓股走势、风控信号。数据源为腾讯行情快照 `qt.gtimg.cn`（GBK）。
- **表现追踪**（`scripts/track_perf.py` + `data/perf_tracker.json`）：把选股信号沉淀为可统计的胜率/盈亏比数据。
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
├── data/                   # 名单与持仓数据
│   ├── watchlist_*.json    # 每日观察名单
│   ├── positions.json      # 持仓清单
│   ├── index_pairs.json    # 配对数据
│   └── perf_tracker.json   # 表现统计
└── 资产库使用指南.pdf        # 使用说明
```

## 环境依赖

- Python 3.11
- `pandas`、`requests`

```bash
pip install pandas requests
```

## 用法

脚本默认数据目录为 `/root/ashare_monitor`（名单放 `watchlist/` 子目录，持仓为 `positions.json`）。可按需修改脚本顶部的 `BASE` 路径。

```bash
# 盘后复盘（自动取前一交易日）
python3.11 scripts/review_after.py --mode close

# 午盘复盘
python3.11 scripts/review_after.py --mode midday

# 指定日期复盘
python3.11 scripts/review_after.py --mode close --date 20260821

# 表现追踪 / 配对指标
python3.11 scripts/track_perf.py
python3.11 scripts/index_pairs.py
```

## 说明

- 数据含个人持仓信息，建议仓库保持**私有**。
- 行情数据为第三方公开快照，仅供学习研究，不构成投资建议。
