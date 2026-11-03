# B 候选同日排序：量能／换手 V1 — 精确基线阻断报告

任务：`B_CANDIDATE_RANKING_VOLUME_TURNOVER_DIAGNOSTIC_V1`。
归类始终为 `research question`，STRICT PATH；证据身份为 `DEVELOPMENT` /
`RECONSTRUCTED_RETROSPECTIVE` / `SAME_DAY_CROSS_SECTIONAL_RANKING` / `DIAGNOSTIC_ONLY`。

**结论：现有冻结证据无法恢复完整 B Score，本次排序效用未评价。**
停止标记：`B_RANKING_BASELINE_SCORE_IDENTITY_NOT_RECOVERABLE`。
允许的主决策：`B_VOLUME_TURNOVER_RANKING_NEEDS_MORE_EVIDENCE`。
这是缺少合法比较基线，不是量能或换手无效的实证结论。

## 直接回答用户的问题

- **原 B Score 有没有同日选股排序价值？** 目前不能回答。精确历史 Score 缺失，不能
  用不含行业分项的分数、统一默认值或现在的行业信息代替它。
- **日报三项量能哪个有用？** 本次没有合法计算任何一项的排序增量，三项均为未评价。
  原有 `VOLUME_PATH_NEEDS_MORE_EVIDENCE` 不变；描述性关系不能替代同日排序证据。
- **换手率 × RV 配对有没有增加价值？** 本次未评价。已有 canonical turnover 字节
  身份已核实，但它不能补上 B Score 的历史行业输入。旧
  `TURNOVER_X_RELATIVE_VOLUME_NEEDS_MORE_EVIDENCE` 不变。
- **综合模型 Top1 / Top3 比原 Score 更好吗？** 未计算，不能声称更好或更差。
- **是否足以支持继续设计新 Ranking？** 尚无证据支持进入基于这次结果的 Ranking
  设计／生产改分；应先解决精确比较基线的证据缺口。
- **是否接着做“防御板块 Wave 广度”？** 不建议作为这次研究的自然下一步立即启动。
  量能／换手的独立排序增量仍未识别，加上 Wave 也不能回答各块贡献。用户仍可另行
  决定独立研究；本阻断不构成整个产品或所有其他研究的 blocker。

## 为什么完整 Score 无法恢复

1. 对冻结 qualified event gzip 做逐行**身份／字段名扫描**，核验完整压缩文件 SHA、
   字节数、实际行数，提取 `(symbol, signal_date, setup_id)`，拒绝重复身份。
   没有 JSON 解码或使用其中的 outcome 值。17,714 条记录均没有 `score_total`、
   `score`、`score_85`、`score_breakdown`、`sector_rank` 或 `sector_chg` 字段。
2. 对冻结 continuous core gzip 做完整字节／解压流核验和相同字段名扫描。
   4,041,140 条记录也均无上述字段。core manifest 的 `core_output_fields` 排除
   Score；`sector_semantics` 明示 `historical_membership_included=false`、
   `neutral_evaluator_sentinel_used=true`、`sector_score_status=UNVERIFIED`。
3. 旧事件虽以 V1 命名，已通过现存 corrected reconstruction impact audit 的
   `ELIGIBILITY_ARTIFACT_EVENT_SET_INVARIANT`、exact shared callable 和事件字节 hash
   对应到 corrected V1_1。这证明资格身份不变，**不能证明完整评分可恢复**。
   原审计也明确 `NOT_APPLICABLE_NUMERIC_PROJECTION_EXCLUDES_SCORE`。
4. 未修改的 `_score_b` 有两个行业分项：`strong_sector` 随当日行业 rank 取
   2/6/10，`sector_linkage` 随当日行业涨幅取 1/5/10。合成反例调用完整 V1_1
   evaluator，在同样 OHLCV、同样 qualified 状态、同样价位下，仅行业输入改变就使
   总分相差 **17 分**。此数字是代码依赖性反例，不是历史收益或历史评分估计。
