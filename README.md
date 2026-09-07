# ashare_watchlist

A 股观察名单与 signal-level 复盘量化工具。用于维护 canonical 观察名单、每日轻量状态和跨日节点评价。

## 功能

- **观察名单管理**（生产目录 `data/watchlist_*.json`）：每日盘前产出的候选股票名单，含买点/止损/目标位；canonical 字段为 `candidates` / `trigger`。
- **每日轻量状态**（`scripts/review_after.py`）：使用 canonical watchlist 与当日腾讯行情快照记录名单状态；不读取旧持仓或配对指标流程。
- **正式跨日复盘**（`scripts/track_perf.py` + `data/perf_tracker.json`）：按稳定 `signal_id` 记录真实 XSHG 交易日的 T+3、T+5、T+10 节点；提前触发 target/stop 的真实结案状态会保留。

## 目录结构

```
.
├── scripts/                # Python 脚本
│   ├── preopen_review.py   # 开盘状态查看（非正式跨日复盘）
│   ├── review_after.py     # 每日轻量状态查看
│   ├── track_perf.py       # 表现追踪器
│   └── eod_review.py       # review_after 的兼容入口
├── data/                   # 名单、tracker 与报告（可由 ASHARE_DATA_ROOT 覆盖）
│   ├── watchlist_*.json    # 每日观察名单
│   ├── legacy_invalid/     # 隔离的历史/非法名单，不参与生产扫描
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

脚本默认数据目录为仓库内的 `data/`。部署时统一设置 `ASHARE_DATA_ROOT`，正式复盘脚本通过同一个 resolver 读写名单、跟踪库和报告。

```bash
# 每日轻量状态（自动取前一交易日名单）
python3.11 scripts/review_after.py --mode close

# 午盘复盘
python3.11 scripts/review_after.py --mode midday

# 指定名单/list 日期查看；行情仍取运行当日，不是历史行情 as-of
python3.11 scripts/review_after.py --mode close --date 20260821

# 跨日正式复盘（每日运行，自动维护节点）
python3.11 scripts/track_perf.py
```

## 正式复盘制度

复盘分为四个固定层次：每个真实 XSHG 交易日生成一份每日轻量状态记录；对每个 signal-level 信号，以信号日 T 后第 3 个交易日做 T+3 短线评价，第 5 个交易日做 T+5 PRIMARY REVIEW HORIZON（主评价），第 10 个交易日做 T+10 延伸观察并结案。节点使用 XSHG 交易日历，不按自然日；信号最早执行日仍是 T+1。每个节点保存 signal/list date、review trading date、horizon 和 deterministic snapshot identity。

跨日评价由 `track_perf.py` 负责，不回写历史研究的 10D outcome。fixed-horizon snapshot 的 observation/return 与 execution/path result 分离；信号若提前触发 target/stop，保留真实结案日和状态，并在后续固定节点允许记录快照。缺少真实节点 observation 或确认入场价时明确标记 missing/unverified，错过节点时不进行历史行情回填。same-bar 同时触发多个边界时保留 `AMBIGUOUS_SAME_BAR`，不猜测盘中顺序。`eod_review.py` 仅作为每日轻量状态的兼容入口。

观察名单必须使用 `watchlist_YYYYMMDD.json` 文件名，payload 必须包含 `date`、`mode`、`market_env`、`sectors`、`candidates`；旧的 `items` / `trig` 结构会直接报错，不会静默转换。生产扫描只读取 `data/` 根目录下的 canonical 文件；`data/legacy_invalid/` 中的历史/非法文件保留供审计但不会参与 ingest。

`review_after.py --date` 仅表示名单/list date。报告会同时显示名单日期与行情日期；生产 review 路径当前行情日期始终是运行当日，不支持 historical replay。Phase 2E 的独立 `CORE_SIGNAL_VALIDATION` research harness 不改变这一生产边界。

## 说明

- 数据含个人持仓信息，建议仓库保持**私有**。
- 行情数据为第三方公开快照，仅供学习研究，不构成投资建议。

## Phase 2B：Generation Input & Timing Contract Freeze

Phase 2B 只冻结 generation system 的 input/timing contract，尚无正式
generation strategy。唯一支持 `close` generation：T 日数据完整后以
`as_of_date=T` 生成信号，最早执行日是 XSHG 日历的下一个交易日 T+1，时区为
`Asia/Shanghai`。premarket、same-bar execution、当前数据冒充历史日期和
historical replay 均不支持。

`LIVE_OBSERVED` 不是标签而已：Universe、Quote、stock/index Kline 和 Sector
的 `retrieved_at_bjt` 北京时间日期必须等于 T；`close` generation 还必须发生
在 XSHG 当日正式 `session_close` 时点或之后。盘中输入拒绝为
`SESSION_NOT_CLOSED`，不使用人工 15:05/15:10 缓冲。

Phase 2B runtime calendar baseline 固定为 `exchange-calendars==4.13.2`；真实
XSHG provider 已覆盖 2026 交易日、节假日与正式 session close 回归测试。

输入 manifest、日期 fail-fast 校验、腾讯
`PROVIDER_QFQ_SNAPSHOT` 语义、AkShare `LIVE_OBSERVED` 限制与 deterministic
input fingerprint 见 [`docs/generation_input_contract.md`](docs/generation_input_contract.md)。
本阶段不实现 A/B/C/D、评分、选股、调参、调度或 historical replay；也不恢复
`screen_system.py`、修改旧阈值/85 分评分、`perf_tracker` 或历史 watchlist。

## Phase 2C：A Platform Breakout Legacy Baseline

Phase 2C 新增 `A_PLATFORM_BREAKOUT_LEGACY_V1` research baseline evaluator。它只
消费 Phase 2B `READY_FOR_STRATEGY_EVALUATION` 的冻结
`GenerationInputManifest`，恢复 V0 A 平台突破、支撑/止损、target/RR、风险标
记和完整 85 分 breakdown，并为每只股票输出可审计的
`CandidateEvaluation`。详细公式、状态、Sector evidence 和 provenance 见
[`docs/a_platform_breakout_legacy_v1.md`](docs/a_platform_breakout_legacy_v1.md)。

该基线不联网、不使用 raw 当前数据、不做 historical replay，不读取
`perf_tracker`，不实现 B/C/D，不接 scheduler，不写历史或 canonical watchlist，
不做 TOP N、score cutoff、portfolio selection 或仓位分配。它不代表 A 参数已验
证、production rule 已冻结、85 分具有预测有效性、target/stop 已经历史验证，
也不可直接交易。Phase 2D 的 promotion、point-in-time source 和正式输出决策仍
未确定。
