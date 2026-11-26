# C_FUNNEL_AND_BOTTOM_HIGHER_LOW_EARLY_START_V1 预注册协议

## 研究问题与边界

非阻塞 `research question`，STRICT PATH。量化现行 C 的真实前瞻漏斗与一年底部区覆盖，判断低位双底抬高早启动能否补齐 Formal B 的底部主升浪盲区，并同时满足可交易性、净收益与稳健性门槛。通过时只推荐提交独立前瞻观察提案供审批。

以 `origin/master` 的 `413ce2bcd8367b4b2207f0af58a2ed04ced4f920` 为基线。真实前瞻证据固定在 `origin/runtime-state` 的 `cce76bf0a205a57b4fbde0ce279e89f4a3c26267`，13 个真实日共 79,084 条完整双规则观测。所有重放使用本地冻结数据。样本标记 `DEVELOPMENT`、`MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE`、`NO_VINTAGE_PROOF`。禁止访问密封 Final OOS、continuous speed probe、行情 provider 和任何未列名研究输入。只读冻结策略与发布代码，保持线上采集、策略和 runtime-state 的写入边界。禁止收益后调参、扩张变体、合成加权评分以及 MACD、RSI、KDJ、布林带。

本协议单独提交在先。脚本固定该提交与 runtime commit，启动时比较 Git blob 与工作区协议的 LF 归一字节。随后核对冻结登记表及下表文件身份，再访问行情与事件。固定索引 769 个信号日为 2023-06-30 至 2026-08-28，预热可用冻结文件中更早的行，结果截断至 2026-08-28。