5. 既有 `docs/phase2e_pit_source_audit.md` 和
   `scripts/historical_validation_layers.py` 早已把 exact V0 历史新浪行业成员及完整
   评分标为 FULL layer 的缺口。冻结回放主动不加载成员表，不等于证明每只股票在 T
   当日确实没有行业映射；不能借 V0 missing-symbol 默认规则把资料缺失变成真实分数。

## 实际样本和分母

| 项目 | 实际核验结果 |
|---|---:|
| qualified B 身份 | 17,714 |
| 至少一个 qualified B 的日期 | 763 |
| 身份日期范围 | 2023-06-30 至 2026-08-28 |
| 冻结 core 评估记录 | 4,041,140 |
| 保存的精确 Score 记录 | 0 |
| 无法建立精确 Score 基线的 qualified 记录 | 17,714 |
| 真正参与排序评价的样本／日期 | 0 / 0 |

| 年份 | qualified 行数 |
|---|---:|
| 2023 | 2,590 |
| 2024 | 6,197 |
| 2025 | 6,697 |
| 2026 | 2,230 |

板块身份计数：Main 11,485；ChiNext 4,416；STAR 1,813。它们来自既有冻结
historical cohort，不扩展生产 Main Board universe。候选数门槛在 **Score／feature／
outcome 完整性筛选之前** 的日期数分别为 Top1（n≥2）745、Top3（n≥3）719、
Top5（n≥5）657；这些不是可用评价日期数。逐日计数在 summary 中。

历史提及的约 17,008 pair-complete 样本，本次在基线停止后**未重建、未认定为实际
可比 cohort**；`pair_complete_rows` 与 `common_complete_case_rows` 为 null。
三个字段的 coverage、系统性缺失、parity、outcome maturity、fold/board/episode
敏感性均未运行，不能以已有研究的分母代替本任务 exact complete-case intersection。
没有生成新的事件级大 artifact；输入均为已有远端可恢复文件。

## 模型总结表

表中“未计算”是 null，不是 0。没有 fit、walk-forward、Top-K、IC 或 bootstrap。

| 模型 | 相对现有 Score 的 Top1 增量 | Top3 增量 | Top5 增量 | Rank IC | 跨年稳定 | 结论 |
|---|---|---|---|---|---|---|
| M0：现有 Score | 未计算 | 未计算 | 未计算 | 未计算 | 未评价 | 精确基线不可恢复 |
| M1：Score + 三项日报量能 | 未计算 | 未计算 | 未计算 | 未计算 | 未评价 | 被基线阻断 |
| M2：Score + turnover/RV/interaction | 未计算 | 未计算 | 未计算 | 未计算 | 未评价 | 被基线阻断 |
| M3：全部组合 | 未计算 | 未计算 | 未计算 | 未计算 | 未评价 | 被基线阻断 |

## Feature-level 表

| 字段 | 预先方向 | 同日 IC／单调性／Top-Bottom | 跨年／coverage | 控制 Score 后增量 | 判断 |
|---|---|---|---|---|---|
| down_volume_share | 低值质量假设 | 未计算 | 未评价 | 未计算 | 未评价有效性 |
| up_down_volume_ratio | 高值质量假设 | 未计算 | 未评价 | 未计算 | 未评价有效性 |
| pullback_volume_decay_ratio | 低值质量假设 | 未计算 | 未评价 | 未计算 | 未评价有效性 |
| RV20_T | 不预设高值更好 | 未计算 | 未评价 | 未计算 | 未评价有效性 |
| turnover_rate_pct | 不预设高值更好 | 未计算 | 未评价 | 未计算 | 未评价有效性 |
| turnover × RV interaction | 不预设正向 | 未计算 | 未评价 | 未计算 | 未评价有效性 |

interaction 事前定义为中心化的同日 percentile-rank 乘积，并保留两个主项。
没有把原始 turnover×RV 当成交易分数。日报仍是观察字段，不参与生产排序。

## 冻结和字节证据

`PRE_OUTCOME_PROTOCOL_COMMIT=24609f3eeea879a58d8f61acfdea0497947b4d56`。
协议：[b_candidate_ranking_volume_turnover_v1_protocol.md](b_candidate_ranking_volume_turnover_v1_protocol.md)。
corrected B spec SHA：`f50c7be101b5c0ffe218cd8daebb4797f4a533c2c27e5c29adab2cf751e2eecd`。

