# C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1 — outcome 前协议（冻结）

状态：`FROZEN_BEFORE_OUTCOME_ACCESS`
冻结日期：2026-09-24（Asia/Shanghai）

冻结 provenance（事实记录，不属于研究定义）：本文件内容定稿于 2026-09-24 12:12:35 +0800
（12,272 bytes，SHA-256 `3aa6ffe2db431574c17a88bfe0b58b85af4a37aa05fb08c3279dc043584e59e3`，
blob `a93e2304d5053092cb430c2eaafdd8f07342c885`），此后到提交为止内容未变；此前先执行过
60 只股票 smoke run 与一次 fail-closed 阻断的 full run（均未产出本文档的报告数字）；全样本
outcome 运行产物生成于 13:57:22 +0800；冻结提交 `9616b49` 创建于 14:01:23 +0800，即
**提交晚于 outcome 运行**。因此本条冻结的含义是“内容在读取收益前固定”，以文件定稿时间与
未变哈希为据，**不是**“提交早于 outcome”。内容定稿后未改动任何规则、窗口、universe、
去重口径、分母或成本边界。

研究分类：`research question`；**不是** Formal B、不是 C 每日名单、不是 C 正式回测、
不是 promotion、不是 Final OOS。

本文件必须在任何 C 收益读取之前固定。冻结后不得因为看到结果而修改规则、窗口、
universe、去重口径、成本边界或收益定义；任何修改都必须新建研究身份。

## 0. 与既有结论的关系（不得重新解释 #87）

- #87（`C_DEVELOPMENT_HISTORICAL_BACKTEST_V1`）的原始阻断结论**保持有效且不被改写**：
  现有 `adjusted=none` 历史文件不是 `C_QFQ_INPUT_V1` 的严格历史快照，
  `C_HISTORICAL_BACKTEST_BLOCKED_BY_VERIFIED_DATA_GAP` 继续成立。
- 本研究不是对 #87 的重新解释，而是用户另行授权、使用**新的输入身份**的独立探索：

```text
C_RAW_T_ANCHOR_LIMITED_EXPLORATION_V1
```

- 本研究结论**不是** `C_QFQ_INPUT_V1` 的正式回测结果，不得写成正式 C 回测、PIT 胜率、
  真实成交胜率或可执行收益。
- 本研究不改变、不合并、不重解释 #81/#83/#84/#85/#86/#87 的任何结论或代码。

## 1. 研究问题、重要性与停止条件

**研究问题：** 在冻结的 C 价格结构规则（`BALANCED_A`、`CONSERVATIVE_B`）不变的前提下，
用可从冻结 raw daily-K 与冻结公司行为表**确定性重建**的 T-anchor 价格序列，
能否计算出可复核的事件数量与 T+3/T+5/T+10 观察统计，以及这些统计的证据缺口在哪里？

**重要性：** 只用于判断“现有历史证据在新输入身份下能支持到哪一步”，供 Sol/用户决定
是否需要为 C 正式路径补齐历史输入。它不触发参数选择、规则变更、正式名单或交易。

**停止条件：**

1. 输入字节身份或换算规则无法验证 → 停在
   `C_RAW_T_ANCHOR_EXPLORATION_BLOCKED_BY_INPUT_IDENTITY_GAP`，不构造替代序列、不输出收益。
2. 输入可验证但某类历史证据缺失（ST、vintage、成交、成本）→ 按本文件逐项标注为
   `PARTIAL_UNVERIFIED`/`UNRESOLVED`，只在可计算范围内输出，并明确不可外推。
3. 结果不得被表述为 Formal B、C 每日名单或 `C_QFQ_INPUT_V1` 的正式结论。

## 2. 输入身份（冻结）

| 项目 | 值 |
| --- | --- |
| raw daily-K | `data/validation/core_signal_validation/raw/daily_k.parquet` |
| raw daily-K 字节数 | `180,203,424` |
| raw daily-K SHA-256 | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` |
| 公司行为表 | `data/validation/core_signal_validation/raw/adjustment_factors.parquet` |
| 公司行为表字节数 | `295,284` |
| 公司行为表 SHA-256 | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` |
| dataset manifest | `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json` |
| manifest 文件 SHA-256 | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` |
| registry | `data/governance/frozen_artifacts.json` → `phase2e.raw.daily_k`、`phase2e.raw.adjustment_factors` |
| 既有换算规则出处 | `docs/phase2e_pit_source_audit.md`（T-anchor 声明）与 manifest `adjustment_semantics` |

已知字段事实（本轮实际读取确认）：`adjusted` 只有 `none`；`interval` 只有 `1d`；
`currency` 只有 `CNY`；`(thscode, date_ms)` 无重复；日期时间戳为北京时间零点对应的
epoch 毫秒（UTC 表示为前一日 16:00Z），因此所有日期换算必须使用 `Asia/Shanghai`，
不得用 UTC 直接取日期。

**身份边界：** 该文件不是 `C_QFQ_INPUT_V1`（B 当日冻结 provider qfq 快照）。
本轮结果不得被引用为 `C_QFQ_INPUT_V1` 结果，也不得用于替换正式 C 输入。

## 3. 价格口径与可证明的转换规则

**价格口径：** 未复权 raw OHLC + 冻结公司行为表的**确定性 T-anchor 重建**。
命名为 `RAW_DAILY_K_DECLARED_T_ANCHOR_V1`。不是 provider `forward`/`qfq` 序列，
不是当日快照复权。

**转换规则（逐字采用既有冻结声明，不新增自由度）：** 对每只证券，按 `ex_date` 升序，
仅对满足 `bar_date < ex_date <= T` 的事件，对 `open/high/low/close` 依次施加仿射变换：

```text
price ← (price - dividend_per_share + allotment_price × allotment_ratio)
         / (1 + per_share_bonus + allotment_ratio)
