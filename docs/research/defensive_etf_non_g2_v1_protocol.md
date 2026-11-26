# G2 轮空期场内防守 ETF 独立预注册协议

研究标识 `DEFENSIVE_ETF_NON_G2_V1`。非阻塞 `research question`，走 `STRICT PATH`。研究问题是，三种场内防守配置在 B V2 无新开仓的市场阶段，能否在 2023、2026 两个弱市切片各自获得扣费正收益，并相对六槽位现金基准改善组合收益及回撤。只有四门全过才支持独立日报观察卡提案。A 股期权为 `OUT OF PRODUCT SCOPE`。前序 `WEAK_REGIME_PANIC_MEAN_REVERSION_V1` 已由用户确认为 `REJECT`，归档身份 `fe42bc6abea36aa70a63dc11513fde3f57dfc4db`。

## 输入身份和停止条件

基线 `origin/master@2f8bd00627a7606bc783a14020609c83ef400791`。单一工作树，研究分支 `codex/defensive-etf-non-g2-v1`。本协议、采集脚本、原始文件及输入清单先单独提交。回放脚本固定 `PROTOCOL_COMMIT`，以 `git merge-base --is-ancestor` 验证祖先，以 `git show <PROTOCOL_COMMIT>:docs/research/defensive_etf_non_g2_v1_protocol.md` 验证工作区协议字节。只允许精确白名单普通文件及原路径，拒绝重定向、路径穿越和额外输入。先验证全部文件大小及 SHA-256，再解码行情。两个既有清单和协议文档按 Git 的 LF 文本字节验证，其他文件用原字节。

ETF 限 `511260.SH`、`518880.SH`、`512890.SH`，采集 `2022-06-01` 至 `2026-08-28`，含两端。腾讯请求自然年未复权 `day` 序列，HiThink 获取每十份税前现金分红与 `fyear` 的单位、复权净值。仅保留范围内日期和所需字段，禁止用回查的前复权价充当历史信号锚点。原始日线须覆盖连续 769 个评估交易日，并有至少 250 个有效预热日。B 使用冻结开发样本资格和行情，`DEVELOPMENT / MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE / NO_VINTAGE_PROOF`。固化文件身份后，个股行情和除权事件均在 Parquet 过滤阶段限定日期不晚于截止。禁止读取密封 Final OOS 行情和分红数据。

### 第 1 门的净值核验

用户在任何收益回放前授权明确使用净值总增长因子。每对相邻净值观察日的非除息日检验 `(unit_nav_t / unit_nav_{t-1}) / (adj_nav_t / adj_nav_{t-1})` 在 `1.0 ± 0.005` 内。净值覆盖所有窗口内 XSHG 时段，亦检查供应商在窗口内发布的额外非交易日净值。除息日检验 `((unit_nav_t + dividend_per_share) / unit_nav_{t-1}) / (adj_nav_t / adj_nav_{t-1})` 在同一容差内，且除息日在交易日历和净值记录中都有对应日。原净涨跌幅之比仅留作输入诊断。净值只用于跨源检查。识别出未建模折算、必需输入缺失或身份不符即中止，标记 `INSUFFICIENT_DATA` 或 `PARTIAL_UNVERIFIED`。

