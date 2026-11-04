# B_PRIORITY_W2W3_VOLUME_RESEARCH_V1：输入审计与真实 parity 数据缺口

**目前不能判断这套优先级有没有用。** 已重建冻结 B 样本的结构代理和三项量能，
但真实日报 observation 对应的原始 T 日输入没有恢复，无法完成用户要求的 historical
reconstruction parity。因此停在 `B_PRIORITY_RESEARCH_BLOCKED_BY_DATA_GAP`，没有运行
本研究的 outcome、R0–R3 收益比较或排名效果分析。这里没有支持或否定假设的收益证据。

先用大白话回答十一件事：

1. **“2→3切换”在合格 B 里有没有用？** 尚不知道；只能确认该结构代理可以因果重建。
2. **切换状态的 5D / 10D 是否优于普通 B？** 未计算，不能说明显优于或弱于。
3. **三个量能指标哪个真的有用？** 尚无效用比较；可计算比例不能当成有效性。
4. **量能综合能不能挑出更好的 Top1 / Top3？** 未运行。
5. **先结构、再量能的 R3 是否优于不排序？** 未运行，不能跳过真实 parity 前置条件。
6. **改善有多大？** 未知；uplift 保留 null，不写成 0。
7. **是否跨年份稳定？** 未评估。四个年份已有输入覆盖，尚无收益稳定性证据。
8. **风险有没有变差？** 未评估 MFE / MAE，不能声称风险不变或改善。
9. **足够支持“首选／次选／观察”产品吗？** 不足；暂不进入生产标签映射设计。
10. **值得把旧 Score 从主界面降级吗？** 本研究尚无支持证据，保持现状；生产 Score 修改为 0。
11. **下一步值得单独研究换手率吗？** 目前没有新证据支持扩大研究，DEFER；先由用户决定
    是否恢复 parity 输入。本任务没有启动换手率研究。

## 研究身份、冻结顺序与边界

- Classification 始终为 **research question / STRICT PATH**，不是整个产品的 blocker。
- 独立分支 `codex/b-priority-w2w3-volume-v1`，从实时 master
  `7d7b6c9f2de1c45e1a4b1a493395ac81646489d8` 启动；没有堆叠、merge 或 cherry-pick 旧研究分支。