```

约束：

- 锚点行自身保持 raw 价格不变（等价于 `bar_date < ex_date` 的严格不等号）；
- `volume` 保持 raw，不参与任何调整；
- 分母 `<= 0` 或非有限 → 该证券该 T 记为 `INVALID_CORPORATE_ACTION` 并跳过，不猜测；
- **评价窗口内的公司行为**：任意 `T→T+k` 的价格比较统一使用**同一 anchor `T+k`** 的
  T-anchor 序列（即 `adj_{T+k}`）计算分子分母，避免窗口内除权除息产生伪收益；
  同时单独统计窗口内是否含公司行为的数量。
- 实现必须与项目既有实现同一规则语义（`scripts/b_phase_volume_path_diagnostic.py`
  的 `_adjusted_symbol_arrays` 使用同一公式与同一事件过滤）；差异仅为本轮按 manifest
  声明同时调整 `open`（既有 B 诊断只用 close/high/low，因为其规则不需要 open）。
  该差异必须在报告中显式记录，并以数值交叉核对证明 close 序列一致。

**可验证性声明（必须在报告中给出实际数值）：**

1. 两输入文件字节大小与 SHA-256 与冻结声明**严格匹配**，否则 fail closed；
2. 重建序列在除权日的连续性必须优于 raw 序列（记录最大 raw 跳变 vs 最大重建跳变）；
3. 前缀不变性：用最后 120 根 bar 与更长历史前缀分别计算同一 (symbol, T) 的规则结果，
   必须完全一致，否则 fail closed（证明 120 根窗口不裁剪规则所需历史）。

**逐 bar known-at / vintage 缺口（冻结承认，不填补）：** manifest 明确
`known_at_vintage_proof=false`，公司行为表是回溯 dump，没有逐事件公告/生效时间戳。
`ex_date <= T` 的事实使事件在 T 前已经生效，但**不能**证明表中每行参数在 T 时即为
当时可见值（例如事后更正过的参数）。因此本研究的时点状态固定为：
`T_ANCHOR_RECONSTRUCTION_PARTIAL_UNVERIFIED_NO_PER_BAR_VINTAGE`，不得宣称严格 PIT。

## 4. 历史日期与证券范围（冻结）

| 项目 | 值 |
| --- | --- |
| XSHG session 日历 | manifest `signal_dates` 的 769 个连续 session |
| 日历区间 | `2023-06-30` – `2026-08-28`（Asia/Shanghai） |
| 证券范围 | `classify_board(symbol) == Main`（沪深 00/60） |
| 最小历史 | 截至 T 至少 120 根已完成 bar（与冻结 universe 语义一致） |
| 排除 | ChiNext 30、STAR 68、其他/未知板块 |

不把当前 universe、当前成分或当前名称回填历史。

## 5. 历史 ST 证据缺失时的处理（冻结）

冻结 raw daily-K **没有**名称或逐 T ST/*ST 状态字段，项目也没有历史 T-known ST 来源。
因此：

- 本轮**不**对任何证券断言 `st_status_known_at_t=true`，也不使用当前名称回填；
- 本轮样本身份固定为 `MAIN_BOARD_ST_UNVERIFIED_CANDIDATE_SAMPLE`；
- 报告必须显式写出：这些证券**不满足**正式 C universe（`C_MAIN_BOARD_NON_ST_V1`）的
  PIT 有效样本条件，`UNRESOLVED_ST_STATUS` 计数 = 样本内全部证券；
- 任何结果不得写成“已排除 ST/*ST 的正式 C 样本”；
- ST 过滤可能同时带来方向不明的样本污染，必须作为主要限制列出，不得事后调整。

## 6. Timing 与执行（冻结）

- 信号只在 T 收盘后形成，只消费 `<= T` 字段；`future_data_used=false`；
- 最早参考执行为**下一个 XSHG session 的 T+1 open**；
- `T_PLUS_ONE_REFERENCE_RETURN` 只是开盘参考价情景，**不是**成交证明；
- 新仓位买入当日不得卖出；本探索不模拟盘中卖出；
- 没有盘中序列、order book、limit price/tick → `炸板`、排队、实际 fill 一律
  `UNAVAILABLE / EXECUTION_UNCERTAIN`，不以 high/low 猜测；
- 停牌或缺失 session 必须显式计数，不得当作正常成交。

## 7. 规则（冻结，复用既有纯函数，不改参数）

- `BALANCED_A`：trend 60 / fast 20 / slow 60、U≥0.55、pivot r=2、L1/L2 间隔≥3、
  最大回踩 20 session、depth 3%–12%、rebound 2%–8%、CLV≥0.60（其余参数见
  `scripts/c_pre_outcome_design.py` 的 `RULE_CANDIDATES`）。
- `CONSERVATIVE_B`：trend 90 / fast 20 / slow 90、U≥0.60、pivot r=3、间隔≥4、
  最大回踩 25 session、depth 4%–15%、rebound 2%–10%、CLV≥0.60。
- 事件定义：`build_entry_observation(...)["entry_candidate"] is True`。
  不新增规则、过滤器、量能 gate、第三套参数，不做参数搜索。
- 允许的加速只限**可证明的必要条件预筛**（趋势条件 + `close_T>open_T` +
  `close_T>close_{T-1}` + CLV≥0.60）。预筛必须验证为超集，不得改变事件集合。

## 8. 评价窗口与收益定义（冻结）

- 窗口：`T+3`、`T+5`、`T+10` 个 XSHG session，按冻结日历取 **T+k 当日的实际 bar**；
  该证券在 T+k 无 bar（停牌/退市）→ `MISSING_SESSION_AT_HORIZON`，计入缺失，不插值；
- `OBSERVATION_RETURN(T,k) = adj_{T+k}(close_{T+k}) / adj_{T+k}(close_T) - 1`
  （只作观察；不作为信号后已成交价格）；
- `T_PLUS_ONE_REFERENCE_RETURN(T,k) = adj_{T+k}(close_{T+k}) / adj_{T+k}(open_{T+1}) - 1`
  （T+1 参考价情景，声明 `REFERENCE_EXECUTION_NOT_ACTUAL_FILL`）；
- `MFE(T,k) = max(adj_{T+k}(high_i), i∈[T+1,T+k]) / adj_{T+k}(open_{T+1}) - 1`；
  `MAE(T,k) = min(adj_{T+k}(low_i), i∈[T+1,T+k]) / adj_{T+k}(open_{T+1}) - 1`；
  日内路径顺序未知，只能作为价格路径观察，不声称可成交；
- 正收益观察比例的分母 = 该规则、该窗口**有效** `OBSERVATION_RETURN` 数；
  参考收益正比例的分母 = 有效 `T_PLUS_ONE_REFERENCE_RETURN` 数；
  两个分母必须与正例数一起报告；
- `COST_AFTER_RETURN = NOT_CALCULABLE_COST_MODEL_NOT_PREEXISTING`：项目没有任务前合法
  固定的统一费用/滑点/涨跌停模型，**不得**在看到结果后选择费率、滑点或涨跌停处理；
- 实际成交胜率：`NOT_AVAILABLE_NO_ACTUAL_FILL_EVIDENCE`，不得用参考价收益冒充。

## 9. 事件去重与重复度（冻结）

- episode identity：`(symbol, stage_prior_high_date, low_one_date, low_two_date, rule_id)`；
  同一 episode 内多个 confirmation date 不算独立事件；
- 同时报告：原始事件数、去重 episode 数、每 symbol 事件数分布、事件最多的 symbol 占比、
  按年份分布、按月分布；
- 不因去重结果调整规则或窗口。

## 10. 量能（冻结：仅描述）

`volume` 的复权语义 `VOLUME_BASIS_UNVERIFIED`（provider `adjust=forward` 对 volume 的
影响未决）。因此本轮量能只输出描述统计（`RV_T`、回踩 path 等），
**不**作为 gate、不改变样本、不影响任何结论。

## 11. 输出与隔离（冻结）

- 只写入 `data/research/c_raw_t_anchor_limited_exploration_v1/`；
- 不写正式 watchlist、日报、checkpoint、runtime-state、tracker；
- 不读取 Final OOS，不读取或触碰 `data/validation/continuous_speed_probe/`；
- 不发起任何 provider 请求，不重抓、不改写、不复制 raw 数据；
- 不修改 Formal B、C 每日名单代码或 `C_QFQ_INPUT_V1` 相关契约；
- 交付独立 Draft PR；不自动合并、不自动 dispatch。

## 12. 结果判读限制（冻结）

- 本研究的正收益比例是**观察统计**，不是策略胜率、不是 OOS 证据、不是可执行收益；
- 样本不足时输出 `INSUFFICIENT_DATA`，不给确定性判断，不做事后显著性检验；
- 必须逐项列出：历史 ST、逐 bar vintage、执行/成交、成本、公司行为窗口、
  session 缺失、前缀不变性、量能语义等证据缺口；
- 不得以本结果主张 C 规则有效、无效或需要调参；决策词只能是
  `ADOPT`（仅限本探索方法/身份）/`REJECT`/`DEFER`/`NEEDS_MORE_EVIDENCE`。
