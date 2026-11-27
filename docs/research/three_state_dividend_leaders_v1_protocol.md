# 三态市场温度计与高股息大盘龙头卫星预注册协议

`THREE_STATE_REGIME_AND_DIVIDEND_LEADERS_V1` 是非阻塞 research question，走 STRICT PATH。独立回答两个问题。第一，主板宽度能否改善现行 B V2 与 R1/A1 六槽账户。第二，结构分化期两槽红利卫星能否在扣费后超过同宽度下直接持有债金的机会成本。两项决定分别用于判断是否有足够发展样本证据支持未来独立观察提案。现行日报可继续使用既有规则。

## 输入身份与停止条件

基线 `origin/master@b6c937d5518e6b08014f7bf19a6ee588fbda0949`。单一工作树，分支 `codex/three-state-dividend-leaders-v1`。先单独提交本协议及六件 ETF 原始文件，再实现和回放。运行时验证该提交为 HEAD 的祖先，并按 Git LF 字节核对协议与冻结表。全部文件身份先通过，才解码行情。带 `LF` 的工作区文件仅将 CRLF 转为 LF；标记 Git 的输入使用指定提交的原始 blob，不依赖其他分支的工作区，可离线读取。

取 `2023-06-30` 至 `2026-08-28`（含两端）的 769 个 XSHG 交易日，2023 与 2026 为部分年份。预热只使用冻结文件中较早的观察。个股日线与除权事件在 Parquet 读取层分别以 `date_ms <= cutoff_ms`、`ex_date_ms <= cutoff_ms` 硬过滤，使用上海时间的当日零点时间戳，分红事件读取自 2016-01-01 起。本研究不访问密封 Final OOS、市场数据 API 或其他数据源。样本沿用 `DEVELOPMENT / MAIN_BOARD_ST_UNVERIFIED_DEVELOPMENT_SAMPLE / NO_VINTAGE_PROOF`，无法单独验证历史 ST 与当日供应商快照，成交额门是大盘流动性代理。

以下两处 Git 身份为 `DEFENSIVE_ETF_NON_G2_V1` 的 ETF 输入锁 `1d1f0177e6e588bfb0c3fa4371e248cbfbb168c4` 与验证归档 `8a7a528dd2df89bdeab9cf18304da5835143364d`。原文件目录为 `data/validation/defensive_etf_non_g2_v1/raw/`。六个目标文件逐字节与输入锁及原预注册 SHA-256 相同。归档回放模块及校验模块只复用离线函数。归档汇总只用于校验 Stage 0 两档 769 点日收益、年度指标及账本审计；逐点使用浮点精确等值。Stage 0 确认以后才进行候选收益评估。输入、覆盖、因果、基线或资金约束校验失败即停止，用 `INSUFFICIENT_DATA` 或 `PARTIAL_UNVERIFIED` 记录，未完成的决策为 `NEEDS_MORE_EVIDENCE`。

