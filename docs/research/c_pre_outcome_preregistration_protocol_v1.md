# C_PRE_OUTCOME_PREREGISTRATION_PROTOCOL_V1

状态：`DRAFT_FOR_SOL_DECISION`；当前决策：`NEEDS_MORE_EVIDENCE`。

本文件是新版 C 的独立、研究前、未读取 outcome 的预注册协议草案。它不冻结参数、不
授权正式历史 replay，不是收益结论、Final OOS 结论、production 规则或 Sol 审计通过证明。
当前终点为 `C_DATA_EVIDENCE_AND_PROTOCOL_READY_FOR_SOL_DECISION`；Sol/用户下一轮审计后
再决定是否采纳、缩窄或否定本协议。

## 2026-09-23 prospective input amendment — `C_QFQ_INPUT_V1`

用户已为**前瞻 T-close 输入**选择 A：`C_QFQ_INPUT_V1` 仅使用 B 当日已冻结的
`PROVIDER_QFQ_SNAPSHOT` 股票历史 OHLC 作为 C 的价格输入。它是独立于下文原始
未复权设计的输入版本；两版本不得混算、合并样本或共享收益结论。此选择不代表 qfq
收益优于未复权，不批准正式历史收益研究，也不改 Formal B。`BALANCED_A` 和
`CONSERVATIVE_B` 的现有趋势、回踩、确认、支撑、阻力与退出结构参数保持原值，
不按收益调整。

HiThink 历史接口将 `volume` 声明为股；B 的归一化直接保留响应中的数值。该接口没有
明确说明 `adjust=forward` 对 `volume` 的影响，因此 `C_QFQ_INPUT_V1` 将 volume
调整语义记为 `UNRESOLVED`，保存 B 冻结的逐日数值、来源和由它计算的研究特征。
`VOLUME_FEATURE_COMPUTED` 表示数值已计算；`VOLUME_BASIS_UNVERIFIED` 表示
`adjust=forward` 的量能语义尚无证据；两者可以同时成立。回踩期间沿用现有中位数
基准和上涨/下跌日口径，另记录按时间等分的前后半段中位数及后/前比值，均只作描述，
不增加阈值或 gate。`PRICE_STRUCTURE_PLUS_VOLUME`、
`PRICE_VOLUME_EARLY_DEFENSE` 等量价确认均不能作为本版本正式有效信号，直至单位、
调整路径和同日原始证据核验通过。下文 raw unadjusted volume 是原草案历史定义，
不自动迁移为 qfq 版本的已验证量能口径。

## 1. 研究问题、materiality、输入与停止条件

