# 新版 C 数据依赖与执行可行性检查 V1

结论：`DESIGN_SUPPORTED / DAILY_K_INTEGRITY_VERIFIED_EXTERNALLY / FORMAL_OUTCOME_RESEARCH_NOT_READY`

本报告只检查当前项目已有 manifest、字段语义、覆盖元数据、复权定义、known-at 声明和本地
文件存在性。没有抓取 provider、没有恢复缺失的 daily-K、没有读取 C outcome、没有读取
Final OOS，也没有重写任何正式历史 artifact。

本轮退出语义修复只影响 C 研究观察：实现与测试已区分
`PRICE_ONLY_EARLY_DEFENSE` 和 `PRICE_VOLUME_EARLY_DEFENSE`；异常量阈值仍是
出场实际使用 `RV >= 2.0`，`robust-z >= 3.0` 只作观察，不代表已完成收益选择或正式研究。
独立协议草案为 `docs/research/c_pre_outcome_preregistration_protocol_v1.md`。

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
`89901be61dfe01872f54da2b031527c721f6d639016b20806ed918a999a3977d`。

## 只读 daily-K 恢复线索

以下仅列出现有项目元数据声明的可能位置，并记录本轮授权的只读完整性核验；不下载、解压、
覆盖或复制任何文件；声明的 raw daily-K SHA-256 均为
`61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`：

| 线索 | 角色 | 当前含义 |
| --- | --- | --- |
| `data/validation/core_signal_validation/raw/daily_k.parquet` | canonical logical path | 本 C worktree `MISSING`；若恢复到 C 输入路径，仍必须重新计算并匹配声明 SHA |
| `D:\dev\ashare-watchlist\data\validation\core_signal_validation\raw\daily_k.parquet` | existing local copy in another worktree | `VERIFIED`：授权只读实际大小 `180,203,424` bytes，实际 SHA-256 与声明完全匹配；未作为 C 输入，未复制或覆盖 |
| `data/governance/frozen_artifacts.json` → `phase2e.raw.daily_k` | frozen artifact / recovery registry | 声明来源为 HiThink daily-K dump + private recovery archive，指向 Google Drive 私有恢复位置；本轮未读取该 archive bytes |
| `data/governance/workstation_durability_manifest.json` → 同一 logical path | workstation durability metadata | 声明 Drive readback 已按同一 SHA 校验；它是恢复线索，不是本地 raw 文件 |
| `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json` 与 `data/validation/phase2e_source_audit.json` | provenance only | 反复声明同一 canonical path/SHA，不构成替代 raw 数据副本 |

只读核验记录见 [`daily_k_integrity_check.json`](../../data/research/c_pre_outcome_design_v1/daily_k_integrity_check.json)。
该记录 SHA-256 为 `2a0496e3414b4bd43969f66f7cf93c2b7a1e4a698266abdc74243f662799f939`；独立协议草案
[`c_pre_outcome_preregistration_protocol_v1.md`](c_pre_outcome_preregistration_protocol_v1.md)
SHA-256 为 `c74447608490fdd7068ea4a018dc3be31358198d3570ead878e5095cc09befd3`。
因此当前结论是：外部 artifact identity `VERIFIED`，但 `LOCAL_C_REPLAY_READY=NO`、
`FORMAL_C_OUTCOME_RESEARCH=NOT_AUTHORIZED / NOT_RUN`。历史 T-known ST 状态和逐 bar
known-at/vintage 证据保持未解决。

## 证据状态盘点

以下状态只描述证据强度，不把 manifest 声明、采集日期或当前名称升级为历史可见性证明：

| 证据项 | 状态 | 证据路径/说明 |
| --- | --- | --- |
| daily-K 外部字节大小/SHA | `VERIFIED` | `daily_k_integrity_check.json`；实际 `180203424` bytes，SHA 与 `phase2e.raw.daily_k` 声明一致；仅证明 artifact identity |
| C worktree canonical daily-K | `MISSING` | `data/research/c_pre_outcome_design_v1/data_dependency_check.json`：`daily_k_local_present=false`；未运行本地 C replay |
| OHLCV 字段与 raw volume 语义 | `DECLARED_ONLY` | `core_signal_validation_manifest.json`；字段/语义有 manifest 声明，但本轮未把外部文件接入 C |
| 复权与 T-anchor event filter | `DECLARED_ONLY` | 同一 manifest 的 `date < ex_date <= T` 声明；未来 event 排除规则可写入 protocol，但逐 bar vintage 仍缺 |
| 交易日历与 session mapping | `VERIFIED` | C metadata check 的 769 个连续 XSHG sessions、Asia/Shanghai 和现有 helper；这不是 PIT 证明 |
| 历史 T-known ST/*ST | `UNRESOLVED` | manifest 没有逐 T status/name history；不得用当前名称回填 |
| per-bar known-at/vintage | `UNRESOLVED` | manifest 明确 `known_at_vintage_proof=false`；采集日期不等于历史可见时间 |
| 涨跌停 price/tick 与逐 bar 触及顺序 | `MISSING` | 日线文件/当前 C metadata 没有合法 T-known limit price/tick/intraday sequence；炸板保持 `UNAVAILABLE` |
| T+1 执行政策 | `VERIFIED` | C 规则固定 T-close signal、最早 T+1 reference、new-position no-same-day-sell |
| T+1 实际 fill/可成交数量 | `MISSING` | 无合法盘中/order-book/actual-fill 证据；只能记录 `EXECUTION_UNCERTAIN` 分类 |
| 调整因子本地身份 | `VERIFIED` | 现有 `data_dependency_check.json` 的 declared/local SHA `MATCH`；这不补足历史 PIT 证据 |

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

当前结论：数据接口、daily-K artifact identity 和定义方向支持继续做 Sol audit；数据证据
仍不足以启动新版 C 的正式历史收益研究。协议草案当前只到
`C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION`，不等同于参数采纳或 outcome 授权。