| 输入路径 | 字节数 | SHA-256 | 来源 |
| --- | ---: | --- | --- |
| `data/governance/frozen_artifacts.json` | 43028 | `8a1d456ee2098808940b591157be875fb53080c97119d0bc33221745148dd38e` | LF |
| `data/validation/core_signal_validation_continuous_parts/core_signal_validation_manifest.json` | 523376 | `008643a64e0070433f3d63dca8243f8dad294b049a7accb5d49af3597aae17b0` | LF |
| `data/validation/core_signal_validation/raw/daily_k.parquet` | 180203424 | `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426` | 工作区 |
| `data/validation/core_signal_validation/raw/adjustment_factors.parquet` | 295284 | `a1b7d63c5826ccd3610dc9bdd949d82eeb0ba84ffad451bfb8bb30ca74962716` | 工作区 |
| `data/validation/core_signal_validation/raw/index_000001_SH_2023.json` | 40966 | `c118fb39d31065914740da150455fba2375d3bcaa83566730d265df0753bb51c` | 工作区 |
| `data/validation/core_signal_validation/raw/index_000001_SH_2024.json` | 40983 | `53fc9e9f0989e67f8a826614c5c8f260171cf081801bf752df6301e69f4ae4bf` | 工作区 |
| `data/validation/core_signal_validation/raw/index_000001_SH_2025.json` | 41175 | `27acba0bd5bfc0f54d349d7dbc41a86bf6836dfee3976a970cbb210b287f76a1` | 工作区 |
| `data/validation/core_signal_validation/raw/index_000001_SH_2026.json` | 27109 | `183f472a1699811edb2550f3ce99b2b05d06c23473b5e2acff0ad2431eaf1514` | 工作区 |
| `data/validation/strategy_candidate_eligibility_v1/b_breakout_retest_eligibility_events.jsonl.gz` | 2506292 | `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9` | 工作区 |
| `data/validation/three_state_dividend_leaders_v1/raw/511260_SH_dividends.json` | 529 | `a0e8d14b85da75a7ec6cbfc3503e246d967d21dfd068f903627323bea028a44a` | 工作区 |
| `data/validation/three_state_dividend_leaders_v1/raw/511260_SH_nav.json` | 64084 | `d0b1e2909f5635193be7c4d14b063d99ea17490235320e853a77df4a0d16c10a` | 工作区 |
| `data/validation/three_state_dividend_leaders_v1/raw/511260_SH_ohlcv.json` | 101469 | `b265404bbd180014887b0d698e8622bda8e56147ede087b5d736d9501dcaf4a6` | 工作区 |
| `data/validation/three_state_dividend_leaders_v1/raw/518880_SH_dividends.json` | 32 | `5c3124db4ca1481c96a58f06614edd886083d48ff770f1a3edd257d1d8bbd807` | 工作区 |
| `data/validation/three_state_dividend_leaders_v1/raw/518880_SH_nav.json` | 63109 | `f5c09e034c530bd5d2c49e27e640e49bac7a80376449c22eaeaabf5a2ff78f47` | 工作区 |
| `data/validation/three_state_dividend_leaders_v1/raw/518880_SH_ohlcv.json` | 95497 | `5d5581fabcc475ab6e37596ad317f1054f3ec81d50c6e20340dbd6ee0ae11ef2` | 工作区 |
| `scripts/fetch_defensive_etf_validation_inputs.py` | 11322 | `08a8f5c0c2d27cfc194b15db2eaba097ccfca0ab572feb6a9d5154c0d368e3ce` | Git 输入锁 |
| `data/validation/defensive_etf_non_g2_v1/raw/input_manifest.json` | 2241 | `b865401b78c9d0fb0007bcf4fbb8a0a78bb75b14e06297811e2b4c5536368960` | Git 输入锁 |
| `scripts/defensive_etf_non_g2_v1.py` | 44661 | `aaaf4182fd0fceba58d9ff934bfae316f1c839e6972af80265b2ad560a79f67c` | Git 验证归档 |
| `data/validation/defensive_etf_non_g2_v1/summary.json` | 550614 | `c1b97ede42755fad2c68b26117a3f6abe08bab07129ebde72212c68e3c3e7da8` | Git 验证归档 |

## 收盘信号

- `G2_T` 为上证收盘严格高于含 T 的 MA20，且 MA20 严格高于第五个先前 XSHG 交易日的 MA20。两档 `STATE_STRONG = G2 & (B20 >= θ_B)` 固定为 W45、W50。每档 `NON_STRONG_3D` 为含 T 连续三个 XSHG 收盘均非强态，使用开窗前两个交易日预热市场门。强态优先。有三日确认且 `DIV_HUG_ON` 时为 `STATE_DIVIDEND_HUG`，有三日确认而红利趋势门未过时为 `STATE_FULL_DEFENSE`，未确认时为观察缓冲且无新开仓。
- 主板代码匹配 `00xxxx.sz/60xxxx.sh`，当日有正成交量的 bar，累计至少 250 根冻结日线，最近 20 根 T 锚点收盘均为正，计入 `B20` 分母。分子为 T 锚点收盘严格高于该 20 根均价。每根价由事件 `(p - dividend + allotment_price * allotment)/(1 + bonus + allotment)` 按除权日顺序作用，仅当 `t < ex_date <= T`。使用累计 scale/offset 的等价仿射坐标，抽样对照既有 `core_signal_replay._adjusted_bars`。历史窗口按该股冻结观察 bar 数计。
- `DIV_POOL_T` 从 B20 分母中要求 `raw_close > 3`、T 锚点近 61 根 OHLC 全正、含 T 近 20 根原始成交额中位数 `>=250000000`。正现金分红 `d_e` 折算为 `d_e / product(1+bonus+allotment)`，乘积只含 `e < split_ex <= T`，同除息日的送转配不重复折算。按除息日历年分别求过去两个完整年的 DPS，两年都须为正，`yield=(DPS[Y-2]+DPS[Y-1])/(2*raw_close_T) >= 0.035`。近 60 个相邻日收益 `r_i=p_T(close_i)/p_T(close_{i-1})-1` 的样本标准差 `std60` 满足 `std60*sqrt(250) <= 0.32`。
- 池成员趋势要求 `C_T > MA20_T > MA60_T` 且 `MA20_T > MA20_{T-5}`。后者使用同一 T 锚点、截至该股此前第 5 根 bar 的 20 根均价。池至少 15 只、趋势成员至少 2 只且占比 `>=0.40` 时 `DIV_HUG_ON`。池为空时占比记缺失，趋势门为假。入选只用趋势成员且 `ret20 <= 0.15`。涨幅 `retN=C_T / p_T(close_{T-N}) - 1`，风险调整分数 `round(ret60/std60,10)` 降序，继以股息率降序、代码升序。已持仓与结案日及后续五个交易日（含 E+5）冷却中的个股排除。未成交的隔夜候选释放槽位，原排队位置不递补。
- X1 只在抱团首次激活或期间每周最后一个 XSHG 交易日收盘补位。X2 在抱团每日补位，额外要求 `0 <= C_T/MA20_T-1 <= 0.03` 且原始收盘不低于原始开盘。各最多 2 槽，次一交易日开盘执行。

