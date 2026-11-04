# C_RULE_FUNNEL_STRICTNESS_AUDIT_V1

日期：2026-11-04。归类始终为 research question / STRICT PATH。

C 最近确实少，而且近期更少了。现有 **21 个真实 C 报告日，共 36 个股票日匹配，
日均 1.71 只，6/21 天为零（28.57%）**；全部来自 BALANCED_A，CONSERVATIVE_B
为零。36 个股票日涉及 23 只不同股票，不是 36 只独立股票。
你给出的 10-08 至 11-03 区间重算为 **18 天、29 个匹配、日均 1.61 只、
6/18 天为零（33.33%）**，与 intake expectation 一致。

**目前不能诚实地判定主要是市场原因还是规则过严。** 原因不是统计方法缺失，
而是近期全量淘汰记录及其原始 T 日输入未恢复；日报只留下最终入选股票。
本次完成了频率和可恢复的条件诊断，**没有完成全市场 F0–F8、数值 margin、
局部 near-miss 或单项放宽模拟**。下面的 null/未运行不是零。

能够直接回答的十二个问题：

1. **到底多少票？** 全部可用报告日日均 1.71；最近十个报告日日均只有 0.6。
2. **市场还是条件？** `C_SCARCITY_CAUSE_NEEDS_MORE_EVIDENCE`；不能给市场/规则比例。
3. **第一大瓶颈？** 全市场未知。在 Balanced 已入选这个偏选子集中，Conservative
   的趋势联合条件失败 34/36，且这 34 项的 close>fast、fast>slow 均已通过；
   剩余嫌疑为 90 日 slope 和 up_close_fraction，二者无法从日报区分。
4. **第二、第三？** 同一偏选子集另有 20 个 depth/time 聚合失败、9 个 rebound
   聚合失败；它们不是全市场 top 2/3，不能把聚合状态当作单个硬阈值根因。
5. **T 日确认太苛刻？** 未证实。全部未入选股票的四项确认子条件未保存。
6. **higher-low/pivot 太苛刻？** 未证实。选中子集没有该聚合失败不代表全市场没有。
7. **深度范围太窄？** 未证实。现有 depth 失败状态同时可能表示 peak 太旧；
   没有失败值，无法识别 0.12–0.14 聚集。
8. **Conservative 为什么零？** 已看到明显的趋势门槛差异，也看到结构失败重叠；
   全市场 `CONSERVATIVE_B_ZERO_MATCH_DOMINANT_CAUSE=UNRESOLVED_POPULATION_INPUTS_UNAVAILABLE`。
9. **只研究一个放宽条件？** 现在不选生产或历史研究阈值。最先需要诊断的是
   Conservative 的 up_close_fraction 与 slope 分拆；这只是取证优先级。
10. **研究两个？** 第二个取证方向是 peak 年龄与 depth 越界分拆。完整漏斗恢复前，
    `next_relaxation_conditions=null`，不把这两个方向写成已选定放宽条件。
11. **哪些不应动？** 当前主板/非 ST、T 日身份、pre-T pivot 确认、支撑收盘破位
    边界均无放宽证据。量能不是 entry gate，不能通过“放松量能”增加匹配。
12. **是否进入轻微放宽版历史研究？** `DEFER` 参数/条件选择；本审计 decision 为
    `NEEDS_MORE_EVIDENCE`。先恢复全量 T 日输入或已有全量 C 观察记录；本任务不启动后续研究。

## 输入与真实性边界

- Source master：`334f636a98c17d31c3f3251b8ce3d3859132c3b7`，#104 已合并。
  #104 head 的 correctness runs `41818259473` / `41818251400` 和 master
  exact-head run `41820494903` 均 success。旧治理文档待决策措辞已最小同步为历史记录。
- Pinned runtime-state：`ebe014748cfd3a551b0e3589124e08b2c154871d`。
  截止 11-04，只有 09-24 至 11-03 的 21 个 dated C manifests；少于 40，使用全部。
  每个 dated alias 与 immutable version 的 manifest/HTML 字节一致，HTML SHA 验证通过。
  同一日两个路径不重复计数。没有日报的日期不按零计入；没有声称覆盖全部交易日。
- 这是真实 runtime 的研究输出，**不是** historical reconstruction，也不是正式
  prospective capture：全部 `prospective_captured=false`、`formal_b_signal=false`、
  `coverage_status=PARTIAL_UNVERIFIED`、价格观察/量能调整口径未核验。
