# 新版 C：研究前规则设计、数据可行性与确定性验证 V1

状态：`C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION`

研究身份：`C_PRE_OUTCOME_DESIGN_V1`  /  `C_MAIN_TREND_RETEST_RESEARCH_V1`

本文件是新版 C 的研究前设计，不是收益结论、Final OOS 结论、production 规则或 Sol
审计通过证明。当前没有读取 C 的 forward outcome、没有执行正式历史收益研究、没有读取
Final OOS，也没有接入 C 正式每日名单。

本轮已完成提前防守量价语义修复后的数据证据核验和独立协议草案：同一持仓和同一价格事件现在明确输出
`PRICE_ONLY_EARLY_DEFENSE` 与 `PRICE_VOLUME_EARLY_DEFENSE` 两个研究观察版本。价格基线不
再被称为量价确认退出；出场版本实际使用 `RV >= 2.0`，`robust-z >= 3.0` 只作观察，
均未由收益选择。协议草案见 `c_pre_outcome_preregistration_protocol_v1.md`；尚未采纳、
尚未授权 outcome 研究。

## 1. 研究问题、materiality 与停止条件

研究问题：在沪深普通主板、排除 ST/*ST 的范围内，能否用 T 日收盘前已经形成的价格结构和
可复核的成交量观测，识别“持续上升通道中的浅回踩，出现两个不同回踩低点和更高低点，随后
小反弹并在 T 收盘重新走强”的入场候选，并把前高阻力、量价转弱和关键支撑破坏分成不同的
出场研究对象？

Materiality：该问题直接决定新版 C 是否有一套可在 T close → T+1 的边界内实现、重放和审计的
研究定义。若支撑、回踩、确认、量价和出场没有先成为确定性 observable，就不能把后续收益
差异解释成 C 规则；若 ST 状态、known-at 或执行证据不足，不能把历史研究写成合法证据。

本轮输入只包括：

- 本项目已冻结的 OHLCV/交易日历/调整因子 manifest 元数据；
- 已存在的、与策略无关的主板分类和交易状态纯函数；
- 合成 OHLCV 样本，用于验证公式、边界、前缀不污染和 T+1 出场约束。

本轮停止条件：

- C 的身份、入场/出场定义、少量候选阈值、数据缺口和未来比较方法已写明；
- C 专属纯函数和合成样本测试通过；
- 数据依赖检查只读 manifest/字段/覆盖/复权/known-at/可重放性，不抓取或重写正式历史数据；
- 所有仍需审计的项标为 `PENDING_SOL_AUDIT`、`PARTIAL_UNVERIFIED`、`UNKNOWN` 或
  `EXECUTION_UNCERTAIN`；
- 停在本文件开头的 terminal marker，等待 Sol/用户审计，不宣称内部自查通过。

未来正式研究开始前，必须有独立的 pre-outcome protocol commit；本文件和纯函数不会自行
开启 outcome 读取、参数搜索、Phase 2F、promotion、freeze 或生产调度。

## 2. 身份、范围与 Formal B 隔离

旧 `C_MAIN_TREND_RETEST_LEGACY_V1` 仅保留为 V0 provenance。旧版的“先涨 30%、再回撤
5%–22%、Fib/MA20、缩量、MA5”不被新版 C 继承为硬条件；本设计也不使用旧 C 的收益、名单、
sample 或成功故事。

新版 C 不要求近期 60 日新高突破。一个标的可以在阶段前高下方完成 T 收盘确认，只要它满足
本文件的回踩结构和重新走强条件。

本 worktree 的隔离约束如下：

| 项目 | C 本轮身份 | 明确不做 |
| --- | --- | --- |
| 策略命名空间 | `C_PRE_OUTCOME_DESIGN_V1` | 不写 B identity/spec |
| 纯函数/执行入口 | `scripts/c_pre_outcome_design.py` | 不导入 B evaluator、B shadow、B tracker |
| 测试 | `tests/test_c_pre_outcome_design.py` | 不修改 B 测试或 B fixtures |
| 研究输出 | `data/research/c_pre_outcome_design_v1/` | 不写 `data/watchlist_*.json`、runtime-state、日报或 canonical watchlist |
| 规则输出 | `C_ENTRY_OBSERVATION_DESIGN_V1`、`C_EXIT_OBSERVATION_DESIGN_V1` | 不消费收益、MFE/MAE 或 outcome label |
| 共享依赖 | 只读 `universe_policy`；数据检查只读通用 frozen manifest | 不修改共享代码，不调用 B-bound live acquisition |
| 执行异常边界 | C 只生成 research observation | C 异常不得阻断 B 收盘作业 |

本轮没有共享代码修改。`scripts/c_pre_outcome_design.py` 不导入 `b_breakout_retest*`、
`b_prospective_observation`、`t_close_runner`、`track_perf`、`render_daily_close_html` 或
任何生产调度模块。

RS/VCB 的既有研究结论保持原样；旧 A 已停止推进，旧 D 排除。它们不是新版 C 的输入或
控制变量。

## 3. 输入与时间语义

### 3.1 日线基础

一根 bar 的必需字段为 `date, open, high, low, close, volume`。所有窗口都按完成的
XSHG trading session 计数，不按自然日计数。价格必须有限且为正，`high >= open/close`，
`low <= open/close`，volume 非负，日期必须是可解析的真实日历日期且严格递增；日期字符串
本身不能用自然日占位符替代交易日序列。

本轮建议的信号 basis 是 T 时可获得的 raw/unadjusted volume 与 T-anchor 价格序列。调整
因子只可按 T 已知的事件构造 T-anchor 价格；不能把数据截止日之后才出现的 corporate action
倒灌到 T 信号。若一个来源只能提供没有 known-at 证明的后见之明复权值，该字段只能标记
`PARTIAL_UNVERIFIED`，不能成为正式 C 历史信号依据。

### 3.2 Universe

新版 C 的 universe identity 为 `C_MAIN_BOARD_NON_ST_V1`：

- `classify_board(symbol) == Main`，即沪深 00/60 系列；ChiNext 30、STAR 68 和 Unknown
  排除；
- `st_status_known_at_t == true` 是历史研究的前置条件；
- T 时名称/状态以明确的 T-known source 证明不是 `ST` 或 `*ST` 才能进入；名称缺失、
  status 未证明、current name 代替历史 status 均为 `UNRESOLVED_ST_STATUS`，不猜测；
- ST/*ST 过滤是 C 自己的 identity gate，不复用 B 的“先评估后 ST 排除”生产语义。

代码对名称仅作前缀诊断：Unicode NFKC/去显式零宽字符/trim 后，前缀 `ST` 或 `*ST`
标记 `EXCLUDED_ST_OR_STAR_ST`。正式历史研究还必须证明这个状态在 T 已知；当前冻结
manifest 没有历史逐日 ST 状态，因此该项目前是 `UNRESOLVED_FOR_HISTORICAL_PIT_UNIVERSE`。

### 3.3 Timing 与执行

- 信号只能在 T 正式收盘后计算，信号内容只看 `<= T` 的字段；
- 最早参考执行为下一个 XSHG session 的 T+1 open，或另行预注册的 T+1 参考执行；
- 新买入仓位在买入当日不得卖出；出场观察从实际可卖的下一交易日开始；
- 本轮没有合法盘中数据时，禁止用 T 收盘后才知道的全天成交量模拟 T 日盘中卖出；
- 日线 high/low 只能形成观察或 ambiguity flag，不能假设实际成交；
- 停牌、NO_TRADE、涨停无法成交、T+1 gap 或 limit-state 均进入显式执行状态，不能当作
  正常 fill。

## 4. 入场候选的精确计算定义

下列定义描述 observable。`support`、`trend`、`shallow` 等名称不是已经证明的机制；例如
“缩量=吸筹”不成立，只有“回踩期间 volume ratio 下降”这一可观察事实。

### 4.1 持续上升趋势

对 T 之前及 T 的完整前缀，计算：

\[
  MA_f(T)=mean(close_{T-f+1:T}),\quad MA_s(T)=mean(close_{T-s+1:T})
\]

以及最近 `W` 个 session 的 `log(close)` OLS slope `beta_W`，和相邻收盘上涨比例：

\[
  U_W=\frac{\#\{close_i>close_{i-1}\}}{W-1}
\]

候选趋势条件为：

1. `close_T > MA_f(T) > MA_s(T)`；
2. `beta_W > 0`；
3. `U_W >= minimum_up_close_fraction`；
4. 所有趋势窗口字段只来自 T 前缀，不要求 `close_T > max(high_{T-60:T-1})`，也不要求
   B 的 breakout event。

为了把窗口自由度限制在很小范围，当前只列两个待审计候选：

| rule id | W / fast / slow | U 下限 | 设计理由 |
| --- | --- | ---: | --- |
| `BALANCED_A` | 60 / 20 / 60 | 0.55 | 较灵敏；仍要求均线顺序和正 slope，不写 60 日新高 gate |
| `CONSERVATIVE_B` | 90 / 20 / 90 | 0.60 | 较慢；减少把单一反弹误称为持续通道 |

两者都是 candidate，不是通过收益选择的参数。Sol 需决定是否保留一个、并行作为敏感性
定义，或否定这套 trend proxy。

### 4.2 事先可确定的支撑

先在严格的 T 前缀 `bars[:T]` 中寻找已确认的 pivot low：半径 `r` 的低点 `j` 满足

\[
  low_j \le min(low_{j-r:j})\quad and\quad low_j \le min(low_{j+1:j+r+1})
\]

右侧 `r` 根也必须已经出现在 T 之前，且代码只在 `bars[:T]` 上计算 pivot；因此右侧窗口
最多结束于 T-1，不使用 T 或 T 之后的数据。输出身份固定为
`pivot_confirmation_timing=T_MINUS_ONE_CLOSE`、`pivot_uses_t_bar=false`。近期反弹高点 `R`
和 stage peak 使用同一时间点定义。

选定回踩的两个低点 `L1, L2` 后，支撑是预先存在的 zone，而不是用 T 日低点倒推：

\[
S_{floor}=min(L1,L2),\quad S_{ceiling}=max(L1,L2)
\]

候选容差 `support_tolerance × S_floor`（A=1.0%，B=1.5%）当前仅是展示字段，代码输出
`support_tolerance_role=DISPLAY_ONLY`；它不改变支撑 floor、entry candidate 或 exit event，
也不能在看到结果后扩大 zone。

支撑事件严格分开记录：

- `T_INTRADAY_PUNCTURE_RECOVERED`：`low_T < S_floor` 且 `close_T >= S_floor`；这是 T 日盘中
  刺破后收回的日线 proxy，不等同收盘跌破；
- `T_CLOSE_BREAK`：`close_T < S_floor`；这是 T 日收盘跌破；
- `PULLBACK_SUPPORT_DESTROYED`：在完整的 pre-T 回踩区间 `P+1:T-1` 内至少一根 bar 的
  `close < S_floor`；T 日事件不混入此字段；
- 回踩期间只有 low 下破但当日收回时，单独计入
  `PULLBACK_INTRADAY_PUNCTURE_RECOVERED`，不填作收盘破坏。

`entry_candidate` 要求没有 pre-T `PULLBACK_SUPPORT_DESTROYED` 且 T 日没有 `T_CLOSE_BREAK`；
T 日的 `T_INTRADAY_PUNCTURE_RECOVERED` 仍保留为显式诊断，不因展示容差静默改变候选。

### 4.3 浅回踩

取两个回踩低点之前最近已确认的 stage peak `P`，`P` 是 pullback 起点的价格结构，
不是“过去 60 日最高点”的强制替代。回踩区间为 `P+1` 到 T-1：

\[
  depth=\frac{P_{high}-min(low_{P+1:T-1})}{P_{high}}
\]

同时要求 `T - P_index` 不超过候选的最大回踩 session 数（A=20，B=25），且

- A：`0.03 <= depth <= 0.12`；
- B：`0.04 <= depth <= 0.15`。

这两个候选只是“浅”的少量事前定义；它们不等同旧 C 的 5%–22%，也不与 30% prior run-up
绑定。没有收益证据时不得增加第三个窗口或把下限/上限向结果方向移动。

### 4.4 两个不同的回踩低点及更高低点

`L1`、`L2` 必须是两个不同日期的 confirmed pivot low，间隔至少 A=3、B=4 个 session，
并且

\[
  low_{L2}>low_{L1}
\]

不使用“差一点也算更高”的结果后容差。实现选择满足结构、深度和后续 rebound 已确认的
最近合法 pair；找不到 pair 就是 `NO_DISTINCT_HIGHER_LOW_PAIR`，不能退回到单一低点。

### 4.5 近期小反弹高点

在 `L2` 之后、T 之前寻找 confirmed pivot high `R`。要求：

\[
  rebound=\frac{R_{high}-low_{L2}}{low_{L2}}
\]

- A：`0.02 <= rebound <= 0.08`；
- B：`0.02 <= rebound <= 0.10`。

`R` 是 T 收盘确认的结构参考，不是目标价，也不应被称为已经证明的需求回归。没有
confirmed `R`，不能把普通上涨日当作“小反弹高点”。

### 4.6 T 日收盘向上确认

T 日 confirmation 为全部条件同时满足：

1. `close_T > R_high`，严格重新站上近期小反弹高点；
2. `close_T > close_{T-1}`；
3. `close_T > open_T`；
4. 收盘位置
   `CLV_T=(close_T-low_T)/(high_T-low_T)` 至少为 0.60（零波幅 bar 使用显式边界规则）；
5. `support_floor`、`R`、stage resistance 来自 T 之前已确认的结构。
6. pre-T 回踩没有支撑收盘破坏，且 T 日没有收盘跌破；若 T 日只是盘中刺破后收回，保留
   独立状态，不与收盘跌破混称。

这不是要求突破阶段前高，也不是近期 60 日新高条件。T 只产生 `entry_candidate`；
实际能否在 T+1 成交要另分执行状态。

### 4.7 阶段前高阻力

当前回踩开始处的 confirmed `P_high` 作为 `stage_prior_high`。它是入场后的阻力参考，
并保留：

\[
  resistance\_distance=\frac{stage\_prior\_high-close_T}{close_T}
\]

“靠近前高”是观察字段，不成为 entry hard gate。当前 A/B 的 near-resistance 容差分别为
1.0%/1.5%，只用于展示前高距离和前高附近事件；不得因为历史结果优化该容差或把它静默
改成入场排除条件。

## 5. 成交量、K 线和“炸板”的独立定义

### 5.1 相对自身历史的异常量

对 T 或任意观察日 `i`，只用 `i-L` 到 `i-1` 的 raw volume：

\[
  RV_i=\frac{volume_i}{median(volume_{i-L:i-1})}
\]

同时记录 robust z-score：

\[
  z_i=\frac{volume_i-median(V)}{1.4826\times MAD(V)}
\]

当前出场协议草案固定 `RV >= 2.0` 为量价版本的实际异常量条件；`robust-z >= 3.0` 保留为
观察字段，不作为 hard gate。median/MAD 仍用于记录 robust-z；mean/std 不是本轮定义，也不
新增第三种异常定义。该安排是 outcome 前的预注册候选，尚未由收益选择或升级为生产规则。

### 5.2 回踩期间的量能路径

基准为回踩起点之前固定 `L=20` 个 session 的 volume median；回踩期间记录：

- `pullback_volume_median / reference_volume_median`；
- 每日 ratio 序列和末段 ratio；
- observable path label：ratio <=0.80 为 `CONTRACTED_OBSERVABLE`，ratio >=1.20 为
  `EXPANDED_OBSERVABLE`，中间为 `MIXED_OBSERVABLE`，基准为零或样本不足为
  `UNDETERMINED`。

“CONTRACTED_OBSERVABLE”只说明成交量下降；不能写成吸筹、卖方耗尽或资金流入已经被证明。

当前代码已实现：回踩/参考区间中位量、回踩相对参考中位量比、三档 path label，以及上涨日/
下跌日计数和量能中位数。代码未实现每日 ratio 序列或末段 ratio；它们仍是未来研究设计，
不能在输出中被当作已实现指标。

### 5.3 上涨日与下跌日量能关系

在同一回踩区间内，按 `close_i > close_{i-1}`、`close_i < close_{i-1}`、相等分别分类，
相等日不进入分子或分母。分别取上涨日/下跌日 volume median，并记录：

\[
  UD=\frac{median(volume_{up})}{median(volume_{down})}
\]

若任一方向少于 2 个有效日，`UD` 数值保持缺失并输出
`up_down_ratio_status=INSUFFICIENT_DIRECTIONAL_DAYS`；若下跌日中位量为零则输出
`ZERO_DOWN_DIRECTIONAL_VOLUME`，也不填中性值。同时保留 up/down 日数，避免用一个极少数
上涨日制造量能不对称故事。

### 5.4 反弹量价配合

当前代码实现 T 日 `RV/z/CLV/body` 和回踩 path/UD 观察。反弹收益、正收盘日比例、正收盘
日 volume median、反弹 volume median 相对回踩基准 ratio 尚未实现；它们只是未来比较设计，
本轮没有将 volume 写成入场 hard gate。

协议草案只比较两个清晰版本：

- `PRICE_STRUCTURE_ONLY`：入场只使用第 4 节价格结构，volume 全部为诊断字段；
- `PRICE_STRUCTURE_PLUS_VOLUME`：在同一价格结构样本上，固定使用
  `RV_T >= 2.0`（前 20 个完成交易日的自身中位量为基准）作为唯一主 gate；回踩 path、UD
  和 robust-z 只作描述，不能在结果出来后替换或叠加。

这样可区分“成交量是否增加可预测信息”和“加入多个 volume 条件后样本被重新选择”。

### 5.5 前高附近放量但缺少有效价格推进

在 `stage_prior_high` 的 tolerance 区域内，逐日记录：

- `RV` 或 robust z；
- `body_return=(close-open)/open`；
- `close_location`；
- upper/lower shadow fraction；
- `high` 相对前一次 push high 的推进；
- 是否 close 仍低于 stage resistance。

候选 observable flag：`RV >= 2.0`、`abs(body_return) <= 0.5%`、`close_location <= 0.60` 同时
成立，命名为 `HIGH_VOLUME_LOW_PRICE_PROGRESS`。实现使用 `RV >= 2.0` 作为量价版本的实际
确认条件；robust-z `>=3.0` 只保留为观察字段，二者都不是收益选择结果。该 flag 本身不
包含前高距离；只有 `PRICE_VOLUME_EARLY_DEFENSE` 在当前日也满足 H 附近受阻时才可消费它。
它不是“派筹已证明”；机制解释保持
`UNKNOWN / HYPOTHESIS`，可替代解释包括新闻/市场波动、涨停规则、拥挤交易和价格离散化。

### 5.6 K 线实体、影线、连续冲高失败和炸板

每根 bar 保留：

\[
body=(close-open)/open,\quad
CLV=\frac{close-low}{high-low},\quad
upper=\frac{high-max(open,close)}{high-low},\quad
lower=\frac{min(open,close)-low}{high-low}
\]

前高失败 push 定义为：对入场后的观察日，在最近 5 个交易日（含当前日）内统计同时满足
`high >= H(1-tolerance)`、`close < H`、`CLV <=0.60` 的失败；重复受阻的主定义是最近 5
个交易日内至少 2 次且当前日失败，不是严格相邻两天。入场后出场观察只从持仓建立后的
`entry_index+1` 开始记录。记录失败次数和从当前观察日向后连续失败次数，但严格相邻只作
描述字段，不自动升级交易规则。`upper_shadow_fraction` 仍可作为 K 线描述字段，但正上影
线只要大于零不构成显著转弱条件，也不构成成交量确认；它不参与提前防守候选判定。

“炸板”只在输入含有合法、T-known 的 `limit_up_price` 与 `tick_size` 时计算：

- `limit_up_touched = high >= limit_up_price - tick_size/2`；
- `limit_up_failed_to_hold = touched and close < limit_up_price - tick_size/2`。

日线 high 不能证明触及时间、排队、成交量或能否卖出；没有 limit price/tick 或存在首日/特殊
涨跌停规则时标为 `UNAVAILABLE`，不按 close/high 猜测。没有盘中数据时，本字段只能是日线
proxy，不可模拟盘中卖出。

## 6. 出场作为独立研究对象

出场不反向改变入场样本，也不把 B 的 stop/target/RR 复制为 C 规则。所有出场信号均为
T close 观察，最早下一可卖 session 执行参考。

### 6.1 三个时间层级

| 层级 | observable 定义 | 默认动作语义 |
| --- | --- | --- |
| 首次预警 | 持仓建立后当前日首次接近 H，high 触及 tolerance、close 低于 H、CLV <=0.60；没有更早的 post-entry failed push | `FIRST_RESISTANCE_REJECTION_WARNING`，只预警，不卖出 |
| 重复受阻风险 | 当前日再次在 H 附近受阻，且最近 5 个交易日已有至少 1 个更早的 failed push，但所选提前防守版本尚未满足 | `REPEATED_RESISTANCE_REJECTION_RISK`，明确记录风险，不伪装成普通持有 |
| `PRICE_ONLY_EARLY_DEFENSE` | 同一持仓、当前日再次在 H 附近受阻；最近 5 个交易日内至少 2 次 failed push（含当前）；当前 close 高于 entry reference | `EARLY_PROFIT_TAKING_CANDIDATE`，价格基线候选；不称为量价确认退出 |
| `PRICE_VOLUME_EARLY_DEFENSE` | 完全相同的持仓与价格事件，且当前日满足 H 附近的 `HIGH_VOLUME_LOW_PRICE_PROGRESS`；实际量价确认使用 `RV >= 2.0`、实体绝对涨跌幅 `<=0.5%`、`CLV <=0.60` | `EARLY_PROFIT_TAKING_CANDIDATE`，量价版本候选 |
| 晚期支撑破坏 | `close_t < support_floor`；T 日盘中刺破后收回不计作收盘破坏 | `KEY_SUPPORT_BREAK`，若仍盈利是保护利润，若不盈利是入场后风险退出 |

一次首次预警不能自动升级为出场；同一日多个 flags 保留，优先级为支撑破坏 > 所选提前防守
版本 > 重复受阻风险 > 首次预警。`classify_exit_observation()` 的
`early_defense_version`、`price_only_early_defense_candidate`、
`price_volume_early_defense_candidate` 和 `volume_confirmation` 必须一起解释；价格基线的
触发不含成交量确认。异常量若远离 H，只能保留为 observable，不能直接和历史失败次数组合
成提前退出。真正的 sell 只能从 entry session 的下一个 XSHG session 开始。

### 6.2 获利退出与入场后风险退出

- `PROFIT_EXIT`：参考价格高于实际 entry price，并满足提前兑现或支撑破坏的退出候选；
  这是保护已有盈利的研究候选，不是保证卖在最高点；
- `ENTRY_RISK`：支撑破坏时参考价格不高于 entry price；不与获利退出混称；
- `WARNING_ONLY`：不产生卖出指令；
- `EXECUTION_UNCERTAIN`：停牌、NO_TRADE、limit-state、缺开盘或无法证明 fill 时不假设成交。

当前实现只返回 `C_EXIT_OBSERVATION_DESIGN_V1`，并要求两个显式观察版本之一；它不写 trade
tracker，不改 B 的收益跟踪，也不声称已经发生卖出。量价版本的 `RV >= 2.0` 是当前协议
草案的事前固定候选，`robust-z >= 3.0` 仅作观察；二者不能读取收益后再挑选。若价格版本
达到候选而量价版本未达到，对量价版本必须输出重复受阻风险，不得悄悄归为毫无异常的普通持有。

### 6.3 假警报、卖飞和重新观察的预注册评价

正式 outcome 研究前固定以下评价，不在看到结果后改变：

- 假警报：首次预警后固定 5/10 个 XSHG session 内没有关键支撑破坏，且未发生预先定义的
  executable exit；分别报告后续 MFE/MAE 和是否重新站回 H；
- 卖飞：提前兑现候选后的固定窗口内，价格重新收于 H 上方并创出新的阶段高点，且退出前
  没有支撑破坏；报告退出后 MFE，不把所有上涨都事后叫卖飞；
- 漏报：没有提前兑现候选而随后出现支撑破坏；
- 重新观察：预警/候选退出后，支撑未破坏且出现一次新的 T-close `close > H`，只产生新的
  observation identity，不把旧仓位偷偷复活；重新入场需独立授权，不在本轮定义。

比较继续持有和提前防守时，使用同一 entry sample、同一 T+1 参考执行、同一成本和同一
可卖约束；不能用更有利的 fill 给提前防守版本。

## 7. 数据可行性结论

机器可读检查为
[`data_dependency_check.json`](../../data/research/c_pre_outcome_design_v1/data_dependency_check.json)，
详细说明见 [`c_data_feasibility_v1.md`](c_data_feasibility_v1.md)。当前结论不是简单的
“可用/不可用”二元结论：

| 能力 | 当前结论 | 对正式 C 研究的影响 |
| --- | --- | --- |
| daily-K 字节身份 | 外部现存 worktree 只读实际大小 `180203424` bytes、SHA-256 与 frozen 声明完全匹配；证据见 `data/research/c_pre_outcome_design_v1/daily_k_integrity_check.json` | `VERIFIED` 仅限 artifact identity；本 C worktree 仍缺文件，未作为本轮 replay 输入 |
| 日线 OHLCV schema | manifest 声明 `open/high/low/close/volume`，volume 为 raw unadjusted | 价格结构、volume ratio 公式可设计；字段语义仍以 manifest 声明为主 |
| 交易日历 | 769 个连续 XSHG session，Asia/Shanghai，现有 calendar helper | T-close/T+1 窗口可确定 |
| 复权 | T-anchor 价格公式和 raw volume 已声明；corporate-action event filter 为 `date < ex_date <= T` | 可定义信号 basis；逐 bar vintage proof 仍缺失 |
| known-at / PIT | `known_at_vintage_proof=false` | retrospective outcome 研究 `PARTIAL_UNVERIFIED`，不得直接宣称严格 PIT |
| 主板 | 通用 board classifier 可用 | 00/60 与 30/68/Unknown 可确定区分 |
| ST/*ST | 当前 manifest 没有历史逐 T status | 历史 C universe 暂不能合法声称“已排除 ST/*ST”；必须补 T-known status evidence |
| 日成交量 | 可算 relative volume、path、UD、stall proxy | 可研究 observable；不能证明吸筹/派筹 |
| 盘中/成交 | 当前没有合法盘中序列、order book 或 actual fill | 炸板时间/卖出成交标 `UNKNOWN/EXECUTION_UNCERTAIN`，不得模拟 T 日盘中卖出 |
| 涨停/停牌/NO_TRADE | quote trade-state helper 可识别部分显式状态；日线本身不够推断 fill | entry/exit 必须保留 `NO_TRADE`、limit-state、missing-open 和 uncertain 分类 |
| 可重放性 | manifest 有 source/hash/determinism 元数据；外部文件 identity 已验证，但核心 K 在本 C worktree 缺失 | artifact identity 可复核；实际 C replay 仍未授权且未运行，外部路径不能冒充本地输入 |

因此：新版 C 的**研究前设计、数据证据记录和预注册协议草案可交付 Sol 决策**；正式历史收益研究当前不 ready，至少
等待合法可恢复的 daily-K 与 T-known ST 状态证据，且需要解决或明确限定逐 bar known-at
缺口。本轮没有抓取、重写或替代这些输入。

## 8. 未来研究的预注册比较方法（本轮只设计）

### 8.1 入场比较

协议草案建议以 `BALANCED_A` 为主定义、`CONSERVATIVE_B` 为敏感性定义；理由和“待采纳”
状态见独立协议文件。至少比较同一 universe、同一 T+1 执行模型和同一成本下的三层：

1. `SIMPLE_TREND_MOMENTUM_BASELINE`：只用预先固定的上升趋势/ trailing momentum；不使用
   C 的双低点、rebound、stage resistance 或 volume；
2. `PRICE_STRUCTURE_ONLY`：加入本文件第 4 节价格结构，不使用 volume 作为 hard gate；
3. `PRICE_STRUCTURE_PLUS_VOLUME`：在完全相同的价格结构样本上加入 outcome 前固定的
   `RV_T >= 2.0` gate；robust-z `>=3.0`、path 和 UD 只作描述。

不比较旧 C 与新版 C 的事后收益优劣；旧 C 只做 provenance 说明，不是 baseline。

### 8.2 出场比较

固定同一模拟持仓、entry cohort、T+1 reference execution、费用/滑点模型和 sellability：

- `CONTINUE_HOLDING`：不使用 C 的提前防守候选，直到统一固定 horizon 或关键支撑规则；
- `PRICE_ONLY_EARLY_DEFENSE`：使用价格基线的重复受阻候选；不消费 volume confirmation；
- `PRICE_VOLUME_EARLY_DEFENSE`：在完全相同的持仓和价格事件上，额外要求事前固定的当前日
  H 附近放量滞涨 observable；首次预警仍只记录，重复受阻未达条件仍保留风险状态。

两个提前防守版本各自与继续持有报告相同 horizon 的 return、MFE、MAE、执行不确定比例和
成本后结果。没有合法
   intraday data 时，不能用 close-after-volume 伪造当日卖出。

### 8.3 固定评价维度与否定条件

在 outcome access 前固定：

- horizon：至少 T+3、T+5、T+10 XSHG sessions；出场预警的后续 5/10 sessions；
- event 去重：同一 symbol 的连续结构属于同一 pullback episode；episode identity 由
  `(symbol, stage_prior_high_date, L1_date, L2_date, confirmation_date, rule_id)` 固定；
  同一 episode 不因多日观察变成独立事件；
- sample coverage：overall、Main Board 子集、年度/市场阶段、可执行/不确定/NO_TRADE 分层；
  不用当前 universe 回填过去；
- 稳定性：年度方向、日期等权均值、symbol/month concentration、episode-deduplicated count；
- path metrics：MFE/MAE、假警报率、卖飞率、漏报率、重观察率；
- costs：同一固定 fees/slippage/price-limit treatment，若项目没有合法成本来源则显式
  `TRANSACTION_COST_MODEL_NOT_PREEXISTING`，不能事后选成本；
- execution：T+1、entry no same-day exit、missing open、NO_TRADE、limit-state、
  suspended、ambiguous same-bar 都单独报告；
- 否定条件：若价格结构相对简单趋势基线无稳定增量、volume gate 只改变样本且无跨年稳定性、
  出场防守在成本和可执行性后没有减少 MAE 或只是显著增加卖飞，则对应假设
  `REJECT` 或 `NEEDS_MORE_EVIDENCE`；不得自动加指标、改窗口、换 subgroup 或换 horizon。

缺少合法时间点证据的控制变量（历史 ST status、逐 bar vintage、盘中 fill、turnover/order
flow）必须列为限制，不得用当前数据回填。

## 9. 待 Sol 审计的关键规则与证据

关键规则：

- A/B trend candidate 是否构成“持续上升”且没有隐含 breakout gate；
- A/B 浅回踩和 rebound 深度是否过多自由度；
- `L1/L2` pivot 半径、间隔和严格 higher-low 规则；
- stage resistance 是仅描述还是入场 headroom hard gate；
- volume anomaly 选 ratio 还是 robust-z，volume 是否只作 diagnostic 还是允许一个 hard gate；
- 首次拒绝、连续失败、high-volume-low-progress 和关键支撑破坏的优先级；
- one-close support break 与 two-close confirmation 的主定义；
- daily `炸板` proxy 在 limit price/tick 缺失时必须保持 UNKNOWN；
- T+1 entry、new-position no-same-day-sell、无法成交和无盘中数据的 fail-closed 语义。

需要核对的 evidence：

- frozen OHLCV 的真实字段 schema、恢复来源、bytes/SHA 和合法 known-at 证明；
- 历史 T-known ST/*ST status 或明确限制正式样本范围的授权；
- XSHG calendar version/session mapping；
- T-anchor adjustment event 的可追溯性和 future event 排除；
- quote trade-state、limit price/tick、停牌/涨停及 T+1 fill classification 的实际字段；
- C 专属输出 identity 不写入 B canonical/runtime/report 的静态和运行时证明。

内部测试只证明纯函数边界和合成样本可重复，不等于上述 Sol 审计 evidence 已通过。

## 10. 本轮交付文件与验证

- `scripts/c_pre_outcome_design.py`：C 独立规则纯函数、数据检查 CLI；
- `tests/test_c_pre_outcome_design.py`：C 聚焦合成/边界回归，覆盖趋势反例、支撑事件、严格
  pre-T pivot、出场时序、量能最小样本、日期和 T/T+1 边界；
- `data/research/c_pre_outcome_design_v1/data_dependency_check.json`：只读 manifest/本地
  存在性检查，包含 `c_outcome_accessed=false` 等边界字段；
- `data/research/c_pre_outcome_design_v1/daily_k_integrity_check.json`：授权范围内对外部现存
  daily-K 的只读大小/SHA-256 核验（文件 SHA-256：
  `2a0496e3414b4bd43969f66f7cf93c2b7a1e4a698266abdc74243f662799f939`）；仅证明 artifact
  identity，不把文件作为本 C replay 输入；
- `docs/research/c_pre_outcome_preregistration_protocol_v1.md`：独立的 outcome 前协议草案，
  固定比较、窗口、事件去重、执行和否定条件（文件 SHA-256：
  `c74447608490fdd7068ea4a018dc3be31358198d3570ead878e5095cc09befd3`），但尚未由 Sol/用户采纳；
- 本文件与 `c_data_feasibility_v1.md`：规则、数据、比较方法和审计问题。

本轮不创建 C 正式 signal membership、outcome detail、收益表或 canonical watchlist。若未来
要创建这些文件，路径必须继续位于 `data/research/c_pre_outcome_design_v1/` 下，并使用新的
明确 protocol/spec identity。

历史旧终态（已不代表当前交付）：`C_PRE_OUTCOME_CORRECTNESS_FIX_READY_FOR_SOL_REAUDIT`。

当前交付终态：`C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION`。本文件不宣称 Sol
审计通过，也不授权读取 C future outcome。