## 执行与组合

股票买入后的下一 XSHG 日起可卖。以沿用的 0.005 元舍入容差识别一字板，要求 `high == low`，一字涨停为 `open >= adjusted_prev_close * 1.10 - 0.005`，一字跌停为 `open <= adjusted_prev_close * 0.90 + 0.005`。次日缺成交 bar 或一字涨停跳过买入；一字跌停仍开盘建仓并登记首次合法开盘退出。停牌或一字跌停导致已触发退出无法执行时锁仓顺延。当一字跌停只阻碍可卖期且保护价未触发时，保留原止损和目标。相对于进入日固定的原始价位，触发参考价和单位成本以因果仿射坐标转换到执行日。按每笔入场名义本金的两侧各 10 bps 扣费，持仓每日预留退出费。

X1 硬保护位为入场价的 0.94 倍，开盘越过按开盘，盘中触及按保护价。每周最后一个 XSHG 日有效收盘严格低于同锚 MA30，或当日进入全面防守或强态，登记下一可卖日开盘退出。无固定期限。X2 设 0.95 止损与 1.10 目标，开盘穿越任一边按开盘，盘中单边按触发价，双触及记模糊并按止损入账。入场后第 25 个 XSHG 交易日仍未触发按收盘退出，停牌或锁跌顺延。强态同 X1 让位，全面防守保留已持仓原退出规则。期末仅按最近可用收盘估值。

B 保留同一冻结资格、G2 + L1 的 B V2 排名基础，Stage 1/2 将发单与成交市场门换成 `STATE_STRONG`。L1 为 `pos250 <=0.55, ret20 <=0.20, ret60 <=0.30`（12 位小数），结构只取 `EARLY_PULLBACK / W2_TO_W3_TRANSITION_PROXY`，要求 V1/V2 与 E0 价位有效。按 `(pos250,V1,code)` 升序每天最多 3 个新挂单，同股挂单或持仓去重，入选或结案后禁入至 E+5（含）。T+1 至 T+10 触价成交，开盘优先；一字涨停跳过当日。静态 E0 开盘优先，盘中双触及按止损；信号后第 10 日收盘到期，必要时延至首个可卖开盘。轮空时旧挂单继续计龄，不占用真钱。

无杠杆的单账户从现金 1 起步。Stage 0 精确沿用归档 `G2 + B V2 + R1/A1`。Stage 1 两组仅改变市场门，并保持 R1/A1 交易顺序。Stage 2 四组在抱团期新增 X1 或 X2 最多两槽，额度不超过扣除存量 B 后的空位，不重复占用同一证券。强态恢复次日，ETF 和可卖红利股先退出；仍锁仓红利保留实占槽位，B 只使用剩余槽位。旧 B 挂单可在可用槽位恢复后参与；容量不足时按挂单原有进入顺序。B 和新红利买入在状态上互斥，开盘清算后每槽目标为开盘权益的 1/6，以可交易现金均分封顶；盘中与收盘卖出所得不回填当天开盘预算。独立红利诊断同一状态、排序与费用，初始现金 1，槽位上限为 2，单槽为权益的 1/2，分别跑两个宽度下的 X1/X2。

