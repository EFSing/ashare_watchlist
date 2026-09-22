# 新版 C 数据依赖与执行可行性检查 V1

结论：`DESIGN_SUPPORTED / FORMAL_OUTCOME_RESEARCH_NOT_READY`

本报告只检查当前项目已有 manifest、字段语义、覆盖元数据、复权定义、known-at 声明和本地
文件存在性。没有抓取 provider、没有恢复缺失的 daily-K、没有读取 C outcome、没有读取
Final OOS，也没有重写任何正式历史 artifact。

## 检查身份

| 项目 | 值 |
| --- | --- |
| C namespace | `C_PRE_OUTCOME_DESIGN_V1` |
| C strategy identity | `C_MAIN_TREND_RETEST_RESEARCH_V1` |
| source manifest | `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json` |
| manifest schema | `CORE_SIGNAL_VALIDATION_DATASET_MANIFEST_V1` |
| manifest SHA-256 | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` |
| declared source | `HiThink Financial-API` |
| declared acquisition date | `2026-08-28` |
| declared stock raw SHA | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` |
| declared adjustment SHA | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` |
| declared stock row count | `10,252,571` |
| declared symbol count | `5,551` |
| declared index rows | `886` |
| declared C-visible sessions | `769` continuous XSHG sessions, 2023-06-30 through 2026-08-28 |

机器可读版本：[data_dependency_check.json](../../data/research/c_pre_outcome_design_v1/data_dependency_check.json)，文件 SHA-256：
`cbf954a4a2f62dcdc98eafd39d94485a7235c2ae8d477926614e75b0d66190`。

## 字段、覆盖与复权

| 依赖 | 观察结果 | 状态 |
| --- | --- | --- |
| OHLCV | manifest adjustment semantics 指明 `open/high/low/close` 价格字段和 `raw unadjusted volume` | `DECLARED_IN_FROZEN_MANIFEST` |
| daily history | universe 语义为 T 有 raw daily-K row 且截至 T 至少 120 bars | `SCHEMA_SUPPORTED`；本 C worktree 的 `daily_k.parquet` 缺失；不推断其他 worktree 或全项目无数据 |
| index/calendar | `continuous_xshg_sessions_within_frozen_validation_interval`，Asia/Shanghai | `PASS_METADATA` |
| price adjustment | event filter `date < ex_date <= T`，按 ex_date ascending，T-anchor formula | `SIGNAL_PRICE_DEFINITION_AVAILABLE` |
| future events | manifest 记录数据截止后仍有 42 个 corporate-action rows | `MUST_EXCLUDE_FROM_T_SIGNAL` |
| volume adjustment | raw unadjusted volume | `AVAILABLE_FOR_WITHIN_SYMBOL_RELATIVE_FEATURES`；仍需检查 corporate-action discontinuity |
| turnover/amount | C core design 不依赖 turnover；当前任务不抓取替代源 | `NOT_REQUIRED / NOT_VERIFIED` |

信号阶段优先使用 T-known raw volume 和有明确 T-anchor 语义的 price。未来事件不能改变 T
信号；若使用后见之明复权序列，必须重新证明其 T-known identity，否则不能作为严格 PIT
研究输入。

## known-at、重放和本地状态

manifest 的 `known_at_vintage_proof=false`，并明确“retrospective official dump has
observation dates and acquisition hash, but no per-bar historical vintage timestamp”。这意味着：

- source/hash/acquisition date 可以支持 provenance 盘点；
- 不能仅凭 acquisition date 证明每一根历史 bar 在其 T 已可见；
- 本轮不把 `HISTORICAL_T_ANCHOR_PRICE_RAW_VOLUME` 写成严格 PIT 已通过；
- 正式 outcome 研究需取得逐 bar vintage evidence，或在 protocol 中明确把结论限制为
  `PARTIAL_UNVERIFIED`，并得到 Sol/用户对研究范围的明确接受。

manifest 的确定性元数据存在，但本 C worktree 没有声明的 `daily_k.parquet`（只读检查结果为
`daily_k_local_present=false`、`daily_k_local_sha256_status=NOT_VERIFIABLE_MISSING`）。该状态
只描述本 worktree 的可恢复性，不推断其他机器、其他 worktree 或全项目无数据；若文件未来出现，
仍必须单独以声明 SHA 实际计算后才能标记 `MATCH`，不能仅凭文件存在证明身份。本轮不从 provider
或 Drive 补取，也不以已有 B 的 replay 输出替代 C 输入。于是当前状态为：

`METADATA_REPLAY_CONTRACT=PASS`，`LOCAL_C_REPLAY_READY=NO`，
`FORMAL_C_OUTCOME_RESEARCH=NOT_AUTHORIZED / NOT_RUN`。

## Universe 与 ST/*ST

通用 `ASHARE_BOARD_TAXONOMY_V1` 可区分 Main/ChiNext/STAR/Unknown，00/60 Main、30
ChiNext、68 STAR。它足以支持 board filter，但不等于历史 ST filter 已完成。

当前冻结 manifest 没有每个 T 的 ST/*ST status 或可验证的 T-known security-name history。
因此 C 的规则要求：

- T 时明确证明 `st_status_known_at_t=true`；
- missing/ambiguous/current-only status 一律 `UNRESOLVED_ST_STATUS`；
- 不以 2026 当前名称回填 2023–2026 历史；
- 在证据补齐前，不能声称 formal historical C sample 已经“排除 ST/*ST”。

这不是对 C 方向的收益否定，而是合法样本边界的 correctness gate。

## 成交量、K 线与执行

日 OHLCV 足以计算 relative volume、pullback path、up/down median ratio、K 线实体/影线、
close location、阶段前高附近的 daily stall proxy 和重复失败 push。它不能证明：

- 缩量是吸筹；
- 放量滞涨是派筹；
- 盘中先封板、开板的确切时间或排队成交；
- 某个 T+1 open/close 实际有可成交数量。

没有合法盘中数据时，不得把 T 日收盘后得到的全天 volume 当成 T 日盘中卖出可知信息。若
`limit_up_price`、`tick_size` 缺失，炸板字段必须为 `UNAVAILABLE`；即使有日线 proxy，也
保留 `intraday_order_known=false`。

已有 provider-neutral trade-state helper 可以识别结构化 `TRADED`、显式 `NO_TRADE` 和
`UNKNOWN`，但 C 本轮不调用 live provider。C 未来执行必须把 `NO_TRADE`、停牌、limit-state、
缺 open、T+1 gap 和实际 fill 不可知分别记录为 `EXECUTION_UNCERTAIN`，而不是隐含成交。

## 可支持的范围

| 范围 | 当前判断 |
| --- | --- |
| 研究前规则设计 | `PASS` |
| 纯函数、合成样本、前缀不污染验证 | `PASS` |
| 读取已存在 manifest 做字段/覆盖盘点 | `PASS` |
| 在本 worktree 运行正式 C 历史 replay | `NO`：缺 daily-K，且本轮禁止抓取/恢复 |
| 在当前证据上读取/比较 C future returns | `NO`：未授权且明确禁止 |
| 严格 PIT 的 retrospective C 结论 | `PARTIAL_UNVERIFIED`：缺 per-bar vintage proof |
| 历史 Main Board non-ST 样本 | `PARTIAL_UNVERIFIED`：缺 T-known ST status |
| 盘中炸板/实际成交/当日卖出模拟 | `UNAVAILABLE / EXECUTION_UNCERTAIN` |
| 未来合法 prospective T-close capture | `IN PRINCIPLE`, 但必须新建 C 专属 input identity、known-at evidence 和输出路径；不能调用 B-bound package 直接冒充 C |

## 需要补齐的 evidence

1. 合法、可恢复的 OHLCV bytes 与字段 schema，精确匹配已声明 hash；
2. 每个历史 T 的 ST/*ST status 或明确缩窄研究样本的 protocol decision；
3. per-bar known-at/vintage evidence，或 Sol 审核通过的 `PARTIAL_UNVERIFIED` 研究边界；
4. C 专属 T-close package/generation identity，不写 B canonical watchlist、runtime-state、
   tracker、日报或生产调度；
5. T+1 reference execution 的开盘/限价/停牌/NO_TRADE/无法成交 classification；
6. 若研究炸板，valid T-known limit price/tick 和其 round/首日规则；否则此特征维持
   `UNAVAILABLE`。

当前结论：数据接口和定义方向支持继续做 Sol audit；数据证据还不足以启动新版 C 的正式
历史收益研究。
