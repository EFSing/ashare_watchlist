# 弱市恐慌超跌均值回归 V1 预注册协议

研究标识 `WEAK_REGIME_PANIC_MEAN_REVERSION_V1`，身份 `NEW_INDEPENDENT_RESEARCH_HYPOTHESIS`。本任务是非阻塞 `research question`，走 STRICT PATH。研究问题是，沪深主板 `NOT G2` 情形下的恐慌超跌回归，能否在冻结样本的 2023 年和 2026 年分别获得扣费正期望，并改善 B V2 的逆风净损益和全期收益回撤比。结果用于决定是否提交独立前瞻观察提案。生产日报和既有研究路径独立继续。

## 冻结输入与启动条件

基础提交 `2f8bd00627a7606bc783a14020609c83ef400791`。先单独提交本协议，再实现和回放。脚本将 `PROTOCOL_COMMIT` 固定为本协议提交，要求其位于当前 `HEAD` 的历史链上，使用 `git show <PROTOCOL_COMMIT>:docs/research/weak_regime_panic_reversion_v1_protocol.md` 读取提交字节并与工作区比较。仅将 CRLF 归一为 LF。失败即停止，先验锁和输入校验成功后才解码数据。

所有输入均为工作区内精确白名单路径，拒绝通过链接解析到其他路径或访问密封数据。仅以 `data/governance/frozen_artifacts.json` 核对下表条目的 `file_sha256`，并核对表中固定字节数与 SHA-256。连续清单的长度和哈希按 LF 归一，其他文件按原始字节。清单仅校验字节身份。