- 09-24 manifest 尚无 `c_status`；其 HTML 明确保存两规则 pending count 均为零，
  因而恢复为成功且有匹配；summary 单独标记 `c_status_source`。其余状态直接来自 manifest。
- 频率是已成功记录报告日上的描述；所有 21 日可计入，不能推断未生成报告日的匹配数。
- 精确 C eligible count 无法恢复。`c_st_or_rule_excluded` 可能对已验证 ST append
  两次；history prefix 检查发生在该计数前；不同排除项可能重叠。不能用
  `b_evaluated - excluded - gaps` 捏造分母。

BALANCED_A 有匹配的日期为 15/21（71.43%）；CONSERVATIVE_B 为 0/21。
相对 B evaluated 的股票日匹配率分别是 36/66,956（**0.05377%，仅代理分母**）和零。
精确 C eligible-stock hit rate 两者均为 null；Conservative 的 observed match count
为零，并不恢复出其 eligible denominator。

## 表 1：逐日真实产出与缺口

所有日期 C eligible universe=未恢复、质量=PARTIAL_UNVERIFIED。状态 M 表示
C_SUCCESS_WITH_MATCHES；Z 表示 C_SUCCESS_NO_MATCH。隔离为 B input isolated；
短历史为 `B_HISTORY_PREFIX_INCOMPLETE` symbol 数。完整逐日 status、原始 coverage
计数、所有 gap 字符串、package/manifest/HTML SHA 均在 `summary.json`，不做零填补。

| 日期 | B 可评估股票 | Balanced 命中 | Conservative 命中 | 总命中 | C 状态 | B 隔离 | 短历史缺口 |
|---|---:|---:|---:|---:|---|---:|---:|
| 2026-09-24 | 3188 | 2 | 0 | 2 | M（HTML恢复） | 8 | 9 |
| 2026-09-28 | 3188 | 1 | 0 | 1 | M | 9 | 7 |
| 2026-09-29 | 3188 | 4 | 0 | 4 | M | 8 | 7 |
| 2026-10-08 | 3185 | 6 | 0 | 6 | M | 13 | 8 |
| 2026-10-09 | 3186 | 2 | 0 | 2 | M | 12 | 8 |
| 2026-10-12 | 3188 | 9 | 0 | 9 | M | 10 | 8 |
| 2026-10-13 | 3187 | 1 | 0 | 1 | M | 11 | 8 |
| 2026-10-14 | 3189 | 2 | 0 | 2 | M | 9 | 8 |
| 2026-10-15 | 3189 | 2 | 0 | 2 | M | 9 | 8 |
| 2026-10-16 | 3189 | 1 | 0 | 1 | M | 9 | 8 |
| 2026-10-19 | 3186 | 0 | 0 | 0 | Z | 10 | 8 |
| 2026-10-20 | 3190 | 0 | 0 | 0 | Z | 6 | 8 |
| 2026-10-21 | 3190 | 2 | 0 | 2 | M | 6 | 8 |
| 2026-10-22 | 3191 | 1 | 0 | 1 | M | 5 | 8 |
| 2026-10-23 | 3191 | 0 | 0 | 0 | Z | 3 | 8 |
| 2026-10-26 | 3188 | 1 | 0 | 1 | M | 6 | 8 |
| 2026-10-27 | 3188 | 0 | 0 | 0 | Z | 6 | 8 |
| 2026-10-28 | 3189 | 1 | 0 | 1 | M | 5 | 8 |
| 2026-10-29 | 3189 | 1 | 0 | 1 | M | 5 | 8 |
| 2026-11-02 | 3189 | 0 | 0 | 0 | Z | 4 | 8 |
| 2026-11-03 | 3188 | 0 | 0 | 0 | Z | 6 | 9 |

每日报告还记录 B qualified symbols 不在 evaluation package、B raw capture 不完整、
B input failure isolated symbols 缺失于 C history、volume adjustment 未决。
这些是输入/覆盖限制，不等于已知数目的规则淘汰。

前十个报告日（09-24..10-16）30 个匹配、日均 3.0、零匹配 0%；后十个
（10-20..11-03）6 个、日均 0.6、零匹配 50%。窗口互不重叠，10-19 不在任一十日窗口。
因此本段观察期内后期更少；没有更早连续真数据，不能说“一直如此”，也不能
由下降本身识别市场和规则的因果贡献。