ETF 为 `511260.SH` 国债与 `518880.SH` 黄金。只在含 T 连续三日非强时允许进入。20 根同锚除息价全部正且收盘高于均价才合格，各占剩余额度的 50%，未合格份额留现金。首次激活和持续期间每周最后一个 XSHG 收盘计算下一开盘的目标；原 ETF 腿绝对权重变化之和严格小于 10% 且无持仓失格时跳过。Stage 2 在股票占用或可成交红利预约变化时另做槽位调拨，按最近一次确认状态下的预算权重缩放，让出红利建仓资金；ETF 只用扣除开盘股票实际支出后可交易的现金及自己的变现净额。预算为 `(6-active_B-active_DIV)/6 × opening_equity`，开盘内计划买入的红利先计入。常规调仓采用上一收盘实占，已知开盘退出与有效预约可调整 Stage 2 当次额度，盘中变化最早于下一开盘调拨。可分份额，先卖后买，实际买卖额各扣 2.5 或 5 bps。无再平衡时额度随市值漂移，现金利率为零。强态时 ETF 清仓。

ETF 净值只用于原 R1/A1 校验，单位净值总增长与复权净值总增长之比容差 0.005。除息日价格以未复权 OHLC 估值并对隔夜持有份额一次性确认应收，场内派息到期才转入现金。国债四笔除息与到账分别为 2025-09-23 → 2025-09-26、2025-12-26 → 2025-12-31、2026-03-25 → 2026-03-30、2026-06-25 → 2026-06-30。

## 统计、决策与结束

每日收益以当日收盘权益除以前一收盘权益减一，首日前权益为 1。各区间收益为逐日复利，最大回撤用区间起始权益及随后逐日前高。收益/回撤比分母为正的最大回撤，无回撤时报缺失。2023 与 2026 弱年合计为两年各自累计收益相加。三段 2026 表按收盘状态归属，按 B、红利、债金逐日实际损益（含各自费用、盯市、债金应收）以初始本金的百分比列示，三腿和等于该段权益变动。独立红利成交笔数按实际买入日、结案数和单笔净胜率与净均值按结案日，模糊单按止损入账并标出笔数。高频标的按接受选股次数降序、代码升序，并附实际买入次数和池内天数。

固定非循环 20 日移动块，有放回抽取起点并裁到原长，5,000 次，每项以 `default_rng(20261129)` 初始化，95% CI 为线性 2.5% 与 97.5% 分位数。Stage 1 对全期配对日收益差的均值抽样。Stage 2 按 2023、2026 年内分别以同一抽样起点配对 Stage 2 与 Stage 1，分别复利求差后两年相加。以下需要的组合门和统计门在 5、10 bps 两档均须通过。

1. `DECISION_STAGE1_BREADTH_GATE` 要求全期净收益严格高于 Stage 0、回撤不超过 1.02 倍、收益/回撤比严格更高、2026 净收益严格改善，且全期超额日均为正。两档 CI 下界严格大于 0 为 `ADOPT`，优先 W50。其余经济条件全过且区间唯一未过项包含零，为 `NEEDS_MORE_EVIDENCE`，需要独立前瞻日样本缩窄超额区间。否则 `REJECT`。
2. `DECISION_STAGE2_DIVIDEND_SLEEVE` 首先要求对应独立红利账户 2023、2026 及全期净收益各严格为正、全期最大回撤不超过 8%。再要求全期、弱年合计的组合净收益均严格大于 Stage 0 和同宽度 Stage 1，最大回撤不超过 Stage 0 的 1.05 倍，收益回撤比不低于 Stage 0。两档弱年配对 CI 下界均严格为正为 `ADOPT`，优先 X1、再 W50。独立和组合经济门全过，仅 CI 含零为 `NEEDS_MORE_EVIDENCE`，需要更多独立弱市与结构分化日证据。独立门通过而至少一档对应组合全期或弱年合计净收益严格低于同宽度 Stage 1，且未达前两判定，为 `DEFER_OBSERVATION_ONLY_SUBOPTIMAL_VS_BOND_GOLD`。其余 `REJECT`。

输出两档费用的各组结果、两项独立决定、2026 年 1–3 月 / 4–6 月 / 7–8 月状态与 B、红利、债金拆解，以及动态池高频入选 TOP15。两次独立回放的汇总 SHA-256 字节一致，完成专项 pytest、compileall 和 git diff --check 后，仅提交本研究回放、测试、汇总及中文报告。推送独立研究分支后结束。