| 路径（根目录为 `data/validation/`） | 字节数 | SHA-256 |
| --- | ---: | --- |
| `core_signal_validation/raw/daily_k.parquet` | 180203424 | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` |
| `core_signal_validation/raw/adjustment_factors.parquet` | 295284 | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` |
| `core_signal_validation/raw/index_000001_SH_2023.json` | 40966 | `c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c` |
| `core_signal_validation/raw/index_000001_SH_2024.json` | 40983 | `53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf` |
| `core_signal_validation/raw/index_000001_SH_2025.json` | 41175 | `27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1` |
| `core_signal_validation/raw/index_000001_SH_2026.json` | 27109 | `183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514` |
| `core_signal_validation_continuous_parts/core_signal_validation_manifest.json` | 523376 | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` |
| `strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz` | 2506292 | `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9` |

样本 `DEVELOPMENT`、`MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE`、`NO_VINTAGE_PROOF`。信号日为 2023-06-30 至 2026-08-28 两端含的 769 个 XSHG 交易日，逐日与本地 XSHG 日历核对。冻结窗口内有效个股日线按最近实际交易 bar 回看，指数可用同一冻结文件内更早的历史预热。缺 bar 视为无可用观测，成交额和成交量保留原始人民币元和原始股数。2023 与 2026 均为部分年份。

对每只股票，按事件日累计作用于旧价格的仿射系数，令 `norm_p[t] = (raw_p[t] - offset[t]) / scale[t]`，`p_T(t) = scale[T] * norm_p[t] + offset[T]`。事件变换为 `(p - dividend + allotment_price*allotment)/(1+bonus+allotment)`，仅使用 `t < ex_date <= T`。所有指标使用窗口内所需的正价。按 `(symbol, ex_date)` 排序选有 250 根历史、窗口确实跨越除权日且能在截止前取得除权日或其后首个 bar 的事件，等距取 500 个，以该 bar 为锚对照 `core_signal_replay._adjusted_bars`，核对最近 250 根 OHLC 的最大绝对误差 `<1e-11`。

## 固定信号与矩阵

`G2_T`: 指数收盘 `> MA20_T` 且 `MA20_T > MA20_{T-5}`，均含各自锚点。`P0_ALL_NON_G2` 在 `NOT G2` 放行。`P1_MARKET_PANIC_PULSE` 同时要求至少一项满足：主板有效 `ret1 <= -4%` 的比例 `>=12%`、上证 `ret1 <= -1.2%`、主板有效 `bias20 <= -8%` 的比例 `>=20%`。广度分母为当日有 bar、累计至少 250 根、近 20 根复权收盘可用的沪深主板 `00xxxx.sz/60xxxx.sh`，不施加个股流动性或形态门槛。

公共资格为同一主板范围和历史要求，原始收盘 `>3`，含 T 的 20 根成交额中位数 `>=50,000,000`，`ret1 > -9.2%`，`bias20 <= -8%`，`ret5 <= -6%`。`retN = p_T(close_T)/p_T(close_{T-N})-1`。一年位置为 `(close_T - min(low250))/(max(high250)-min(low250))`，平窗取 `0.5`。`CLV = (raw_close - raw_low)/(raw_high - raw_low)`，零振幅时 CLV 缺失。变体仅有下列三个。

| 变体 | 在公共资格上追加 |
| --- | --- |
| `M1_PURE_EXTREME_STRETCH` | `bias20 <= -10%` 且 `ret5 <= -8%` |
| `M2_PANIC_HAMMER_REJECTION` | `(raw_high_T-raw_low_T)/p_T(close_{T-1}) >= 4%`，`CLV >= 0.55`，`volume_T >= 1.2 * median(prior20_volume)`，基准中位量 `>0` |
| `M3_LOW_POS_EXHAUSTION` | `pos250 <= 0.50`，`ret60 <= 15%`，`ret1 > p_T(close_{T-1})/p_T(close_{T-2})-1`，`CLV >= 0.45`，`volume_T <= 1.2 * median(prior20_volume)` |

`TOP2` 按 `(round(bias20,10), round(pos250,10), code)` 升序，先排除持仓与冷却代码，最多接受 2 只，接受的隔夜订单和持仓合计占用不超过 6 个名额。次日开盘订单失败后释放名额，当天收盘可再次入选。结案日 E 同股及随后 3 个交易日 E+1 至 E+3 均不入选。`S_ALL` 沿用同股去重及冷却，取消日选和并发上限。两档市场门、三档入场、两档退出、两档账户共 24 组，`TOP2` 的 12 组参与决策。

## 执行与损益

只在信号后的首个 XSHG 日开盘买入，缺 bar 或一字涨停记 `UNBUYABLE_SKIP`，一字跌停按开盘强制买入。截止日生成的订单记 `ENTRY_AFTER_CUTOFF`。一字条件为 `high == low`，涨停 `open >= prev_close*1.10-0.005`，跌停 `open <= prev_close*0.90+0.005`，`prev_close` 为上一有效 bar 收盘在当前日的因果除权价。只在买入后下一 XSHG 日及以后卖出。跨除权用同一仿射坐标换算原订单价位、比较参考价与收益分母，价位按进入该订单时的原始固定价转换。

`X1_TARGET_45_STOP_50_HOLD4` 固定目标 `entry*1.045` 与止损 `entry*0.950`。可卖日先看开盘，越过止损或目标按开盘成交。开盘在区间内时，单边触及按该价成交，双触及记 `AMBIGUOUS_SAME_BAR`，在账户于当日终结。该类从主统计剔除，在 `pessimistic_net_avg_pct` 和权益曲线中全部按止损结算。买入后第 4 个 XSHG 日未触发则按收盘强制平仓。

`X2_MA5_CLOSE_RECLAIM_NEXT_OPEN_HOLD5` 在买入日及以后每日有效收盘检查 `close >= MA5`，成立后于下一可卖交易日开盘兑现。买入后第 5 个 XSHG 日无条件开盘离场。其余可卖日按 `entry*0.940` 保护，开盘穿越时按开盘，盘中触及时按保护价。开盘兑现与跳空止损价重合时成交价均为开盘。

任何已到期或已触发但遇停牌或一字跌停的卖单维持待执行，于后续首个有 bar 且未一字跌停日的开盘卖出。未到期的缺 bar 仅等待后续观察。一字跌停内达到保护价即登记待执行。截止日仍未卖出记 `OPEN_AT_CUTOFF`。每笔结案扣双边合计 0.20 个百分点。净收益分组用信号年。已触发为完成入场的笔数，含尚未结案和模糊单。获利因子为正净收益之和除以负净收益绝对值之和，只有正收益时为正无穷，无盈亏时为空。

## B V2 与组合面板

读取冻结 B 正式资格事件的信号日和代码，以同一沪深主板和日历回放独立比较面板。只用信号当日及此前的原始行情重建正式 B 静态触发、止损、目标价，以及既有 `b_structure_volume_observation` 与 `preview_b_shortlist._position_metrics` 的 V2 输入。沿用 `G2 + L1`，接受回踩前段或转强阶段、有效 V1/V2 与参考价，按 V2 的 12 位小数规则检验 `pos250 <=55%`、`chg20 <=20%`、`chg60 <=30%`，并按 `(pos250,V1,code)` 取最多 3 只。面板将入选当作模拟挂单，同股持仓和冷却排除，沿用 `MODEL_S` 的 10 个 XSHG 日挂单期限及入选后与退出后 5 日冷却。有效 bar 当日开盘达到触发价则按开盘买入，否则盘中触及按触发价。不可买日跳过该日。采用 `E0` 静态目标止损，开盘优先，双触及权益按止损处理。T+10 收盘强制结案，若同日才买入或无法卖出，随后首个合法可卖日开盘结案。B 面板采用与弱市腿相同的成本和除权口径。报告标记为冻结资格的独立回放面板。

每笔使用同一固定名义单位，逐市场日将已实现净盈亏与未平仓按最近可用收盘盯市的变动相加。未平仓估值扣预留双边成本。权益从零起算，年累计按损益发生日分配，最大回撤为权益曲线相对历史峰值最大跌幅，单位均为 pp。组合曲线为独立 B 与弱市 `TOP2` 两腿的逐日相加，允许 G2 与 NOT G2 信号后的持仓重叠。组合面板用名义损益度量，风险量化与实际共享资金容量分属不同问题。

## 决策、显著性与停止条件

1. `TOP2` 全期主统计至少 120 笔结案，2023 与 2026 合计至少 60 笔，模糊单占已触发笔数 `<=5%`。
2. 2023 和 2026 主统计单笔净均值均 `>0`，各年悲观净均值均 `>0`，两年合并净获利因子 `>=1.20`。
3. 全期净均值 `>=0.50%`、胜率 `>=52.0%`、净获利因子 `>=1.25`。
4. 与 B 比，组合 2023 加 2026 累计净损益改善 `>0` 且差值的双侧 95% 移动块 Bootstrap 区间下界 `>0`，全期收益/最大回撤比严格高于 B。对两个年份内的逐日组合减 B 损益独立按年重采样，再求和。沿用第 5 条的块长、重复数和种子。
5. 每个信号日的有效已结案净收益取日内均值，无有效结案的交易日填零。对完整 769 个交易日序列做非循环重叠移动块 Bootstrap，20 个交易日一块，均匀有放回抽起点，拼接后裁至原长。每项检验用独立重置的 `NumPy default_rng(20261127)` 抽 5000 次，2.5% 和 97.5% 线性分位数。实际日均值及 95% CI 下界均 `>0`。

全部通过为 `ADOPT`，语义 `RECOMMEND_WEAK_REGIME_PROSPECTIVE_SHADOW`。多组通过时按 `P1 > P0`、`X2 > X1`、`M1 > M2 > M3` 取一组。若无通过，且任一组过 1–4、日均值为正而 95% CI 含零，为 `NEEDS_MORE_EVIDENCE`，所缺证据是能提高日级净均值精度的独立前瞻样本，供未来提案判断。其余已完成但未达到门槛的情况为 `REJECT`，尤其任何组均未在两年分别取得扣费正均值时直接拒绝。输入身份或独立 B 基准不可验证即中止回放并标记证据缺口。矩阵、门槛和优先级在协议提交后固定。

只交付本协议、独立脚本、专项测试、汇总 JSON 与中文报告。验证两次独立回放汇总 SHA-256 一致、专项测试和编译通过、差异仅为五个约定文件。提交并推送研究分支后结束，前瞻观察提案需另行决策。