| 冻结路径（`data/validation/` 下） | SHA-256 |
| --- | --- |
| `core_signal_validation/raw/daily_k.parquet`（180,203,424 B） | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` |
| `core_signal_validation/raw/adjustment_factors.parquet`（295,284 B） | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` |
| `core_signal_validation/raw/index_000001_SH_2023.json` | `c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c` |
| `core_signal_validation/raw/index_000001_SH_2024.json` | `53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf` |
| `core_signal_validation/raw/index_000001_SH_2025.json` | `27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1` |
| `core_signal_validation/raw/index_000001_SH_2026.json` | `183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514` |
| `core_signal_validation_continuous_parts/core_signal_validation_manifest.json`（LF） | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` |
| `strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz` | `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9` |

## A. 现行 C 诊断

固定 Git 树中读取 `data/research/c_rule_funnel_capture_v1/{daily,near_miss}/*.json` 与 `data/research/c_simulation_v1/*.json`。以日期绑定 near-miss 路径、字节数及 SHA-256，逐日累加两规则 F0–F8 已知通过、确定淘汰、缺失，独立失败率分母为全部输入股票日及另列的条件已知股票日。汇总斜率/上涨比例联合计数、确切结构状态、全配对失败、峰龄/深度、反弹高点/幅度、冻结的三组股票直方图和三组配对直方图，另报告被选中配对子集及 near-miss 全量分类和采样计数。少于 15 日标 `COLLECTING_PRE_15D_CHECKPOINT_DIAGNOSTIC`。分开描述 F2 趋势、F4 深度与峰龄、F5 须在 L2 之后确认 R 的顺序损耗，独立和配对计数不归因为唯一因果效应。

持久化 C 模拟的初始 RR 用 `(target-trigger)/(trigger-stop)`，只以有效正风险计划为分母，分别计 `<2`、`<1` 和价位无效。仅在账本持有原始计划选择依据时归属压力分支。冻结重放可按 `pressure > close*1.03` 确切拆分压力和延伸目标。C0 及保守版结构复核使用现行 `build_entry_observation` 的价格结构命中语义，使用最后 260 根及与新规则共同的至少 250 根有效线、T 收盘高于 2 元、有效 pos250 资格。报告两规则位置分位数及 `pos250<=0.40` 股日比例。

## B. 固定四变体

每只代码以 `00` 或 `60` 开头的股票按时间预计算仿射（`s=1,b=0` 起步）。发生 `ex_date` 时按原顺序 `d=1+bonus+allotment`、`s/=d`、`b=(b-dividend+allotment_price*allotment)/d`。`norm=(raw-b_t)/s_t`，`p_T(t)=s_T*norm(t)+b_T`，仅包含 `t<ex_date<=T`。要求信号使用窗口的复权价为正，成交量不复权。执行前核验 500 个固定种子随机合成含现金分红、送转与配股的 `(symbol,T)`，逐价对比 `_adjusted_bars` 最大绝对误差 `<1e-11`。

T 为冻结交易日，至少 250 根有效股票日线且 `close_T>2`。250 根包含 T，`pos250=(close_T-llv250)/(hhv250-llv250)`，要求 `hhv250>llv250`、`pos250<=0.40`、`(hhv250-llv250)/hhv250>=0.25`、`close_T/close[T-20]-1<=0.20`。股票特征下标用个股有效日线，账户、固定窗口和波段计时用指数交易日日历。

在严格 `bars[:T]` 上使用冻结 `_pivot_indices(low, radius=2, low=True)` 语义确认低点，`L2<=T-3`。按 L2 降序、L1 降序取首个满足全部几何条件的配对。要求 `3<=T-L2<=10`、`8<=L2-L1<=45`、`low[L1]<=1.05*min(low[T-59:T+1])`、`0.005<=(low[L2]-low[L1])/low[L1]<=0.12`。颈线是 `max(high[L1+1:L2])`，并列取最早日。要求 `(H_neck-low[L1])/low[L1]` 在 `[0.04,0.25]`，`(H_neck-low[L2])/H_neck>=0.03`，`min(close[L1+1:T+1])>=low[L1]`、`min(low[L2+1:T+1])>=low[L2]`。所有价格在 T 锚，`L1<H_neck日期<L2<T`，`pivot_uses_t_bar=False`。

公共转强要求 `close_T>MA20_T`、`MA20_T>=0.995*MA20[T-5]`、`close_T>close[T-1]`、`close_T>open_T`、`CLV>=0.60`、`(close_T-low[L2])/low[L2]<=0.15`。一字价 CLV 按较前收上涨为 1，否则 0。MA20 窗口为 `[T-19,T]` 和 `[T-24,T-5]`。

| 变体 | 入场 |
| --- | --- |
| `C0_EXISTING_BALANCED_A` | 原版 `BALANCED_A` 命中，交易采用现行模拟定价 |
| `C1_BOTTOM_W_NECKLINE` | 公共资格、几何和转强，`close_T>H_neck` 且 `close[T-1]<=H_neck` |
| `C2_BOTTOM_HL_EARLY_RECLAIM5` | 同一公共条件，`close_T>max(close[T-5:T])` 且 `close[T-1]<=max(close[T-6:T-1])` |
| `C3_BOTTOM_HL_EARLY_VOL` | C2 加 `volume_T/median(volume[T-20:T])>=1.8`，中位数须为正 |

右脚缩量诊断使用 L2 前一日至 L2 两日均量除以 L2 之前 20 日成交量中位数，固定箱 `<0.8`、`[0.8,1.0)`、`[1.0,1.2)`、`>=1.2` 和缺失。

## C. 交易、覆盖与统计

C1–C3 触发价为原始 T 收盘四舍五入到分，止损为 T 锚右脚低点乘 0.98 后到分。`risk_pct=(trigger-stop)/trigger` 在 `[0.02,0.10]` 才形成计划。严格 T 前 60 根最高价距触发达 2R 则取该阻力（`PRESSURE`），否则取触发加 2.5R（`TREND_2_5R`），目标到分。C0 原价使用 `round(max(rebound_high, MA5),2)`、`round(support_floor*0.98,2)`、`pressure if pressure>close*1.03 else close+2.5*(close-stop)`。额外只修正 C0 目标，原目标低于 2R 时取触发加 2.5R 到分，覆盖价位顺序倒挂的原计划。其余相同，原 C0 无效计划单列。

`G0` 恒放行。`G2` 为沪指 `close>MA20` 且 `MA20_T>MA20[T-5]`。`G4` 为 G2 或 `close>MA5`、`MA5_T>MA5[T-3]` 且该变体当日有效定价宽度至少 5。`S_ALL` 接纳全部账户可用计划；`TOP2` 每日按 `(round(pos250,10),round(risk_pct,10),code)` 升序最多接纳 2。先处理当日已有挂单和仓位，再按当日收盘信号接纳。同股票持仓或未过期挂单排除。信号及平仓当日和随后 5 个市场交易日冷却；仅可在 T+1 至 T+10 触发，T+10 收盘后未成交记 `EXPIRED_UNTRIGGERED`。开放仓位右截尾，模糊仓位退出计入平仓冷却。

以逐日现行除权事件将触发、止损、目标及已有买入价同步变换；成交距原始日线同一坐标。主板 ST 状态未核验，一字涨跌停用约 10% 主板价格限制，将前一有效收盘换算到当日坐标后用半分容差判定。一字涨停跳过买入，一字跌停跳过卖出。触发成交 `max(trigger,open)`，买入当天无法卖出。可卖日先处理跳空（开盘越过止损或目标即按开盘价），开盘在两水平之间且同日触两价则 `AMBIGUOUS_SAME_BAR`。净收益为平仓价/当日基准买入价减 1 再减 0.002，总净损益为逐笔净收益百分点之和。净胜率按净收益严格大于零，净 PF 为净正收益和除以净负收益绝对值和（仅盈利无亏损记正无穷， JSON 单列标记）。

固定窗统计对每个组合的已接纳去重信号，不依赖触发状态，要求精确市场 T+1 至 T+5/10 每日有效行情。以 T+1 开盘为参考，在各日共同除权坐标上比较终点收盘及区间高低，给出均值、中位数、胜率、平均 MFE/MAE 和扣费前后口径。Bootstrap 按信号日先等权平均同日已实现的净回报，再以连续 20 个市场交易日做重叠移动块抽样，空日无收益观测，按有收益日重算均值。5000 次，NumPy 默认生成器种子 20261126，等尾 2.5% 和 97.5%。固定窗也给出对应区间。

波段审核同一主板样本，使用至少 120 根有效行情后的最多 250 根定义 pos250，T 锚计算相邻涨幅与位置。`t0>=2023-06-30`、原始收盘大于 2、`pos250<=0.40`、涨幅至少 3%、当日量至少为前 20 根均量的 1.8 倍，随后市场 20 日内最高价相对除权同基准 t0 收盘至少涨 30%。同股保留先出现的 t0，间距至少 30 市场交易日。完整窗要求 `t0-5` 在研究信号窗口内且 `t0+40` 不越截止日。及时早捕为市场日 `[t0-5,t0+10]` 同股有效信号且相同价格基准相对 t0 收盘涨幅不超 15%。B 无早捕但在 `[t0-5,t0+40]` 有信号为晚捕，其余为漏捕。Formal B 仅提取 `(symbol,signal_date,setup)`，核对 17,714 / 10,779 / 749，按同股同日对照。必须核对完整窗 2,137 与 B 晚捕加漏捕 2,080。任何不一致标 `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，报告实现的分子、分母和差额，不把探索结果充作既有盲区的证据，门槛 2 未经核验。

每变体给出 G0 原资格交集及各组合按账户接纳口径的覆盖与同股同日 B 重叠（分母为各组合接纳身份）。同时按信号日归属报告 `2024-02-06..2024-02-29` 与 `2024-09-18..2024-09-30` 的接纳、结案及累计净收益。TOP2 的「显著高于 C0」预先定义为同门、同比较 TOP2、同一 B 盲区波段内针对早捕/未早捕的配对单侧精确检验 `p<0.05`，且对应同门 S_ALL 满足 15%。

## D. 判定与停止

报告 `C_SCARCITY_AND_BOTTOM_BLINDSPOT_CAUSE`，保留未满 15 日状态。候选 C1–C3 × G0/G2/G4 × S_ALL/TOP2 同时满足：

1. MODEL_S 已结案至少 250 笔，模糊占触发 `<=5.0%`，B 同股同日重叠 `<15.0%`。
2. S_ALL 的 B 盲区早捕恢复 `>=15.0%`；TOP2 执行上述配对检验和 S_ALL 15% 条件。
3. 扣费后平均 `>=+1.00%`、PF `>=1.35`、胜率 `>=40.0%`，且三项均严格优于同环境同接纳模式 C0 原价。
4. 2023–2026 至少三年按信号年分组的净均值为正且超过同年 C0 原价。2023 与 2026 累计净损益 `>=-150.0 pp`。无结案的年份均值未定义，不能计作通过。
5. 日级等权净均值和 Bootstrap 95% 下界均大于零。

有组合通过时 `ADOPT`，仅 `RECOMMEND_C_V2_PROSPECTIVE_SHADOW_PROPOSAL`。按 G0/G2/G4、C1/C2/C3、TOP2/S_ALL 的字典序选唯一主推荐。门槛 1–4 通过、日均净收益为正而区间触零或跨零，判 `NEEDS_MORE_EVIDENCE`。所有候选的净均值均非正，或已核验的全部候选盲区恢复低于 5%，判 `REJECT`；仅覆盖达标而净期望不足时也判 `REJECT`。B 分母不复现且未触发独立的全候选净均值非正条件时判 `NEEDS_MORE_EVIDENCE`，说明所缺波段证据。其余未达到门槛的情况判 `DEFER`。不补变体或择优回调规则。

仅提交本协议、离线脚本及测试、汇总 JSON 和简体中文报告。须连续独立运行两次，汇总字节 SHA-256 完全一致，串行通过指定 pytest、compileall、diff 与生产路径检查。只推指定研究分支，不合并，不发起线上运行。