| 输入 | 实际行数／字节 | 文件 SHA-256 | 解压内容流 SHA-256 |
|---|---|---|---|
| qualified events | 17,714 / 2,506,292 | `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9` | `c77a0894ff17427fd1f3540ecb1a4459d9182af649e7e99a9a962bb1bb9671c6` |
| core replay | 4,041,140 / 24,956,498 | `0d23cf54843920f5fdcc05847e4b78c5d605b05c8793f878b6021c85b3ab0c2f` | `882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b` |

事件旧 manifest 的 `content_sha256` 是 JSON array hash，与本表 JSONL 解压流 hash
算法不同；没有冒称二者相等，也没有为了重算旧 array hash 解析 outcome。
canonical turnover 文件核验为 26,322,516 字节，SHA
`589322bcc14cffcc56b5ce96141da7293dca3c7ef4b94bf5ad897cdc44d74193`。
其既有 acquisition manifest 报告 3,938,059 行及 canonical stream SHA
`cfa763eeb067c5162dbda0421539001fd6739a04315dfa5fa7949542f94c7a9c`；本次只独立核实
文件字节和 SHA，没有宣称重新扫描该行数或完整配对。

输入路径、元数据／代码实际 SHA、逐日身份分母、null 统计和边界记录见
`data/validation/b_candidate_ranking_volume_turnover_v1/summary.json`。恢复只依赖此研究
分支与既有 Git-tracked 文件，不依赖本机 daily_k 或未提交 detail artifact。

复现：在仓库根目录运行 `python scripts/b_candidate_ranking_volume_turnover_v1.py`。
脚本验证锁定协议、corrected spec／membership proof、完整文件 SHA 和真实行数；
输入变化会 fail closed，不会绕过缺失 Score 自动生成近似模型。

## 缺什么证据，以及真正的用户决策

需要与每个 qualified identity 绑定且有来源证明的精确历史 `score_total`；或者 exact
T-known V0 新浪行业成员／provider traversal、当日 rank／涨幅等输入，使未修改的
full evaluator 能逐身份精确恢复并验证评分。不能以当前成员回填，也不能用统一
默认行业分、无行业“基础分”或新分数替代。本任务没有授权新的 provider 获取。

该证据由未来的 **Score 基线可恢复性检查** 消费，随后才可运行已冻结的 Ranking
比较。用户可决定是否值得另行解决这个数据缺口，或先保留既有观察并继续真实
prospective 捕获。现有 Formal B 日报、原 Score、观察字段和生产路径均可继续。
本任务未触发新的 Phase、promotion、Wave、防御板块或生产改分。

Prospective sanity：`NOT_RUN_BASELINE_GATE_FAILED`。没有检查其 outcome／成熟样本，
因此不伪称样本足够或不足；MODEL_P 与 MODEL_R 未混用，也没有历史补采。
Final OOS：`SEALED / UNREAD`；未读 `continuous_speed_probe`。新 outcome 值访问=0，
provider calls=0，production semantics change=0，runtime-state 写入=0，production
dispatch=0，merge=0。

## 验证与交付边界

Focused／relevant regressions：40 passed；full pytest：834 passed、2 skipped、10 warnings。
两项 skip 是既有未提交大 capture fixture，不是本研究豁免。`compileall scripts tests`
及 `git diff --check` 通过；两次确定性复现得到相同 summary SHA-256：
`aa034545b0afaf315f51ae4a0acabcf265cf0c0c9a10a7c7426171375b7d0a41`。
summary 为 26,411 字节；没有新增大文件。

唯一研究分支为 `codex/b-candidate-ranking-volume-turnover-v1`，base 为核验后的
live `master`。同一 PR 仅含本研究及 #102 已合并／部署的最小治理纠正；保留旧记录为
historical checkpoint，不建立后续治理 PR 循环。PR／exact-head CI／mergeability
以最终 live GitHub 核对和该 PR 的交付说明为准。停止于数据证据缺口并等待用户决策，
不把阻断审计说成已完成 M0–M3 的排序研究。