- [#103](https://github.com/EFSing/ashare_watchlist/pull/103) 已 squash merge；该 master
  的 [correctness run 41767491750](https://github.com/EFSing/ashare_watchlist/actions/runs/41767491750)
  为 exact-head SUCCESS。Runtime-state intake 为
  `ebe014748cfd3a551b0e3589124e08b2c154871d`。Open PR #60/#66/#67/#68/#71/#84/#87/#89 未修改。
- `PRE_OUTCOME_PROTOCOL_COMMIT` = `13008a3579a225af1f89f1facee1f22c48050195`。
  [协议](b_priority_w2w3_volume_v1_protocol.md) 已在本研究 outcome 访问前提交。
  协议同时要求真实 parity 通过后才能读取 outcome；本次没有满足这一前置条件。
- `B_OPERATIONAL_SCORE_VOLUME_RANKING_V1` 从未运行，状态为 **NOT_STARTED /
  SUPERSEDED_BY_USER_DECISION**。此前的
  `B_CANDIDATE_RANKING_VOLUME_TURNOVER_DIAGNOSTIC_V1` 与
  `B_RANKING_BASELINE_SCORE_IDENTITY_NOT_RECOVERABLE` 继续有效，不能写成被本研究推翻。
- 本研究不使用旧 Score、sector、turnover、RV20_T、其他指标或其他 repo 的数据。
  结构是 **B-native 价格结构代理**，不是 Elliott 浪型预测成功的证据。
- 所有本研究收益值、IC、bootstrap CI、stop/target 比较均未计算。没有混合 MODEL_P / MODEL_R，
  没有替换 entry price，没有读取 Final OOS（**SEALED / UNREAD**）。

## Exact cohort 与输入覆盖

冻结 interval 为 2023-06-30..2026-08-28，共 769 个 signal sessions。
Qualified stream 实际核对 **17,714 个唯一身份 / 763 个候选日**；不是每个 session 都有候选。
旧文件名中的 V1 身份通过既有 V1_1 corrected event-membership proof 对齐，没有重定义资格。
价格沿用既有 T-anchor affine adjustment、只应用截至 T 的公司行为，volume 保持 raw。
原始官方 dump 缺少逐 bar 历史 vintage timestamp；因果性测试通过不等于已经证明历史
known-at，也不会把这些 DEVELOPMENT 输入改称真实前瞻样本。

| Board | Qualified rows | 候选日 | 结构可定义 | 三项量能完整 |
|---|---:|---:|---:|---:|
| **Main（Primary）** | **10,779** | **749** | **9,085** | **7,861** |
| ChiNext（Secondary） | 4,416 | 669 | 3,936 | 3,488 |
| STAR（Secondary） | 1,813 | 501 | 1,550 | 1,354 |
| Beijing / OUT_OF_SCOPE_PREFIX（单列） | 706 | 314 | 648 | 581 |
| 全 frozen qualified cohort（仅总量） | 17,714 | 763 | 15,219 | 13,284 |

Secondary Main + ChiNext + STAR = **17,008 条 / 762 日**。706 条北京 identity 不属于
Main，不用于当前生产的 Primary 结论。Board 使用已有 deterministic prefix mapping。

Main 结构覆盖为 **84.28%**（9,085 条 / 736 日），三项量能 complete case 为
**72.93%**（7,861 条 / 719 日）。Complete case 中结构可定义 7,541 条；其状态为
EARLY 5,546、TRANSITION 1,908、CONTINUATION 87、INVALID 320。
R2/R3 可用输入子集中的 Top1 / Top3 / Top5 候选日分别为 **648 / 559 / 439**。
这些是 **outcome 可用性检查之前** 的日期上限，不是最终可评价日期。

| Main 年份 | Qualified rows | 候选日 | 结构可定义 | 三项量能完整 |
|---|---:|---:|---:|---:|
| 2023（从 06-30 起） | 1,571 | 125 | 1,275 | 1,062 |
| 2024 | 4,111 | 234 | 3,697 | 3,406 |
| 2025 | 3,817 | 238 | 3,050 | 2,519 |
| 2026（截至 08-28） | 1,280 | 152 | 1,063 | 874 |

按 `(symbol, first-breakout date)` 可识别 Main 5,628 / ChiNext 2,642 / STAR 1,061 /
北京 435 个 episode。只审计 episode identity，未进行 dedup outcome sensitivity。

## 表 1：Main 结构状态

| 结构状态 | 样本 | 日期 | 5D | 10D | Positive Rate | MFE | MAE | 判断 |
|---|---:|---:|---|---|---|---|---|---|
| EARLY_PULLBACK | 6,424 | 695 | — | — | — | — | — | 已重建，效用未评估 |
| W2_TO_W3_TRANSITION_PROXY | 2,512 | 621 | — | — | — | — | — | 已重建，效用未评估 |
| POST_H1_CONTINUATION_PROXY | 149 | 122 | — | — | — | — | — | 单列，没有并入 transition |
| INVALID / UNAVAILABLE | 1,694 | 536 | — | — | — | — | — | 保留缺失状态，没有剔除身份 |

日期可重叠，不能纵向相加。所有“—”表示 **NOT_RUN**，不是零。
L0 / H1 / L2、首次 equal-high、无完整回踩日、无效分母和 T 排除规则严格按协议实现。
R1 没有强造 Top1 排名；full 与 common-intersection outcome comparison 均未运行。

## 表 2：Main 的三个量能指标

| 量能指标 | 方向 | Coverage | IC | Top-Bottom | 单调性 | 跨年 | 判断 |
|---|---|---|---|---|---|---|---|
| down_volume_share | 越低越好（预注册） | 9,880 / 10,779 = 91.66% | — | — | — | — | 只有覆盖证据 |
| up_down_volume_ratio | 越高越好（预注册） | 8,558 / 10,779 = 79.40% | — | — | — | — | 只有覆盖证据 |
| pullback_volume_decay_ratio | 越低越好（预注册） | 7,944 / 10,779 = 73.70% | — | — | — | — | 只有覆盖证据 |

窗口固定 `i+1:T`，排除 T；缺失不填零、不填均值。Complete case 为 7,861 条，尚未计算
任何同日 percentile、volume_quality 或收益排序。表中“好方向”是待检验假设，不是本次发现。
逐字段 missing reason 保存在 summary 与可重建 detail；字段级计数不能当成独立 candidate 数。

## 表 3：真正的选股优先级

| 方法 | Top1 uplift | Top3 uplift | Top5 uplift | 5D | 10D | MFE | MAE | 跨年稳定 | 判断 |
|---|---|---|---|---|---|---|---|---|---|
| R0 无排序 | — | — | — | — | — | — | — | — | 未运行，真实 parity 输入缺失 |
| R2 量能 | — | — | — | — | — | — | — | — | 未运行，真实 parity 输入缺失 |
| R3 2→3结构代理 + 量能 | — | — | — | — | — | — | — | — | 未运行，真实 parity 输入缺失 |

没有把全样本 R0 与量能完整子集比较。协议已经冻结相同 rows/dates benchmark、
signal-date cluster bootstrap、年份、episode 去重及异常日期敏感性，但没有冒充已完成。

## 实际停止原因：真实 observation 的输入没有恢复

从 pinned runtime-state 实际读取并核对 **24 份日期文件**（2026-09-21..2026-11-03，
其中 23 日有 candidate）、共 **223 条 identity**：156 条三字段完整，67 条不完整。
核对了文件 SHA/bytes、signal_id、date、candidate_count、complete_count 和 missing reason
存储。示例：09-21 为 24 / 完整 22 / 不完整 2；09-22 为 16 / 14 / 2；11-03 为 14 / 8 / 6。
这些核对验证存储可读和身份完整，**没有完成 historical reconstruction parity**。

缺少的是上述日期原始、provenance-bound 的 T 日 OHLCV prefix / 输入包：

- runtime-state tree 没有 `generation_input`、`input_package` 或 `t_close_evidence` 原始输入；
  `cloud_runtime_state.py` 明确将 raw/generation inputs 留在临时 ASHARE_DATA_ROOT。
- `daily_t_close.yml` 将该 root 放在 RUNNER_TEMP，没有上传这些输入的 artifact step。
- shadow pre_outcome 保留派生观察值和输入 SHA，没有完整 K 线前缀，不能反解原始输入。
- 本机现有冻结 daily-K 的实际身份截止 2026-08-28，与全部 observation 日期不重叠。
- 通过 Google Drive 只读搜索和本项目 root / daily_checkpoints / research_archive 目录核对，
  可见归档有 09-07 T-close、09-08/09-09 checkpoints 以及早期独立研究，没有找到这些
  observation 日期的输入包。没有读取其他项目或 sealed 数据，也未将搜索未命中表述成全世界不存在。

所以 parity 状态为 **NOT_RUN_INPUTS_UNAVAILABLE / NOT_REPRODUCIBLE_WITH_CURRENT_DATA**；
实际重建真实日期 = 0，真实 candidate = 0，mismatch count = null。
这不是 `B_VOLUME_OBSERVATION_HISTORICAL_PARITY_FAILED`，也没有宣称 parity PASS。
历史样本内的两条现有计算入口一致，只能证明代码路径一致，不能替代真实日期 parity。

## 三个独立 decision 与产品含义

```text
B_W2W3_TRANSITION_PRIORITY_NEEDS_MORE_EVIDENCE
B_REPORT_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE
B_W2W3_VOLUME_PRIORITY_NEEDS_MORE_EVIDENCE
```

统一研究 decision = **NEEDS_MORE_EVIDENCE**，理由为输入前置证据不足，不是负面效用结论。
尚不输出 `PRIORITY_PRODUCT_DESIGN_WARRANTED`，旧 Score 保持当前生产行为。
如果将来 R3 在 Main、Top1/Top3、跨年、episode 与风险检查中支持进一步验证，才建议用户
在另一个产品 PR 中决定：B 资格保持原规则；独立展示结构阶段和量能质量；今日优先级仅用
“首选／次选／观察”；再决定旧 Score 降级或移入历史参考区。本次不实施任何映射。

需要用户决定的真实节点：恢复至少多个真实日期的原始 T 输入及其 provenance，覆盖完整
与缺失 candidate；或明确决定是否修改这项前置研究要求。没有这些证据，不继续 outcome
分析。不得以 current-data backfill、复制 observation 或重获当前历史数据冒充原始输入。
研究暂停不影响现有 Formal B 每日流程、三个报告观察项和既有前瞻记录。

## 复现、验证与交付

审计入口为 `scripts/b_priority_w2w3_volume_v1.py`，只有输入审计路径，**未实现或运行收益分析**。
先从现有归档恢复六个 frozen raw members 至任一目录，匹配 manifest SHA，再执行：

```powershell
python scripts/b_priority_w2w3_volume_v1.py --raw-dir <restored-core_signal_validation/raw>
```

`daily_k.parquet` 的既有恢复引用是本项目 Drive folder
`1KjQa8SmorXoHnEpN3WxKrKiYB-TsCTTJ` / member `1lLxp0y_csfOczwEBNYo4ysdyItBgF4Ja`；
本轮验证的是本机现存 bytes 的 exact frozen SHA，没有重新获取 provider 数据或声称完成新 Drive readback。
其余五个 raw members 已由现有 Git/manifest 路径标识。命令从 Git 的 pinned runtime-state 读取
observation stores，不写 runtime-state。恢复研究不依赖聊天记忆或新的本机独占数据。

Outcome-blind detail：`data/validation/b_priority_w2w3_volume_v1/input_features.jsonl.gz`，
17,714 行，971,997 bytes，compressed SHA-256
`1c4f70aff7cf9d6262ccbc89507b6ec35483f6207dc644279ca3e2ae4ae4dd82`，content-stream SHA-256
`4b20355d1ca6b1a19db3d3d11374090f62e40fdb57a3e5a31f6305f06299e11d`。
Detail 可用上面命令确定性重建，不提交；小型 `summary.json` 在 Git 中保存覆盖、逐真实文件
hash、输入身份、决策及 null metrics。Qualified compressed hash 与六个 frozen raw hash 均实测匹配。

Final focused/relevant tests 57 passed；full pytest 852 passed / 2 existing large-fixture skips /
10 warnings；compileall 与 diff checks passed。17,714 个真实历史前缀均完成身份保留、
future-append invariance 与 public-volume-wrapper 一致性检查；这些不是缺失的真实 observation parity。
最终代码两次完整重建的 summary 与 detail bytes/SHA 均相同。Summary 为 26,762 bytes，
SHA-256 `beebccfe664c53f6738404fa25644432f9bd6c2446bd59b19ec86031f19332a5`；
Node dispatcher 检查 5 passed。Draft PR、exact-head CI 和 mergeability 由本分支 HANDOFF
及最终 live delivery readback 记录，不能把本次输入阻断写成研究成功终点。
独立交付为 [Draft PR #104](https://github.com/EFSing/ashare_watchlist/pull/104)，
base = 创建时 live master；恢复时直接从 PR 重读 current head 与 CI，不将 transient SHA
或 run ID 当成永久不变量。

Formal B qualification/spec、trigger/stop/target、production Score/report、tracker、
MODEL_P/MODEL_R、runtime-state、provider、C、scheduler 均未修改；production dispatch = 0；
没有自动 merge。任务分类未改变；Final OOS = **SEALED / UNREAD**。
