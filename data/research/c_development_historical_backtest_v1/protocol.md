# C_DEVELOPMENT_HISTORICAL_BACKTEST_V1 — outcome 前协议锁定

状态：`LOCKED_BEFORE_OUTCOME_ACCESS`  
锁定日期：2026-09-24（Asia/Shanghai）  
研究分类：`research question + correctness/provenance gate`；不是 Formal B 或产品晋级任务。

## 1. 研究问题、重要性、输入与停止条件

**研究问题：** 在新版 C 已冻结的 `C_QFQ_INPUT_V1` 输入身份和既有规则不变的前提下，逐交易日重放 `BALANCED_A`、`CONSERVATIVE_B`，分别报告信号后的 T+3、T+5、T+10 观察表现、T+1 参考执行表现、执行覆盖以及成交量描述统计，并判断现有历史证据允许何种结论。

**重要性：** 该结果只用于决定新版 C development research 是否有可审计的历史证据继续交由 Sol 检查。已授权的研究不触发 Formal B 变化、规则晋级、生产名单、正式交易或 Final OOS 读取。

**冻结代码/规则输入：**

- 锁定前工作树提交：`20216bfd9a154ce638e2b9306817a727be732110`（本轮独立分支起点，来自开放的 C 工作流 Draft PR #86）。
- `scripts/c_pre_outcome_design.py` blob：`e1307755819b6f542e56b517bc6a01eb37d05301`。
- `scripts/c_b_input_adapter.py` blob：`bbdacb40f2c873f93b0aaab65d27cf82a99c2ef2`。
- 规则定义和字段语义：`docs/research/c_pre_outcome_design_v1.md` 与 `docs/research/c_pre_outcome_preregistration_protocol_v1.md`；本研究不修改两文件、不更改规则参数。
- 输入身份：仅接受能以来源记录和字段语义支持 `C_QFQ_INPUT_V1` 的既有冻结输入。用户提供的旧 B 数据候选 SHA-256 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` 是待实测核对的身份线索，不代表其自动属于 `C_QFQ_INPUT_V1`。

**数据输入边界：** 只检查现存 frozen daily-K、registry、manifest 和来源记录；不发起新的全市场 HiThink 请求，不改写或重建原始数据，不使用 B 最终选股名单作为 C 事件样本，不使用当前名称回填历史 ST。任何不匹配的输入必须保留其真实身份，并与新版 C 输入隔离。

**模式选择固定如下：**

1. 仅当价格/量能字段身份、每个 T 可知的 ST 状态、逐 bar 可见时间、调整口径和执行证据均满足既定要求，才标为 `PIT_HISTORICAL_RESEARCH`。
2. 若真实文件身份与字节 SHA 可核验，但上述一个或多个历史时点证据缺失，则仅在其余可计算样本、排除范围和限制可以逐项记录时，采用用户已授权的 `EVIDENCE_LIMITED_HISTORICAL_EXPLORATION`。结果不得称严格 PIT 胜率、真实成交胜率或可执行收益。
3. 若必需的 C 输入文件不存在、SHA 不符、来源身份无法确认，或价格无法合法支持 T 日信号，则停止收益计算并报告 `C_HISTORICAL_BACKTEST_BLOCKED_BY_VERIFIED_DATA_GAP`。不构造替代序列、合成收益或伪胜率。

**停止条件：** 模式分类和输入边界达到以上任一确定终点；或在任何收益读取前发现输入身份/完整性失败。任何协议更改都必须发生在结果解盲之前；一旦读取 outcome，不得用同一数据修改规则或评价协议后声称独立验证。

## 2. 冻结评价设计

- 规则只为 `BALANCED_A` 与 `CONSERVATIVE_B` 两套；两者独立重放，复用现存纯函数，保留 `rule_id`。不增加第三套规则、过滤器、趋势条件、量能 gate 或参数搜索。
- 规则 membership 必须只由截至 T 的合法输入前缀形成。信号在 T 收盘后形成；最早参考入场是下一个 XSHG session 的 T+1 open。T 收盘价只用于观察收益，绝不作为信号后已成交价格。
- 评价窗口固定为 T+3、T+5、T+10 个 XSHG sessions。对每个信号/窗口分别计算：
  - `OBSERVATION_RETURN` = `close[T+k] / close[T] - 1`；
  - `T_PLUS_ONE_REFERENCE_RETURN` = `close[T+k] / open[T+1] - 1`，仅是开盘参考价情景，不声明成交；
  - `COST_AFTER_RETURN` = `NOT_CALCULABLE_COST_MODEL_NOT_PREEXISTING`，除非发现本任务前已合法固定、可引用且适用于该时期/输入的统一模型。不得按观察结果挑选费率、滑点或涨跌停处理；
  - `MFE/MAE_REFERENCE` = T+1 至 T+k 的 high/low 相对 T+1 open；只对可计算的窗口报告，作为价格路径观察，不声称可成交。
- 每个胜率都必须标记分子/分母。正收益观察比例的分母为对应规则、窗口中有效 `OBSERVATION_RETURN` 数；参考收益正比例分母为有效 `T_PLUS_ONE_REFERENCE_RETURN` 数。实际成交胜率在没有成交证据时为 `NOT_AVAILABLE`，不把参考价收益冒充真实交易胜率。
- 缺失价格、停牌/NO_TRADE、涨跌停、缺 T+1 open、窗口不足和执行不确定各自计数。参考收益只在所需价格有效时计算；异常状态不能默认为正常成交。
- 输出 `FULL_COMPARABLE_UNIVERSE` 的日期/证券/排除覆盖，以及每套规则各自的 `MATCHED_EVENT_SAMPLE`。不能将未匹配样本差异解释为规则因果优势。
- 每个事件保留 signal date、symbol、rule_id、价格结构事件 identity、episode identity、原始输入/特征 SHA；同一 symbol/episode 的连续观察不得作为多个独立事件夸大样本。记录年度/主要市场阶段、个股集中度和去重前后数量。
- 不计算未在原预注册中精确定义的简单趋势基线。本轮只报告两个已指定 C 规则；不以 B 的 51.6403% 作为 C 门槛。

## 3. Universe、价格与量能解释

- 目标范围是沪深 00/60 普通主板且 T 日非 ST/*ST。历史 ST 状态只有在来源和 known-at 可证明时才能作为正式资格。若缺失，不以当前名称回填；受限探索必须明确把未核实 ST 的 00/60 证券作为单独的 `ST_STATUS_UNVERIFIED` 候选覆盖，不能把它们标成满足 C universe 的有效 PIT 信号。
- `C_QFQ_INPUT_V1` 的前复权价格不得仅因序列完整而视为 T 时可知。检查调整因子/公司行为及其时间证据；无合法 T-anchor 或逐日 vintage 证明时，只能在证据允许范围内标 `PARTIAL_UNVERIFIED`，不得宣称 PIT replay。
- 量能计算字段固定为：`RV_T`、回踩量相对既定基准量、回踩前/后半程量能、上涨日/下跌日量及方向性比值。其结果仅描述冻结字段值。除非 volume basis 另有合法的来源/调整语义证明，统一标记 `VOLUME_BASIS_UNVERIFIED`；无论结果如何都不设 gate、不改变样本、不影响 C 信号。
- 旧 B frozen daily-K 与 `C_QFQ_INPUT_V1` 是不同的待核验身份。若仅旧 B 输入可用，其上的价格事件不能被报告成新版 C_QFQ outcome；只有在明确标注为不同输入的诊断对照且不被误读为 C 结果时才可展示，否则停止。

## 4. 结果判读与限制

分别呈现两个规则的信号数、各窗口有效数、正收益率、均值、中位数、成本边界、MFE/MAE、执行失败/不确定数、按年和主要市场阶段样本、重复 episode 程度。样本不足时标 `INSUFFICIENT_DATA`，不输出确定性判断。未预注册简单显著性门槛；不作因果归因、不自动晋级、不修改冻结规则。

量能收益结论、严格 PIT 胜率、真实 fill 成交率及成本后收益，只有对应数据证据齐备时才可提出。缺失项需写明由哪个后续审计或产品决策使用，以及在该证据缺失时仍可继续的路径。

输出仅放在 `data/research/c_development_historical_backtest_v1/`。不修改 Formal B、生产/日常名单、checkpoint、delivery receipt、runtime-state、原始数据、sealed Final OOS 或其他项目的正式产物。