`dividend_per_share = per_ten_cash_before_tax / 10`。国债 ETF 四笔除息和金额均与场内公告核对。场内派息依次为 `2025-09-26`、`2025-12-31`、`2026-03-30`、`2026-06-30`，对应除息日 `2025-09-23`、`2025-12-26`、`2026-03-25`、`2026-06-25`。原始文件保留供应商 `payment_date` 作为来源记录，到账日采用公告的场内日期。除息日持仓认列应收红利，场内发放日才转为可用现金。用未复权价格标记实际份额价值并加上应收或到账红利，在货币损益上等价于用当前锚的仿射价比较旧日和当日价格，每笔税前红利只入账一次。对应公告 [2025 年 9 月](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-09-18/511260_20250918_HDYX.pdf)、[2025 年 12 月](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2025-12-23/511260_20251223_ZED8.pdf)、[2026 年 3 月](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-03-20/511260_20260320_QYES.pdf)、[2026 年 6 月](https://www.sse.com.cn/disclosure/fund/announcement/c/new/2026-06-22/511260_20260622_BWI3.pdf)。

### 精确输入白名单

| 路径 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `data/validation/defensive_etf_non_g2_v1/raw/511260_SH_dividends.json` | 529 | `a0e8d14b85da75a7ec6cbfc3503e246d967d21dfd068f903627323bea028a44a` |
| `data/validation/defensive_etf_non_g2_v1/raw/511260_SH_nav.json` | 64084 | `d0b1e2909f5635193be7c4d14b063d99ea17490235320e853a77df4a0d16c10a` |
| `data/validation/defensive_etf_non_g2_v1/raw/511260_SH_ohlcv.json` | 101469 | `b265404bbd180014887b0d698e8622bda8e56147ede087b5d736d9501dcaf4a6` |
| `data/validation/defensive_etf_non_g2_v1/raw/512890_SH_dividends.json` | 32 | `caf9070bf9a78f7f6df43c2da9610d26c531b39f270e90633a8407e5a21bfc40` |
| `data/validation/defensive_etf_non_g2_v1/raw/512890_SH_nav.json` | 62954 | `1dfc5c4377a07da9fb5fead5488f5cef0942557648a659cdf233ca6b4ccca764` |
| `data/validation/defensive_etf_non_g2_v1/raw/512890_SH_ohlcv.json` | 95196 | `7abb7b1ffec5cc917b8d57efcfd22abf881714264eece20b3096571163c9e632` |
| `data/validation/defensive_etf_non_g2_v1/raw/518880_SH_dividends.json` | 32 | `5c3124db4ca1481c96a58f06614edd886083d48ff770f1a3edd257d1d8bbd807` |
| `data/validation/defensive_etf_non_g2_v1/raw/518880_SH_nav.json` | 63109 | `f5c09e034c530bd5d2c49e27e640e49bac7a80376449c22eaeaabf5a2ff78f47` |
| `data/validation/defensive_etf_non_g2_v1/raw/518880_SH_ohlcv.json` | 95497 | `5d5581fabcc475ab6e37596ad317f1054f3ec81d50c6e20340dbd6ee0ae11ef2` |
| `data/validation/defensive_etf_non_g2_v1/raw/input_manifest.json` | 2241 | `b865401b78c9d0fb0007bcf4fbb8a0a78bb75b14e06297811e2b4c5536368960` |
| `data/governance/frozen_artifacts.json` | 43028 | `8a1d456ee2098808940b591157be875fb53080c97119d0bc33221745148dd38e` |
| `data/validation/core_signal_validation/raw/daily_k.parquet` | 180203424 | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` |
| `data/validation/core_signal_validation/raw/adjustment_factors.parquet` | 295284 | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` |
| `data/validation/core_signal_validation/raw/index_000001_SH_2023.json` | 40966 | `c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c` |
| `data/validation/core_signal_validation/raw/index_000001_SH_2024.json` | 40983 | `53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf` |
| `data/validation/core_signal_validation/raw/index_000001_SH_2025.json` | 41175 | `27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1` |
| `data/validation/core_signal_validation/raw/index_000001_SH_2026.json` | 27109 | `183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514` |
| `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json` | 523376 | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` |
| `data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz` | 2506292 | `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9` |

## 固定信号与执行

评估日期 `2023-06-30` 至 `2026-08-28`。开窗初始权益 1 且全现金，前序指数信号仅用于三日确认。`G2_T` 为上证收盘严格高于含 T 的 MA20，且 MA20 严格高于五个 XSHG 交易日前的 MA20。`R0_IMMEDIATE_NON_G2` 当日非 G2 即激活。`R1_CONFIRM3_NON_G2` 首次进入需含 T 连续三日非 G2。任一模式在 `G2_T` 恢复时，于次日开盘先无条件清空 ETF。

任意日的旧价按 `p_A(t) = raw_p[t] - sum(dividend_per_share where t < ex_date <= A)` 转换。每个收盘用当日锚点，合格需含 T 的 20 根转换收盘全部正且末值严格高于均值。`A1_MACRO_SHIELD_CAPPED` 为合格国债和黄金各 50%，余为现金。`A2_TRIPLE_INV_VOL20` 在三个合格标的中按 20 个同锚点收盘收益的样本标准差倒数归一，用 21 根收盘，国债以外两只各封顶 50%，剩余留现金。合格资产缺有效正波动率即中止。`A3_PURE_BOND_PARK` 在国债合格时配置 100% 国债，否则持有现金。无合格标的均持现金。

首次激活和持续期间每周最后一个 XSHG 收盘生成目标，次日开盘按差额交易。以 T 收盘的实际 ETF 权重及目标权重计算绝对变化之和，ETF 腿差额严格小于 10% 且无持有标的失去顺势资格时跳过。目标差额按开盘成交，先卖后买。用开盘可用预算计算目标头寸，买方按比例缩减以留足实际成交费。金额允许零碎份额，按实际 ETF 买卖名义金额分别扣 2.5 或 5 bps。现金收益 0。买入后的首个可卖日为下一交易日。截止日收盘按可用价格计值，无次日交易和强制期末变现。

## B V2 与资金归属

B 沿用冻结沪深主板正式资格。信号日用 `G2 + L1`，一年位置 `<=55%`、20 日涨幅 `<=20%`、60 日涨幅 `<=30%`，用前序研究的 12 位小数比较，接受 `EARLY_PULLBACK` 或 `W2_TO_W3_TRANSITION_PROXY` 且 V1/V2 有效、参考价合法的事件，按 `(pos250, V1, code)` 取每天至多 3 只。挂单、持仓同股排斥，信号入选及结案后一律冷却至 E+5（含该日）。订单 T+1 起最多有效十个 XSHG 交易日，优先开盘触价，其次盘中触价，跳过无行情及一字涨停。B 使用前序 `E0` 定义，开盘优先、盘中双触及按止损、T+10 收盘退出，遇同日买入或无法卖出延到首个合法可卖日开盘。股价和订单在当时已知的因果仿射坐标下转换。沿用前序 B 每笔固定入场名义本金 20 bps 双边费用，已持仓估值预留费用。

`ACCOUNT_6SLOT` 基准与组合均用同一 B 容量和市场门。B 持仓与尚有效挂单合计最多占 6 槽。前收盘是非 G2 的交易日，B 不成交新仓，旧挂单继续计龄并占槽，G2 恢复后未过期者可成交。B 每个新仓目标为开盘账户权益的 1/6，先计入开盘已实现卖出，再用当时的可交易现金保障该笔和当日其他有效挂单的等额预算。现金不足只按各有效挂单的均分额度成交。盘中、收盘才退出的 B 不作为当天开盘资金。基准闲置现金不计收益。

组合建仓或周调仓时用 T 收盘的 `free_ratio=(6-active_B_positions)/6` 乘以防守目标 ETF 权重，于下一个开盘使用至多 `free_ratio × 开盘权益` 的预算，实际至多使用可交易现金及 ETF 变现净额，应收红利不上杠杆。非 G2 隔夜 B 无权使用暂入防守袖套的现金。G2 信号后的开盘先清出全部 ETF，现金到账后才允许 B 开盘或盘中触价。组合与基准的 B 事件完全共用，成立条件为每次 B 成交都有正的自有资金，且同时占用不超过 6 槽。独立袖套无 B，使用同样的 ETF 执行与费用。桥接列 `B_V2_UNCONSTRAINED + 6_UNITS_DEFENSIVE` 沿用前序无槽位上限、挂单可跨市场门成交的固定名义 B，逐日名义损益加独立袖套权益增量的六倍。仅作参考。

## 判定和停止

逐日收益为开窗单位本金的收盘权益路径环比。年度与全期均按区间内逐日收益复利，回撤为相对前高的百分比，含开窗本金。弱年组合增量为 2023 与 2026 各自相对基准的复利累计收益差之和。两组成本均报告。仅主成本用于门槛中未单独规定成本的全期收益、回撤、收益回撤比和显著性。

1. 三只 ETF 与全部冻结基准通过身份、覆盖、日期及净值检查，跨期运行与资金校验通过。
2. 2023 和 2026 两年的独立袖套净收益在 5 和 10 bps 下各自严格大于零，主成本最大回撤不超过 6.0%。
3. 主成本袖套全期净收益大于零，四个年份至少三个净收益不低于零，769 日实际日均收益为正且双侧 95% Bootstrap 区间下界为正。对完整日序列按非循环、重叠 20 日块抽样，有放回拼接并裁至原长。每项统计独立初始化 `NumPy default_rng(20261128)`，5,000 次，2.5% 和 97.5% 用线性分位数。
4. 两档成本相对基准的弱年累计收益增量均严格为正。主成本下按年分层配对 Bootstrap，2023、2026 分别以相同块起点抽组合和基准，分别复利后求年度差，再相加。块长、次数和种子沿用第 3 门，下界严格为正。主成本全期组合收益/最大回撤比严格高于基准，组合回撤不超过基准的 1.05 倍。

四门全过为 `ADOPT`，含义 `RECOMMEND_DEFENSIVE_ETF_DAILY_REPORT_CARD_PROPOSAL`，通过组依 `R1 > R0`、`A1 > A3 > A2` 唯一选定。没有全过，且候选其余条件全过、袖套实际日均为正、仅第 3 或第 4 门区间含零，判为 `NEEDS_MORE_EVIDENCE`。其余完成评估后判为 `REJECT`。未通过数据和因果校验时停止评估，不计算候选收益。两次独立回放汇总字节相同、专项测试及编译和差异检查通过后，提交并推送独立研究分支。生产日报观察卡需要单独决策。