研究问题：在沪深普通主板、且每个 T 都能证明当时不是 ST/*ST 的可比 universe 中，比较
简单趋势/动量、价格结构和价格结构加成交量，是否能在 T 收盘形成可复核的新版 C 入场观察；
在同一持仓、同一价格事件、同一成本和执行约束下，比较继续持有、价格提前防守和量价提前
防守的观察差异。

这里必须区分两个层次：`FULL_COMPARABLE_UNIVERSE` 是在 T 日先完成身份、ST、OHLCV、历史
前缀和数据质量核验后的全量可比 security-date 范围；`MATCHED_EVENT_SAMPLE` 是某个入场
规则实际满足其事前定义后的事件样本。不同入场规则会产生不同的 matched event sample，
不能因为它们共享 full comparable universe 就声称天然拥有相同 entry cohort。任何跨规则
比较若需要相同样本，必须另外预先构造并记录明确的匹配/交集身份和损失的样本数。

Materiality：如果入场样本、前高受阻、量能确认、支撑失效和执行时间没有在 outcome 读取
前固定，后续差异无法归因于 C 定义；如果历史 ST、known-at 或成交证据不足，则不能把
历史探索写成严格 PIT 或真实成交结论。

本协议只允许使用：

- 已声明身份并通过完整性核验的 OHLCV/交易日历/调整因子输入；
- T 前缀可计算的价格与 raw unadjusted volume observable；
- C 专属、可审计的 T-close signal identity 和未来执行分类。

停止条件：任一关键输入没有合法时间点证据，或发现样本、窗口、阈值需要看 outcome 才能
决定时，停止并记录 `UNRESOLVED`/`PARTIAL_UNVERIFIED`/`EXECUTION_UNCERTAIN`，不补数据、
不重采样、不新增第三套退出方案。

## 2. 研究证据模式

协议严格区分三种模式，不把一种模式的结论升级成另一种模式：

| 模式 | 必要条件 | 当前状态与允许语义 |
| --- | --- | --- |
| `PIT_HISTORICAL_RESEARCH` | daily-K 身份、T-known ST/*ST、逐 bar known-at/vintage、复权和执行边界均可证明 | 当前 `UNRESOLVED`；未运行；条件满足后才可形成历史研究结论 |
| `EVIDENCE_LIMITED_HISTORICAL_EXPLORATION` | 明确标注缺失证据和样本边界，并取得 Sol/用户对 `PARTIAL_UNVERIFIED` 范围的接受 | 当前仅保留为可能的受限研究模式；不得宣称严格 PIT、不得调参或晋级 |
| `PROSPECTIVE_OBSERVATION` | 每次 T-close 记录当时可见输入、known-at、C 专属 identity，并以 T+1 参考执行等待观察 | 优先只读复用 B 已冻结的原始收盘输入，由 C 独立计算规则；绝不复用 B 候选结论或把事后数据标为当时捕获 |

## 3. 入场研究定义

### 3.1 Universe 与两个既有候选

Universe identity 固定为 `C_MAIN_BOARD_NON_ST_V1`：00/60 Main Board；30/68 和 Unknown
排除；每个 T 必须有 `st_status_known_at_t=true` 且明确不是 ST/*ST。当前名称、采集日期或
后来状态不能回填历史 T。

保留现有两个候选，不创建第三个：

| 候选 | 既有定义 | 协议草案角色 | 事前理由（不是收益选择） |
| --- | --- | --- | --- |
| `BALANCED_A` | trend window 60、MA 20/60、上涨收盘比例下限 0.55，现有 A 的 pivot/pullback/rebound/resistance 定义 | **建议主定义，待 Sol/用户采纳** | 窗口较短、可复核性与反应速度平衡；作为主定义更少把单次反弹拖成长周期趋势，也不引入近期 60 日 breakout gate |
| `CONSERVATIVE_B` | trend window 90、MA 20/90、上涨收盘比例下限 0.60，现有 B 的其余结构定义 | **建议敏感性定义，待 Sol/用户采纳** | 更长趋势和更高上涨比例检验“持续上升”是否依赖较宽松定义；它只承担敏感性，不因结果好坏替代主定义 |

这里的“主/敏感性”是研究前的可审计安排，不是参数选择或收益选择。若 Sol/用户不接受
该安排，协议停在 `NEEDS_MORE_EVIDENCE`，不自行改窗口。

### 3.2 三层入场比较

三层先使用同一 `FULL_COMPARABLE_UNIVERSE`、同一信号日 T、同一 T+1 参考执行和同一
成本/可成交性分类；每层实际形成的 `MATCHED_EVENT_SAMPLE` 单独记录，不把不同规则的
entry cohort 视为相同：

1. `SIMPLE_TREND_MOMENTUM_BASELINE`：只使用预先固定的趋势/动量 observable，不使用双低点、
   higher-low、rebound、stage resistance 或 volume 作为 hard gate；
2. `PRICE_STRUCTURE_ONLY`：在完全相同的样本范围加入现有第 4 节价格结构；volume 只记录，
   不改变 membership；
3. `PRICE_STRUCTURE_PLUS_VOLUME`：在第 2 层的价格结构事件上增加下述一个、事前固定的
   volume gate；必须同时保留它自己的 matched event sample 与相对于价格结构样本的
   membership 差异，不允许把 path、UD、ratio 和 robust-z 叠加成多个 gate。

### 3.3 成交量主假设与观察字段

入场量价版本的固定主假设为：

`RV_T >= 2.0`，其中 `RV_T = volume_T / median(volume_{T-20:T-1})`，只使用 T 之前的
20 个完成交易日作为基准；它**只检验确认日 T 的放量**。它不能代表完整回踩期间的量能
路径，也不能替代回踩 path、上涨/下跌日量能或其他独立观察。该 gate 只描述 T 日成交量
相对自身历史的异常，不解释为吸筹、派筹或因果机制。

`robust-z >= 3.0` 只保留为观察字段，不能作为本协议的 hard gate，也不能在看 outcome
后将它替换为主假设。回踩 path、上涨/下跌日 UD、body、CLV 和 upper shadow 同样只作
描述或覆盖诊断，除协议明确列出的量价出场条件外不得改变入场样本。该主假设是预先固定的
候选，不是从收益选择出来的正式参数。

## 4. 样本、事件去重与评价窗口

- 全量可比 universe 按 `symbol × signal_date(T)` 记录；规则事件样本按
  `symbol × signal_date(T) × rule_id × entry_definition` 记录。不同规则的 matched event
  sample 必须分别计数和持久化，不能把不同 entry rule 的结果写成相同 entry cohort。
- 若需要公平的跨规则差异，必须在 outcome 前固定 `matched_event_sample_id` 的构造方法；
  未显式构造时，只能分别描述各自样本，不能用事后交集或结果筛选替代。
- 同一 pullback episode 的 identity 固定为
  `(symbol, stage_prior_high_date, L1_date, L2_date, confirmation_date, rule_id)`；同一
  episode 多日观察不拆成多个独立事件。重复信号必须保留原 identity 并记录重复原因。
- 入场信号为 T 日收盘后形成；固定报告 T+3、T+5、T+10 个 XSHG session，窗口不因结果改变。
  每个窗口同时报告可用性和缺失原因，不把无法成交当作正常收益。
- 成本、滑点、涨跌停处理、停牌、NO_TRADE、缺开盘和实际 fill 分类在 outcome 前固定；
  在正式收益研究开始前必须固定统一成本模型、版本身份和可追溯来源。若项目没有合法
  成本来源，写 `TRANSACTION_COST_MODEL_NOT_PREEXISTING`，不得利用未来收益选择费率、
  滑点或成本处理。

### 4.1 观察日浮盈与 T+1 参考执行盈亏

- `OBSERVATION_DAY_FLOATING_PNL` 只表示某个观察日收盘按统一 entry reference 做的
  mark-to-market 状态；它不是该日可执行的成交价，也不等于已经完成退出。
- `T_PLUS_ONE_REFERENCE_EXECUTION_PNL` 只从信号 T 后下一个 XSHG session 的预注册参考执行
  （默认 T+1 open）开始计算，并单独记录参考执行、成本和可成交性分类。
- T-close 捕获阶段在 T+1 参考执行尚未发生前不写收益；不能把 T 日收盘观察的浮盈/浮亏
  字段当作 T+1 参考执行后的盈亏，也不能用未来价格回填当时的观察记录。

## 5. 出场研究定义

三种出场观察在**同一持仓、同一 entry cohort、同一 entry price/reference、同一价格事件、
同一成本和同一 sellability 约束**下比较：

| 版本 | 观察/动作语义 |
| --- | --- |
| `CONTINUE_HOLDING` | 保留所有 warning/risk flags 作为观察，但不使用提前防守候选；到固定 horizon 或独立支撑失效路径 |
| `PRICE_ONLY_EARLY_DEFENSE` | 当前价格事件满足重复受阻和盈利条件即可产生价格基线的提前退出候选；不消费 volume confirmation |
| `PRICE_VOLUME_EARLY_DEFENSE` | 完全相同的价格事件上，再要求当前日 H 附近合法的放量滞涨确认；不把价格基线触发称为量价确认退出 |

### 5.1 前高失败的唯一主定义

对持仓建立后的可观察日，从 `entry_index + 1` 开始：失败 push 必须同时满足

`high >= H * (1 - resistance_tolerance)`、`close < H`、`CLV <= 0.60`。

“重复冲高失败”固定为：**最近 5 个交易日内至少 2 次，且当前日就是失败日**。这不是
“严格相邻两天”；严格相邻失败次数只作 `consecutive_failed_pushes_at_end` 描述字段，不
新增交易规则。当前失败但最近 5 日只有一次（或没有）时，不得触发重复受阻候选。

### 5.2 四种独立状态

每个观察日保留独立 flags；一个 flag 不覆盖另一个：

- 首次受阻预警：当前日首次失败，输出 `FIRST_RESISTANCE_REJECTION_WARNING`，只预警；
- 重复受阻风险：当前日失败且最近 5 日已有至少一次更早失败，但尚未达到所选版本的
  提前退出条件，输出 `REPEATED_RESISTANCE_REJECTION_RISK`；不得对外写成无异常普通持有；
- 提前退出候选：价格版本或量价版本分别满足各自条件，输出版本字段和
  `EARLY_PROFIT_TAKING_CANDIDATE`；
- 支撑失效：`close_T < support_floor` 输出 `KEY_SUPPORT_BREAK`，与上述受阻状态独立，
  盘中刺破后收回不冒充收盘失效。

如果同一日多个 flags 同时存在，输出必须保留完整 flags 和所选版本；展示上的主状态可以
按既有支撑优先级排列，但不能删除重复风险或把它静默降级为普通持有。

### 5.3 两种提前防守的差异

`PRICE_ONLY_EARLY_DEFENSE` 的候选条件是：当前日失败、最近 5 日失败次数至少 2（含当前）、
当前 close 高于 entry reference。它是价格基线，不包含任何成交量确认。

`PRICE_VOLUME_EARLY_DEFENSE` 先满足完全相同的价格条件，再要求当前日处于 H 的候选容差内，
且同时满足：

- `RV >= 2.0`；
- `abs(body_return) <= 0.5%`；
- `CLV <= 0.60`。

`robust-z >= 3.0` 在本版本只观察，不改变候选。`upper_shadow_fraction > 0` 只保留为
K 线描述，不能冒充显著转弱，也不能冒充成交量确认。放量但远离 H 时只能记录 observable；
入场前出现放量、入场后没有合法放量事件时不得倒灌为出场条件。

因此同一价格事件可以出现：价格版本为候选、量价版本为重复受阻风险；这是预期的研究
对照差异，不是语义冲突。不得新增第三套提前退出方案。

## 6. 执行时间与无法成交

- T 日收盘信号只在收盘后形成；不能倒推 T 日盘中卖出，也不能用收盘后才知道的全天 volume
  模拟 T 日卖出；
- 最早参考执行固定为下一个 XSHG session 的 T+1 open；新建仓位禁止 entry session 当日卖出；
- `TRADED`、`NO_TRADE`、`UNKNOWN`、`SUSPENDED`、`LIMIT_UNSELLABLE`、`MISSING_OPEN` 和
  `EXECUTION_UNCERTAIN` 分开记录；没有实际成交数量时不写成 fill；
- daily high/low 只有在有合法 T-known limit price/tick 时才可作为日线 proxy；没有盘中序列
  时不推断触及时间、排队或成交量。
- 观察日浮盈/浮亏与 T+1 参考执行后的盈亏必须使用不同字段和不同 identity；前者不能
  代替后者的执行结果。

## 7. 预注册评价与否定条件

三种出场版本共享 T+3/T+5/T+10 以及受阻后的 5/10 session 观察窗口，报告：

- MFE、MAE，以及同一成本/执行约束下的结果覆盖率；
- 首次预警后的假警报：窗口内没有支撑失效或预定义可执行退出；
- 提前候选后的卖飞：退出后在固定窗口内重新收于 H 上方并创阶段新高，且退出前无支撑失效；
- 漏报：没有提前候选而后续发生支撑失效；
- `EXECUTION_UNCERTAIN`、NO_TRADE、停牌、limit-state、missing-open 的分层计数。

否定条件在 outcome 前固定：若价格结构相对简单基线没有稳定增量、量价 gate 只是缩小样本
且无跨期稳定性、或提前防守在成本/可执行性后不减少 MAE 而只增加卖飞，则对应假设记为
`REJECT` 或 `NEEDS_MORE_EVIDENCE`。不能因为结果不理想而添加指标、改窗口、改 H 距离、
改失败次数或切换为 robust-z。

## 8. 当前证据门槛与决定

本协议使用的证据状态如下：daily-K 外部只读字节身份为 `VERIFIED`，但 C worktree 本地
replay 路径仍为 `MISSING`；复权/字段语义主要为 `DECLARED_ONLY`；历史 T-known ST/*ST
为 `UNRESOLVED`；逐 bar known-at/vintage 为 `UNRESOLVED`；实际 T+1 fill、limit/tick 和
盘中序列为 `MISSING`；统一成本模型及合法来源尚未固定。因此本协议是完整的研究前草案，
独立前瞻捕获可以在单独审计后启用，但不是正式 outcome 研究授权。

Sol/用户仍需决定：是否采纳 `BALANCED_A` 主定义与 `CONSERVATIVE_B` 敏感性安排；是否接受
严格 PIT 缺口未解决时的任何 `EVIDENCE_LIMITED_HISTORICAL_EXPLORATION`；以及未来是否授权
C 专属 prospective capture。当前没有一项决定被本文件替用户做出。

## 9. 明确边界

本轮未读取 C future outcome、Final OOS 或受禁目录；未运行正式 C 回测；未下载、复制或覆盖
daily-K；未修改 Formal B、共享生产代码、runtime-state、正式产物或 B 调度。C 专属捕获
实现只写入 `data/research/c_prospective_capture_v1/`，失败和证据不足保留诊断而不伪造
`PROSPECTIVE_CAPTURED`。内部纯函数/合成测试和 exact-head CI 只验证实现/仓库状态，不等于
Sol 审计通过。

协议终态：`C_PROSPECTIVE_CAPTURE_PR_READY_FOR_SOL_ACTIVATION_AUDIT`。