## 表 2：全市场 F0–F8 的证据可用性

下面是完整漏斗的**未完成状态**，不是伪造的漏斗。U=`NOT_RUN_INPUTS_UNAVAILABLE`。
F8 只恢复最终计数，其进入数和淘汰率仍未知。F1 还受 adapter 的统一 90-bar
minimum 限制，不仅是 Balanced 60 日 / Conservative 90 日趋势窗口。

| Funnel 层 | Balanced 进入 | Balanced 通过 | Conservative 进入 | Conservative 通过 | 淘汰率 |
|---|---:|---:|---:|---:|---|
| F0 主板/非ST/T身份/历史可计算 | U | U | U | U | U |
| F1 历史长度/pivot/pullback窗口 | U | U | U | U | U |
| F2 四项趋势子条件 | U | U | U | U | U |
| F3 pivot/distinct higher lows/间隔/前高 | U | U | U | U | U |
| F4 depth/peak年龄 | U | U | U | U | U |
| F5 confirmed rebound/size | U | U | U | U | U |
| F6 T日四项确认 | U | U | U | U | U |
| F7 支撑 | U | U | U | U | U |
| F8 最终价格结构匹配 | U | 36 | U | 0 | U |

可恢复的**条件对照**：把同一 36 个 Balanced 已匹配股票日送入其日报已保存的
Conservative 判断，并非重算全市场 counterfactual。

| 条件子集顺序 | 进入 | 通过 | 说明 |
|---|---:|---:|---|
| Conservative 趋势联合条件 | 36 | 2 | 34 失败；36 项 MA 顺序与 close>fast 均通过 |
| 在这 2 项内，完整 structure | 2 | 0 | 1 项 depth/time 状态、1 项 rebound 状态 |
| 后续确认与支撑 | 0 | 0 | 这是条件子集的空集，不代表全市场无人到达 |
| 最终 Conservative 匹配 | 0 | 0 | 与 manifest 的零匹配相符 |

独立地看 36 项结构：7 项 OK，20 项 depth/time 聚合失败，9 项 rebound 聚合失败。
结构 OK 的 7 项全部趋势失败；其中 5 项确认、支撑通过，2 项确认和支撑均失败。
这些是重叠联合条件，不能把 34+20+9 相加成淘汰总数。

## 表 3：已选子集的失败原因与 near-miss 限制

此表分母仅为 36 个 Balanced 已匹配股票日；全市场失败原因排名仍为 null。

| 失败原因 | 数量 | 占比 | 局部 Near-miss 数量 | 是否疑似过严 |
|---|---:|---:|---|---|
| Conservative trend_qualified=False | 34 | 94.44% | 未知；仅5项是“其他联合门槛已过” | 值得分拆 slope/up fraction，尚不能判定 |
| PULLBACK_DEPTH_OUTSIDE_CANDIDATE | 20 | 55.56% | 未知 | depth 与 peak 年龄混合，不能归因于深度范围 |
| NO_CONFIRMED_REBOUND_HIGH | 9 | 25.00% | 未知 | 无 confirmed high 与 size 越界混合 |
| confirmation=False（已计算部分） | 2 | 5.56% | 未知，且两项同时支撑失败 | 四项子条件未保留 |
| entry_support_ok=False（已计算部分） | 2 | 5.56% | 未知 | 没有放宽收盘支撑边界证据 |

五项“只差趋势联合门槛”是：09-24/601598、09-29/601598、10-09/601598、
10-12/601088、10-12/601098。它们不是五个已证实的“只差一个趋势子条件”near-miss。
日报未保留 slope 和 up-close fraction，两项可能同时失败；单项去掉后是否新增也未知。
原始 detail 保存了全部 36 项的两规则布尔/状态，便于定向恢复核查。

## 当前规则差异与数值 margin

| 当前定义 | BALANCED_A | CONSERVATIVE_B | 本次可恢复的 margin 分布 |
|---|---:|---:|---|
| trend window / fast MA / slow MA | 60 / 20 / 60 | 90 / 20 / 90 | U |
| minimum_up_close_fraction | 0.55 | 0.60 | U |
| pivot_radius / minimum_pivot_separation | 2 / 3 | 3 / 4 | U |
| maximum_pullback_sessions | 20 | 25 | U |
| peak 年龄实际上限（max sessions + 2×radius） | 24 | 31 | U |
| shallow_depth_min..max | 0.03..0.12 | 0.04..0.15 | U |
| rebound_size_min..max | 0.02..0.08 | 0.02..0.10 | U |
| confirmation_close_location | 0.60 | 0.60 | U |
| support_tolerance | 0.01 | 0.015 | DISPLAY_ONLY，不是支撑 entry gate |
| resistance_tolerance | 0.01 | 0.015 | diagnostic，不是 entry gate |

close>fast、fast>slow、slope>0、close>rebound high、close>previous close、
close>open 都是严格大于；location 和 depth/rebound 两端使用包含边界。
不能由两位小数的 HTML 深度或相同 threshold 推导 full-precision margin。
通过/失败分布、距阈值距离、极小距离失败数量全部未运行，不声称 0.548 靠近 0.55
或 0.12–0.14 的真实股票分布。

两个容易误读的状态来自 frozen implementation：

- `PULLBACK_DEPTH_OUTSIDE_CANDIDATE` 也可能因为所有 peak 过旧，根本没有执行深度判断；
  最大回踩窗口实际用于 `T - peak_index <= maximum_pullback_sessions + 2*pivot_radius`。
- `NO_CONFIRMED_REBOUND_HIGH` 也可能已经存在 confirmed high，但 rebound_size 不在范围。
  枚举的多个 low pairs 可以互相 rescue；必须按真实选择顺序复现，不能按任意失败 pair 计股票淘汰。

Conservative 的 depth 上限和 rebound 上限实际上更宽；它的零匹配不能简单解释为
“所有阈值都比 Balanced 更窄”。radius/window 改变还会改变被选 pivot/peak/pair。

量能是 observation/diagnostic，不参与当前价格结构 baseline entry candidate。
实际 gate 是 trend + structure + confirmation + support；缺失 volume 口径证据
使正式量价 entry 保持关闭，但不是本报告 price_structure_match 稀少的量能筛选原因。

## 表 4：candidate-count sensitivity 未运行

下列仅为 protocol 预先列举的独立候选计数操作；没有选择 top 3，也没有执行模拟。
每项只改单个字段，不组合、不读取收益；pivot 变化可能同时新增与丢失。

| 单项条件轻微放宽 | 当前观察候选数 | 新候选数 | 增量 | 覆盖日期变化 |
|---|---:|---|---|---|
| up_close_fraction minimum -0.02 | Balanced 36 / Conservative 0 | U | U | U |
| depth maximum +0.02 | 36 / 0 | U | U | U |
| rebound maximum +0.02 | 36 / 0 | U | U | U |
| 去掉 positive_body | 36 / 0 | U | U | U |
| close_location minimum -0.05 | 36 / 0 | U | U | U |
| pivot radius -1 或独立 separation -1 | 36 / 0 | U | U | U |

标签：`CANDIDATE_COUNT_SENSITIVITY_ONLY`。没有 5D/10D、MFE/MAE、MODEL_R/P outcome、
收益筛阈值或 grid search。表中 U 不支持任何一个放宽项能增加多少票。

## 缺口核查与继续所需证据

核查范围限于本项目，不是无边界搜索：

- Pinned runtime-state 没有全量 C observation JSON、输入包或 raw Kline。
  `c_daily_watchlist.build_watchlist` 只保留至少一个 rule matched 的股票，HTML 又只显示
  聚合布尔/状态和四舍五入值；manifest 的 package SHA 不是 package 本身。
- `daily_t_close.yml` 的数据根和 C report 中间产物位于 RUNNER_TEMP；没有原始输入的
  upload-artifact step。独立 C private-handoff workflow/未启用后端不等于已存在记录。
  GitHub connector 不支持仓库全局 artifacts GET；未声称完成全局 artifacts 穷举。
- 当前本机相关 C/daily/B-priority worktree 的已知 evidence/observation 恢复目录未找到
  这批日期输入。现有冻结 historical daily-K 截止 08-28，无法代替 09-24 以后 T-bound 输入。
  未为本研究读取它或任何收益文件；Secondary historical cohort 未运行。
- 2026-11-04 Drive 只读元数据核查：项目根
  `13_-tlozdfe1KEtNSMxp6pCroI893g_qH` 只见 daily_checkpoints、09-07 T-close、research_archive、
  daily_k backup；checkpoints 下为 09-08/09-09/latest；research_archive 为早期 RS/VCB/CRSR。
  对 202610/202611/c_prospective/b-c-input 文件名的搜索无结果。没有打开这些历史研究
  内容，也不把“在已检查来源未找到”写成“所有地方都不存在”。

需要：这些 real dates 的全量原始 C observations（包括 rejected stocks、完整精度的
trend/structure/confirmation/support 和输入身份），或匹配 manifest package SHA 的
B frozen packages 与 T 日身份/响应时间证明；pivot/radius/深度 sensitivity 尤其需要
完整 OHLCV prefix。仅有 36 个命中股票或新抓 current data 均不满足总体问题。

恢复后，先验证原 C matches 完全复现，再计算逐票/逐层子条件和全精度 margin。
这些证据供本次 scarcity causal decision 和之后“是否选择 1～2 项研究”使用；
证据未恢复前，现有 Formal B、C 每日报告与既有 prospective 记录均可继续。
没有因此新增产品 blocker、Phase、shadow、gate 或 recovery framework。

## 决策与复现

研究决策：`NEEDS_MORE_EVIDENCE`。

- C 整体：`C_SCARCITY_CAUSE_NEEDS_MORE_EVIDENCE`。
- Conservative：`C_CONSERVATIVE_B_STRICTNESS_NEEDS_MORE_EVIDENCE`。
- `CONSERVATIVE_B_ZERO_MATCH_DOMINANT_CAUSE=UNRESOLVED_POPULATION_INPUTS_UNAVAILABLE`。
- 全市场 top 3、MARKET_SCARCITY/RULE_STRICTNESS 分解与 next relaxation conditions：null。
- 条件选择/轻微放宽历史研究：`DEFER`，不废除 Conservative。
- ADOPT 用户后续 B/C 产品方向：资格判断 → 结构状态 → 独立证据 → 优先级/解释；
  不设计 Score/加权总分；qualification 与 priority 分开。

Protocol 在聚合分析前提交：`bedb730`。可从 remote Git 单独恢复所有本次派生文件；
不依赖聊天、本机未提交 raw 或 cloud token。

```powershell
git fetch origin
python scripts/c_rule_funnel_strictness_audit_v1.py --runtime-ref ebe014748cfd3a551b0e3589124e08b2c154871d --cutoff 2026-11-04
```

Artifacts 位于 `data/validation/c_rule_funnel_strictness_audit_v1/`：

- `daily.csv`：21 行 / 1,462 bytes，SHA-256
  `38716287df6b276bdb21f6942c542808cbda3cfcc7a9008f29da5a9ce9b40082`。
- `selected_match_diagnostics.jsonl`：36 行 / 23,417 bytes，SHA-256
  `028ba12503080c470fdbe1cf025d2cd62d33332debbe2007b880d0adef85a1c8`。
- `summary.json`：记录所有源 identity、逐日 gaps、频率、frozen rule snapshot、缺失值
  和上述 artifact hashes；SHA-256
  `0d50b08bc44d13ef7744d354e13e1500b1d36fef998a1b6b1744ab7a5c877b9d`。

验证：focused tests 10 passed；full pytest 870 passed / 2 existing missing
large-fixture skips / 10 warnings；compileall、Node dispatcher 5 tests、diff check
通过。两次真实输入重跑的三个输出文件 hashes 完全相同。测试覆盖日期去重、双规则
union、cutoff、pending/failed 不当零、legacy 显式 pending 证明、alias/version/hash/count
损坏 fail closed、四舍五入数值不当 margin、趋势联合失败不当单项 near-miss。
与 live master 的生产/C规则/Formal B/renderer/workflow diff 为空；runtime-state remote
仍为 intake SHA。PR exact-head CI 与 mergeability 是 live 属性，从独立 Draft PR 读取。

边界：production semantics change=0；C rule definitions/Formal B/renderer/scheduler/provider
/runtime-state 均未修改；provider calls/writes=0；production dispatch=0；Final OOS
`SEALED / UNREAD`，禁用目录未访问。没有收益读取、后续研究、部署或自动 merge。

交付停止点：`C_RULE_FUNNEL_STRICTNESS_AUDIT_READY_FOR_USER_DECISION`，含明确的未完成
证据缺口，不代表完整 funnel 已完成或任何门槛已被证明过严。
