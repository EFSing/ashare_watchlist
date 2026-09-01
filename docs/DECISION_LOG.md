# DECISION LOG

职责：长期记录重要项目决策为什么形成。当前操作接手规则不在此重复，见 [`HANDOFF.md`](../HANDOFF.md)；正式状态见 [`CURRENT_STATUS.md`](CURRENT_STATUS.md)。

## 2026-08-27 — Phase 2A provenance labels

- context：V0 `screen_system.py` 的历史输入、as-of snapshots、raw responses 和 adjustment factors 不完整。
- decision：无法证明的规则与结果使用 `UNKNOWN_ORIGIN` / `NOT_REPRODUCIBLE_WITH_CURRENT_DATA`，不从当前数据补造历史。
- rationale：历史可复现性优先于表面上完整的规则恢复。
- alternatives：按现有代码推测历史数据；把当前结果视作历史重演。
- consequences：部分 legacy 输出保持不可验证，但研究结论不会被伪造为已证实。
- revisit condition：取得可验证的原始 payload、as-of provenance 和调整因子后，另开审计。
- PR / commit：PR #2；`b1c4615`（merged）。

## 2026-08-27 — Phase 2B close-only timing contract

- context：需要定义 generation input 的可知时间和执行时间，避免盘中、same-bar 或当前数据回填。
- decision：只接受 T 日正式收盘后的 close generation；最早执行是 XSHG 下一个交易日 T+1；时区为 `Asia/Shanghai`；日历 pin 为 `exchange-calendars==4.13.2`。
- rationale：T close → T+1 是项目明确的时序边界，真实 provider session close 不能用人工缓冲代替。
- alternatives：premarket generation；same-bar execution；固定 15:05/15:10 代替交易所 session close。
- consequences：盘中输入返回 `SESSION_NOT_CLOSED`；历史 replay 不属于本阶段 generation contract。
- revisit condition：明确批准新的 timing contract 并新增协议版本。
- PR / commit：PR #3；`e587753`（merged）。

## 2026-08-27 — Phase 2C baseline remains research-only

- context：需要恢复 V0 A 平台突破规则并提供可审计的逐标的 evaluation。
- decision：建立 `A_PLATFORM_BREAKOUT_LEGACY_V1` evaluator，保留完整 85 分 breakdown 字段，但不做 TOP N、score cutoff、portfolio selection、scheduler 或 production write。
- rationale：规则恢复不等于预测有效性验证；sector evidence 缺失时必须显式不足，不能静默用中性值。
- alternatives：直接发布 canonical watchlist；把 85 分当成已验证信号；使用 `rank=50/chg=0` 作为缺失 fallback。
- consequences：只产生 research `CandidateEvaluation`；完整 legacy output parity 仍待历史新浪行业 membership。
- revisit condition：完成指定 validation layer、历史 provenance 和显式 promotion decision。
- PR / commit：PR #4；`fc2762e`（merged）。

## 2026-08-28 — Phase 2D point-in-time validation protocol

- context：CORE / historical validation 需要防止 current universe、current sector、future events 和 known-at 违规。
- decision：冻结 `PHASE2D_VALIDATION_PROTOCOL_V1`；semantic SHA 为 `a7db6dc2d6f2dba2555855236fce5580f5e13e192e66991f0f9f63cb0eb9e7ee`；输入必须有 T 日证据、source/version/hash 和 `known_at <= T`。
- rationale：缺证据时 fail-closed，比用近似数据产生不可审计结果更安全。
- alternatives：current constituents backfill；current sector taxonomy 替代历史新浪行业；把 provider forward 结果改名为历史 T-anchor。
- consequences：历史新浪行业 membership 成为 FULL legacy validation 的明确 blocker；核心 signal layer 可以与 sector score layer 分离。
- revisit condition：取得满足 effective-date / T-day semantics 的历史新浪 membership source。
- PR / commit：PR #5；`4ea7b5c`（merged）。

## 2026-08-29 — Phase 2E CORE replay and DEVELOPMENT V2 outcome

- context：在 Phase 2D contract 下验证 CORE signal/level，并在明确授权后测量 DEVELOPMENT outcome。
- decision：完成 769-session continuous CORE replay；以冻结 raw input、T-anchor affine adjustment 和 T+1 open 完成 V2 DEVELOPMENT returns；V2 为 `RECONSTRUCTED_RETROSPECTIVE`，Final OOS 保持 false。
- rationale：先冻结信号 identity，再把 outcome measurement 与 full 85-score parity、production promotion 分离；raw V1 不覆盖，只保留 diagnostic。
- alternatives：读取 Final OOS；把 retrospective data 写成 OOS；用 unadjusted raw outcome 作为 primary；重跑已完成 769 日 replay。
- consequences：CORE 工程结果和 V2 development metrics 可审计，但 FULL legacy 仍因新浪行业 membership blocked，不能 promotion。
- revisit condition：获得历史 sector membership、接受 vintage provenance 边界，并得到新的明确 validation / OOS 授权。
- PR / commit：PR #6；head `edb57a3`，merge `74ccf86dfdea3b9d4b0124fb54346aa429735508`。

## 2026-08-29 — Project handoff governance

- context：跨设备接手需要同时知道 formal master、local unpublished work、artifact identity、backup 和 CI 状态。
- decision：新增 `HANDOFF.md`、`CURRENT_STATUS.md`、本文件、`FROZEN_ARTIFACT_POLICY.md` 和 `data/governance/frozen_artifacts.json`；治理 branch 从 master 独立派生，不吸收 local-only Phase 2F。
- rationale：职责分离可避免把会话摘要、正式状态、决策理由和 artifact inventory 混为一份易漂移文本；local-only artifact 必须显式标注为不可完全恢复。
- alternatives：继续依赖会话记忆；从 Phase 2F local HEAD 建治理 PR；把未验证的外部 backup 写成已存在。
- consequences：新会话有固定冲突 gate；`daily_k.parquet` 在唯一 Google Drive private-download parquet member 完成 exact SHA recovery verification 后更新为 `FULLY_RECOVERABLE`。
- revisit condition：治理 PR 合并后，或发生 phase/PR/CI/artifact/provenance/production-status 变化时更新治理文件。
- PR / commit：PR #7；head `c72ad0498a1ac89966ea39e1e600647f14926ada`，squash merge `16ad543bb39a7d01ed4c484406f1053ca5da0ec2`；merge CI run `33250117945` success。

## 2026-08-29 — daily_k Google Drive recovery verification

- context：`daily_k.parquet` 的本机 bytes 已有 frozen SHA，但此前缺少独立 persistent backup 与 recovery read；Google Drive 下载条目为一个 ZIP archive。
- decision：只读取 Downloads 根目录中实际下载的 `daily_k.parquet-20260829T145838Z-1-001.zip`，对其唯一 member `daily_k.parquet/daily_k.parquet` 的解压字节流做 SHA-256；member size `180203424` bytes，SHA 严格匹配 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`，matching member count 为 1。更新 registry 为 `LOCAL_PRESENT`、`HASH_VERIFIED`、`PERSISTENT_BACKUP_PRESENT`、`RECOVERY_VERIFIED`、`FULLY_RECOVERABLE`，storage type 为 `GOOGLE_DRIVE_PRIVATE`。
- rationale：恢复身份由 frozen parquet bytes 决定；ZIP 自身 hash、文件名、绝对路径、URL、token 和 credentials 都不替代 byte-level identity，也不进入治理 identity。
- alternatives：按名称猜测；把项目目录原始 frozen 文件当作 recovery copy；把 ZIP hash 当作 parquet hash；记录 share URL 或临时 URL。
- consequences：`daily_k.parquet` 的跨设备 persistent-backup / recovery blocker 已解除；不改变 Phase 2E replay、strategy、protocol、Final OOS 或 Phase 2F 边界。
- revisit condition：recovery archive/member 不可读、member 数量变化、member SHA 不再匹配 frozen SHA，或 backup storage semantics 发生变化时，立即降级为 `NOT_FULLY_RECOVERABLE` 并停止 replay/resume。
- PR / commit：PR #8；head `2a1fa22ad474ee91c5946d5d0c1d49db34d691a4`；squash merge `7fe15d8fd2eaf07892a0051321fa6d1dc4352ef9`；PR exact-head correctness runs `33259704118`、`33259700451` success，merge master correctness run `33259819493` success。

## 2026-08-29 — Product charter and agent development contract

- context：Phase 2E research/development evidence 和现有 manual review utility 已存在，但项目需要明确何时能进入每日 observation / paper-use，避免把 deferred research 误当成 release blocker。
- decision：新增 `docs/PRODUCT_CHARTER.md` 定义产品使命、范围、十项 usable gate、P0–P3 blocking severity、Delivery Ladder 和 anti-research-loop rule；新增根目录 `AGENTS.md` 作为所有新 Codex / agent 的强制 intake、分类、边界和 research exit 契约。当前 formal Delivery Ladder 保持为 `research`，不作 production promotion。
- rationale：研究、PIT、provenance、hash 和 validation 服务于可靠的每日系统；没有端到端 deterministic generation、canonical output、explicit failure、monitoring/rollback/versioning 的证据，不能把研究完成写成 usable。
- alternatives：继续以 research 完整度作为唯一 release 条件；把所有未解决研究都列成系统 blocker；从 local-only Phase 2F 分支直接晋级 product candidate。
- consequences：P1 只用于阻止当前 usable milestone；历史新浪 membership 缺失明确限制在 FULL legacy / 85-score validation，不能阻止 CORE research 或 prospective product progression；新的研究必须以 `ADOPT`、`REJECT`、`DEFER` 或 `NEEDS_MORE_EVIDENCE` 结束。
- revisit condition：具体 usable gate、当前 frozen candidate 或真实产品范围发生变化时，更新章程并记录新 decision；不得用新指标本身触发新 Phase。
- PR / commit：PR #9；head `859935fb80a0de585149da16ead8870db11a63a7`；squash merge `7a27484293cbcb791c6b8407949e9e71257e016b`；PR exact-head correctness runs `33260677946`、`33260690327` success，merge master correctness run `33260777592` success。

## 2026-08-29 — Phase 2F local diagnostic exit decision

- context：local-only commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 的 Phase 2F DEVELOPMENT diagnostic 在不修改冻结策略/阈值、不读取 Final OOS 的边界内分析 A_MATCH/QUALIFIED 的失败结构与执行归因。
- decision：`NEEDS_MORE_EVIDENCE`。诊断结果不足以 adopt production threshold、promotion 或自动启动 Research V2；如未来继续，必须先有 materiality justification、预注册比较和明确 exit gate。
- rationale：Phase 2E V2 结果是描述性 `RECONSTRUCTED_RETROSPECTIVE`，Phase 2F 能帮助判断当前候选是否应被拒绝或是否值得一个范围受限的新 protocol，但当前证据没有证明稳定可迁移 edge。
- alternatives：把诊断画像直接改成规则；因为发现分组差异就自动调参；把历史 sector/membership 缺失扩大成整个产品 blocker。
- consequences：Phase 2F 的研究结果保持 local-only / research-only，不改变 formal master、strategy、data、Phase 2E artifacts 或 product delivery；FULL legacy blocker 仍只作用于对应验证层。
- revisit condition：取得足以改变下一 product decision 的 evidence，或明确批准一个新的 preregistered research protocol 后，另记新 decision。
- PR / commit：Phase 2F 没有在本次治理 PR 中发布；本条只记录其退出 decision。

## 2026-08-30 — Live Git State vs Persisted Governance Snapshot

- context：tracked governance 文档曾把静态的 current HEAD / CI 记录写成实时 invariant；治理文档自身的后续 commit 会使该 invariant 永久自引用并制造假冲突。
- decision：live Git/GitHub state 永远在 intake 时实时查询；tracked docs 只保存 `last_verified_master_snapshot`、last-verified CI provenance、历史 milestone identities、正式 Delivery Ladder、Current Objective、blockers/deferred、decisions 和 frozen identities。
- rationale：SHA 前进本身不是治理语义变化；只有 material semantic divergence、required frozen identity/hash mismatch 或非法历史后继才构成 `PROJECT_GOVERNANCE_STATE_CONFLICT`。
- alternatives：每次治理文档变更后把新 HEAD/CI 再写回同一文档；把 snapshot 与 live HEAD 强制相等；把 GitHub API 依赖放入普通 unit tests。
- consequences：snapshot 可以落后 live HEAD，governance-only commit 不会形成无限更新循环；冻结 strategy/protocol/artifact identity 仍保持 exact-match gate，语义产品状态不一致仍 fail closed。
- revisit condition：live intake、正式 Delivery Ladder、Current Objective、frozen identity 或历史 branch/base/merge provenance 的语义发生变化时，更新对应治理职责文件并记录新的 decision。

## 2026-08-30 — Development Candidate Gate V1

- context：PR #12 在既有 Phase 2B close-only input contract 和既有 legacy evaluator
  wiring 上建立了受控 development-candidate path；代码审计和 development gate
  evidence 已完成，随后 PR #12 已 squash merge。
- decision：`ADOPT` development candidate product path V1。PR #12 已 squash merge，正式
  Delivery Ladder 已从 `research` 晋级为 `development candidate`；对象是产品路径，
  不是 `A_PLATFORM_BREAKOUT_LEGACY_V1` strategy 本身。
- rationale：该路径已经证明 deterministic generation → schema-valid canonical
  watchlist → explicit fail-closed handling → immutable provenance/versioning →
  monitoring/rollback 的受控闭环，具备继续核验 frozen-candidate prerequisites 的
  产品基础。
- gate evidence：正常 evaluator 运行即使 `candidate_count=0` 也成功生成
  `candidates=[]` canonical watchlist，重复运行保持 output SHA 幂等，downstream
  ingest 可读取且 monitor 为 `HEALTHY`；evaluator failure 与 zero-candidate 明确
  区分；`generation_fingerprint` 覆盖 Phase 2B `input_fingerprint`、contract/schema
  version、strategy identity、实际参与输出的规范化 names、canonical `market_env`
  和其他输出相关辅助输入；同一 T 的不同 generation identity fail closed；write
  failure、rollback、完整 provenance monitor 均有回归证据；focused/full tests、
  compileall、JSON/hash/provenance、diff 和 secret checks 通过，并以 exact-head CI
  复核。
- known limitations：输入仍限于 READY frozen generation manifest 和受控
  development fixtures；历史新浪 industry membership / effective-date evidence
  缺失仍只限制 FULL legacy validation；retrospective data 的 vintage provenance
  限制仍存在。该 gate 不证明参数有效性、收益 edge、跨数据源迁移性或运营上线安全。
- non-equivalence：本 decision 不构成 frozen candidate，不构成 production strategy，
  不构成参数选择或调参，不构成 Final OOS 结论，也不授权自动交易、promotion 或
  自动启动 Phase 2F。
- consequences：正式 Delivery Ladder 已为 `development candidate`；后续必须先核验
  frozen-candidate prerequisites，明确必须解决的 P0/P1，并在 prerequisites PASS
  时定义 frozen candidate contract/gate。不得把 product-ladder 晋级改写为 legacy
  strategy promotion。
- revisit condition：frozen-candidate prerequisites、产品范围、required
  provenance 或正式 promotion decision 发生变化时，另记 decision；任何新的
  research question 必须有独立 exit decision，不能由本 gate 自动触发新 Phase。
- PR / commit：PR #12；最终 merge 状态和 exact-head CI 属于 live Git/GitHub
  provenance，不在本条写入会自引用的 current HEAD。

## 2026-08-30 — Frozen-candidate prerequisites audit V1

- context：PR #12 已将产品管线正式带入 `development candidate`；下一 decision
  不是默认把既有 legacy baseline freeze，而是审计当前是否存在真实、获批准且有
  足够 development evidence 的 strategy candidate。
- research question：当前项目是否已经具备一个可以进入 frozen candidate gate 的
  真实 strategy candidate？停止条件是完成 product infrastructure、strategy
  eligibility、data/provenance 和最小 operational prerequisite 核验后形成唯一
  decision；不以新增指标或优化方向扩大研究。
- decision：`FROZEN_CANDIDATE_BLOCKED`，具体原因为
  `FROZEN_CANDIDATE_BLOCKED_NO_APPROVED_STRATEGY_CANDIDATE`。
- rationale：当前没有正式 nominated/approved strategy candidate；
  `A_PLATFORM_BREAKOUT_LEGACY_V1` 仍是 research-only wiring witness。虽有可复核
  spec identity、T close/T+1、deterministic generation、canonical output、
  fail-closed、monitoring/rollback 和 artifact recovery 的 development/path
  evidence，但现有 CORE 与 `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` evidence
  不足以支持“值得进入 prospective/frozen candidate”的资格判断；sector score
  仍 `UNVERIFIED`，FULL legacy 仍受历史新浪 membership 限制，Phase 2F 仍是
  `NEEDS_MORE_EVIDENCE`。
- P0/P1：本轮没有新的全局 P0 correctness/safety defect。frozen gate 的 P1 是
  (1) strategy nomination/eligibility decision 缺失，(2) 固定 development evidence
  的候选资格 decision 缺失，(3) candidate-bound prospective input/provenance
  package 缺失。历史新浪 membership 只作为 FULL legacy retrospective scope 的
  blocker，不升级为全局 blocker。
- consequences：不把 A baseline 晋级为 frozen candidate，不创建或伪造
  `FROZEN_CANDIDATE_CONTRACT_V1`，不启动 Phase 2F、不调参、不读 Final OOS、不
  promotion。scheduler、broker、自动交易和复杂告警不属于当前 frozen gate 的最小
  前置条件。
- next decision：取得上述最小 nomination/eligibility 与 candidate-bound
  prospective evidence 后，回到 `FROZEN_CANDIDATE_PREREQUISITES` decision point；
  缺少这些证据时仍保持 BLOCKED。完整审计见
  [`frozen_candidate_prerequisites_audit.md`](frozen_candidate_prerequisites_audit.md)。

## 2026-08-30 — Strategy Candidate Nomination V1

- context：PR #13 已以 expected head `0f5629765ef0eebbae0c6981f2d7ccafab7f7e35`
  squash merge；其 master merge CI 已成功。当前任务只允许确定下一只值得进入
  development eligibility 验证的 candidate，不允许调参、Phase 2F 或 Final OOS。
- A decision：`REJECT_A_PLATFORM_BREAKOUT_LEGACY_V1_AS_FROZEN_CANDIDATE`。冻结的
  Phase 2E V2 primary evidence 为 1D 42.4594% / -0.1270%，3D 42.6095% / -0.2281%，
  5D 40.6703% / -0.5085%，10D 41.3134% / -0.4631%；scope 是 DEVELOPMENT /
  RECONSTRUCTED_RETROSPECTIVE，不是 Final OOS。A 仍是 research baseline / regression
  witness；该 decision 不外推到平台突破思想、未来 A 版本或 Research V2。
- inventory：只审计已有固定 V0 provenance 的 A、B breakout-retest、C
  main-trend-retest；D / generic old history types 因 exact mapping/provenance 不完整
  排除。未引入其他项目规则。
- nomination：在读取 B/C development returns 之前，按 exact provenance、未知来源、
  frozen/recoverable data、无 backfill、Phase 2B contract、implementation/inference
  complexity 的 lexicographic rule，唯一提名
  `NOMINATE_B_BREAKOUT_RETEST_LEGACY_V1_FOR_DEVELOPMENT_ELIGIBILITY`。B lower
  complexity；若仍相同，B→C 是固定 research tie-break，不是预测排名。C 不做 returns
  evaluation。
- reconstruction：B exact V0 reconstruction PASS；V0 source commit
  `c8406c393c0b135eafb0aec763576ae869fddcff`，source SHA
  `6cac746123e315199cbeeb1a612868ef77b50af6c7c64b0d80eb387ae1d19f9`，canonical
  semantic spec SHA `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`；
  focused parity/hash/edge/decision tests `7 passed`。
- eligibility environment stop：此前的环境阻塞状态统一为
  `CANDIDATE_ELIGIBILITY_BLOCKED_ENVIRONMENT`，原因是
  `B_ELIGIBILITY_NOT_EXECUTED_MISSING_PARQUET_READER`。这不是 B performance
  rejection、no-rule conclusion 或 C rejection。
- fixed replay：安装 exact-pinned `pyarrow==17.0.0` 后，以 Python 3.12.13、
  pandas 2.2.3 只运行一次相同的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1`；首次
  parquet read 前 registry required artifacts 13/13、daily_k exact SHA
  `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`、raw source、
  checkpoint、CORE projection/manifest identity 均通过，frozen bytes 未修改。
- frozen protocol：`ELIGIBILITY_RULE_FROZEN_BEFORE_B_RETURNS_READ = true`；
  minimum N=30、primary=10D、10D positive rate >=50%、mean >0、median >0、
  robust years >=3（每年 >=10 events）、positive robust-year means >=2。结果未改动
  threshold。
- B result：Event N `17,714`；available N 1D/3D/5D/10D 为 `17,689` / `17,635` /
  `17,602` / `17,558`；10D positive rate / mean / median 为 `51.6403%` /
  `+1.4603%` / `+0.3226%`；4 个 robust years 中 2 个 mean 为正，fixed gates 全部
  PASS。
- decision：`CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`。这是 B candidate
  eligibility 的 `ADOPT`，不是 production strategy promotion、parameter validation
  或 Final OOS 结论。event artifact SHA 为
  `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`；eligibility
  original manifest file SHA 为 `a0c5a195ea991a471fd56eb80534d03091d6bd308f6c6f263476737380a28c9a`；
  该文件后续仅因 provenance correctness 修复而 deterministic rematerialized，当前
  file SHA 由 2026-08-31 closure entry 记录。
- prospective contract：定义
  `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`，绑定 B strategy/spec
  SHA、T close/T+1、universe、sector semantics、names、market_env、provider/version、
  calendar、availability/fail-closed、recovery 和 generation/output identity；不伪造
  尚未发生的 live instance。
- rejudged prerequisites：`FROZEN_CANDIDATE_BLOCKED`；唯一 P1 为
  `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，等待首个真实 candidate-bound
  `LIVE_OBSERVED` T-close package 并验证 `known_at <= T`。不测试 C、不启动 Phase 2F、
  不调参、不读 Final OOS、不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## 2026-08-31 — PR #14 governance conflict and provenance correctness closure

- context：Sol 独立审计发现 active PR body 仍保留旧的 parquet-reader stop /
  `NO_REPRODUCIBLE_STRATEGY_CANDIDATE` 叙述，与 HEAD 上已完成的 B eligibility
  及 HANDOFF/CURRENT_STATUS/本日志冲突；同时 eligibility manifest provenance
  serialization 允许 CLI absolute path 影响 manifest identity。
- decision：只修 active PR metadata、eligibility provenance canonicalization 和
  formal decision-artifact registry；B fixed rule/spec/thresholds、observed metrics、
  event set 与 decision 全部保持不变。
- provenance：不同 filesystem root 及 relative/absolute invocation 的 regression
  证明 canonical identity 相同；path 只保存稳定 repo-relative logical provenance，
  `Path.resolve()` 的 machine-specific result 不进入 semantic/content/manifest hash。
- deterministic verification：同一冻结 raw/CORE inputs 与既有固定 protocol 完成一次
  reproducibility verification；event count `17,714`、event file SHA
  `8940a4a346ac6911ba669f84a9ceba7ef878b0ed0ce51edf673439b52aa056b9`、event semantic
  SHA `a16e48dfbe8a93f64d8bf1bad6e00d3eaf32c10fd60eed09dc5574247b8119bc`、metrics
  identity、all gates 和 `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES` 与修复前完全
  一致。manifest 只做 deterministic provenance rematerialization；new manifest
  semantic SHA 为 `f79ec9baa494f2f0256843c2540988bd25c94269ed9a1fd4ada228759bd8e0a2`，
  payload content SHA 为 `e754787836b28316430278372ab2d84817091d4608da394f9207f695a4c27aee`，
  file SHA 为 `5e0a557c1930de7b4f182f09f43b45c0c11b19b2d7c992bf9e7fa7e6cc6de048`。
- registry：两个 B artifacts 均登记为 `required_for_decision=true`、
  `required_for_replay=false`，并验证 registry 的实际 file/content SHA 与提交文件
  完全匹配；不记录 absolute path、URL、token 或 secret。
- governance outcome：Formal Delivery Ladder 仍为 `development candidate`，不创建
  `FROZEN_CANDIDATE_CONTRACT_V1`；唯一当前 P1 仍为
  `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`；不 promotion、不测试 C、不启动
  Phase 2F、不调参、不读 Final OOS。
- revisit condition：只有首个真实 candidate-bound `LIVE_OBSERVED` T-close input
  instance 到来，或正式 strategy/protocol/data/provenance identity 改变时，才重新
  进入对应 decision gate。

## 2026-08-31 — Live acquisition adapter readiness

- task classification：本轮属于 product blocker 审计，并包含 correctness fail-closed
  风险；不是新的 strategy research、参数选择、Phase 2F 或 Final OOS 任务。
- audit finding：当前 master 原有 Phase 2B `GenerationInputManifest` 只验证已构造
  的输入，没有 AkShare universe/sector adapter，也没有 Tencent qfq stock/index K
  acquisition path，因此确认存在 `P1-FC-LIVE-ACQUISITION-ADAPTER_MISSING`。
- implementation decision：在从当前 master 派生的单一分支中补齐最小
  `scripts/live_acquisition.py`，绑定 B strategy/spec identity，严格执行 T close /
  T+1、`LIVE_OBSERVED`、provider/version、names、market_env、coverage/conflict/
  freshness、fingerprint、immutable persistence 和 fail-closed contract；新增
  AkShare `1.18.94` 明确 pin。B strategy/spec/threshold、冻结数据和既有 research
  artifacts 均未修改。
- readiness evidence：mock/fixture tests 覆盖 pre-close、wrong date、provider
  unavailable、空/不完整 universe、sector member/rank/name failures、stale/missing
  quote/Kline、future bar、T+1、deterministic fingerprint/bytes、no backfill 和
  incomplete manifest 不产生 output。实际 runtime probe 读取 AkShare `1.18.94`；
  pyarrow 保持 `25.0.1`，没有执行 research optional pin 的降级。
- boundary：这是 implementation/runtime readiness，不是 prospective evidence；本轮
  不调用 live provider，不生成或冻结正式 `LIVE_OBSERVED` T-close package，不生成
  canonical watchlist。Formal Delivery Ladder 仍为 `development candidate`，唯一
  formal prerequisite blocker 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`。
- revisit condition：Sol review/CI 后合并才可将 adapter 视为 master path；正式收盘后
  才能运行真实 T 日采集，并按 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`
  审计首个 package。

## 2026-08-31 — First prospective T-close acquisition attempt

- task classification：本轮属于 product blocker 审计，并包含 provider-induced
  correctness fail-closed 风险；不是新的 strategy research、参数选择、Phase 2F 或
  Final OOS 任务。
- baseline：PR #15 已按 expected head
  `f0528744d9fe0add78436a543b15afa12c2e229e` squash merge，merge SHA 为
  `f1fed4608210aa175ac268189a8d7f032b0b88e0`；master correctness run
  `33367655723` success，head 精确匹配 merge SHA。
- timing：T=`2026-08-31` 被 exchange-calendars/XSHG 判定为真实 session，官方
  session close 为 `2026-08-31T15:00:00+08:00`，T+1 为 `2026-09-01`。正式调用使用
  实际运行时 `observed_at_bjt=2026-08-31T15:21:18.969554+08:00`，满足 close 后
  precondition。
- provider result：正式调用 `acquire_live_generation_inputs()` 在 AkShare sector
  membership acquisition 阶段发生 `ConnectionError`，adapter 映射为
  `PROVIDER_FAILURE` 并停止。已做首次调用加两次有限重试；另外在切换到 merge
  master 后做了一次 formal master-baseline attempt，结果相同。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。本次没有
  READY `GenerationInputManifest`，没有 `LIVE_OBSERVED` package，没有 universe/
  sector/quote/Kline completeness evidence，没有 input/generation fingerprint，
  没有 package content/file SHA 或 logical path。
- fail-closed evidence：T/session-close/date gate PASS；AkShare runtime capability
  已可读取且版本为 `1.18.94`；sector membership provider failure STOP；Tencent
  quote、stock/index Kline、market_env、manifest READY、persistence、exact-byte
  read-back、recovery 和 frozen-candidate audit downstream checks 均
  `NOT_REACHED`，不得写成 PASS。
- persistence/recovery：`ASHARE_DATA_ROOT` 本次显式指向仓库 `data` 根；由于没有
  完整 package，`data/prospective_inputs/` 未创建，没有 local package、persistent
  backup 或 recovery identity 可登记。没有修改 `data/governance/frozen_artifacts.json`。
- hash audit note：对既有、非 replay-required 的 `phase2e.hithink_probe` record
  进行 JSON/hash audit 时发现，当前 exact bytes SHA 为 registered `file_sha256`
  `395601b...`，但预存 `working_tree_sha256` 为 `af694b...`。这是本轮之前的
  provenance discrepancy；未自动修复、未重新下载、未改变 frozen identity，也没有把
  该 probe 用作本次 live evidence。后续若要修复，需单独记录明确治理 decision。
- consequences：Formal Delivery Ladder 保持 `development candidate`；B 的
  `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`、strategy/spec/threshold、冻结数据、
  existing artifacts 和 Final OOS sealed 状态不变；不创建
  `FROZEN_CANDIDATE_CONTRACT_V1`，不 promotion、不测试 C、不启动 Phase 2F、不调参、
  不读 Final OOS。
- revisit condition：仅在 provider 可用后的新真实 XSHG T-close session 重新 acquisition；
  不把 2026-08-31 的失败回填为成功，不跳过 sector coverage，不猜 membership，且
  必须重新满足完整 `CANDIDATE_BOUND_PROSPECTIVE_INPUT_PROVENANCE_CONTRACT_V1`。

## 2026-08-31 — PR #16 same-day retry semantics and AkShare bounded retry

- context：Sol review 发现 active PR #16 草稿把同日 retry 错写成只能等待下一个
  T-close session；真实 AkShare acquisition 还显示三个 provider-read API 没有
  adapter-level transient retry，sector membership 的单次 `ConnectionError` 会终止整次采集。
- task classification：product blocker hardening，并包含 provider-induced correctness
  fail-closed 风险；不启动新的 strategy、Phase、promotion、参数选择或 Final OOS。
- decision：`ADOPT` 最小 retry hardening；同一 BJT 日期 T 在正式收盘后允许新的独立
  live acquisition attempt。每次 attempt 使用新的真实 `observed_at`、重新获取全部
  required input、不复用 failed attempt 的 partial response；第一次失败保留，跨到
  下一 BJT 日期后禁止用当前 live provider 数据构造此前 T 的 package。
- implementation：AkShare `stock_info_a_code_name`、`stock_board_industry_name_em`
  和每个 `stock_board_industry_cons_em` read 只对 transient network/connection
  exception 做固定最多 3 次 retry，backoff bounded 为 `0.25s`、`0.50s`。schema、
  empty、duplicate、name/sector conflict、coverage 等 response semantics 在 retry
  边界外一次性校验；exhaustion 映射 `PROVIDER_FAILURE` 且不产生 formal output。
- identity：attempt/backoff 仅为 process diagnostics，不进入 canonical input /
  generation/package content identity 或成功 provenance；不改变 provider source、
  B strategy/spec/threshold、Phase 2B contract、冻结 artifact 或 Final OOS。
- scale audit：完整 universe 的固定执行模型是 1 次 universe read、1 次 definitions
  read、每个 definition 1 次逻辑 member read、`ceil(N / 50)` 个 Tencent quote batch、
  N 个 stock Kline request 加 1 个 index request。它是 execution diagnostics，不是筛选
  规则；不得缩 universe 或跳过股票。首次正式失败在 sector membership，后续实际计数
  保持 `NOT_REACHED`。
- evidence：新增回归覆盖 universe/definitions transient recovery、persistent
  3-attempt failure、sector-member recovery、semantic/schema no-retry、no-output 和
  retry-independent identity；full pytest、compile、JSON/hash、diff 和 secret checks
  必须在 PR #16 exact head 上通过。
- consequences：Formal Delivery Ladder 仍为 `development candidate`；唯一 frozen
  prerequisite P1 仍为 `P1-FC-FIRST-PROSPECTIVE-T-CLOSE-INPUT-INSTANCE`，同日窗口内
  可在 clean merged master 重新 acquisition；不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。

## 2026-08-31 — PR #16 merged and same-day retry remained blocked

- context：PR #16 的 bounded AkShare retry hardening 已在 exact-head CI 全绿后合并；
  按 Phase 2B 同日 close contract，在北京时间仍为 `2026-08-31` 时于 clean merged
  master 上重新发起独立 acquisition。
- provenance：PR #16 final head 为
  `f604dc39c681ee63c075cc0fea5cef367d6296f5`，squash merge SHA 为
  `c9d5e50be833bf5bb1c3c83c0a2fa1b3e83979c1`；merge master correctness run
  `33372781495` success，head 精确匹配 merge SHA。新的 attempt 使用真实
  `observed_at_bjt=2026-08-31T16:27:36.974203+08:00`，没有复用第一次 attempt。
- result：AkShare `stock_info_a_code_name` 在固定 `3/3` attempts 后以
  `ConnectionError` fail closed，provider/API 为 AkShare/universe，acquisition elapsed
  `0.782s`；sector code/name 不适用，completed sector calls `0`，sector definition
  count `NOT_REACHED`，universe symbol count `0`，Tencent quote batch、stock/index
  Kline、market_env、manifest 和 persistence 均 `NOT_REACHED`。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_PROVIDER_FAILURE`。两次失败均保留；
  没有 READY manifest、`LIVE_OBSERVED` package、fingerprint、content/file SHA、
  logical path、partial formal evidence 或 recovery copy。没有把失败改写为成功，也
  没有 current-data backfill；本任务不自动无限重试。
- consequences：Formal Delivery Ladder 仍为 `development candidate`；B eligibility、
  B strategy/spec/threshold、Phase 2B semantics、frozen artifact identities、Final OOS
  sealed state 和既有 `phase2e.hithink_probe` non-blocking metadata debt 均未改变。
  不创建 `FROZEN_CANDIDATE_CONTRACT_V1`，不 promotion、不测试 C、不启动 Phase 2F、不调参。

## 2026-08-31 — P0 live sector taxonomy mismatch correction

- task classification：`correctness blocker` P0，并包含阻止当前 candidate-bound live
  path 使用的 product/provider architecture blocker；不启动新的 strategy research。
- research question and materiality：当前 authenticated HiThink Financial-API 是否能
  支持 universe/names 与 stock/index K primary，以及 AkShare 当前是否仍能提供 B 冻结的
  exact Sina industry membership；答案决定能否修正 live adapter，而不修改 B spec。停止
  条件是 endpoint capability、返回 schema/taxonomy 和 fail-closed boundary 均被核实。
- finding：merged master 的 `stock_board_industry_name_em` /
  `stock_board_industry_cons_em` 是东方财富 industry taxonomy，违反 B exact legacy
  provenance（AkShare `stock_sector_spot` / `stock_sector_detail`，`新浪行业`）。两次
  `2026-08-31` attempt 都在 package 构造前失败，故没有 contaminated prospective
  artifact，也不改写既有失败事实。
- capability evidence（非 prospective evidence）：HiThink authenticated metadata/
  ticker、snapshot、stock historical K、index historical K、adjustment-events 当前均
  返回 HTTP 200 / `code=0` 与结构化字段；AkShare `1.18.94` 的 exact Sina spot/detail
  当前可调用，live probe 返回 49 个行业及首个 detail 的 19 个成员。没有保存 raw
  payload、没有构造 manifest/package、没有进行收益研究或 Final OOS 读取。
- decision：`ADOPT` 最小 provider correction。HiThink metadata primary universe/name；
  HiThink `adjust=forward` stock K 和 unadjusted index K primary；exact Sina API 是唯
  一 sector source；Tencent quotes 保留既有字段语义；Tencent Kline 仅作为明确版本化
  `LIVE_MARKET_DATA_FAILOVER_POLICY_V1` / `TENCENT_QFQ_FALLBACK_V1` transport fallback。
  EM/THS/SW 代替、taxonomy/schema/date/coverage failure 和非 transient provider failure
  均 fail closed。HiThink index 使用 `PROVIDER_RAW_SNAPSHOT`，不伪装成 qfq。
- invariants：B strategy/spec/threshold、spec SHA
  `5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`、T-close/T+1、
  no-current-data-backfill、no-future-bar 和 existing frozen artifacts 均不变。
- verdict：`HITHINK_LIVE_PRIMARY = SUPPORTED`；
  `EXACT_SINA_SECTOR_SOURCE = AVAILABLE`。
- next decision：单一 correction PR #17 已创建并保持 `OPEN`，head=
  `869eade1eaf48e2d470175e234e83c99fd2168ac`；pull-request correctness run
  `33379014737` 与 push correctness run `33378978157` 均在该 exact head 成功，当前
  `CLEAN`/`MERGEABLE`。停在 Sol review；review/merge 后是否运行新的 prospective
  T-close acquisition，必须由用户在新的合法 close session 明确授权；本任务不自动
  选择新的 T、不生成 package、不启动 C/Phase 2F、不调参、不读 Final OOS、不 merge。

## 2026-08-31 — PR #17 adjustment boundary and tradable-universe scope closure

- task classification：`correctness blocker`（stock raw Kline 可被通用 validator 接受）
  加 `product blocker` hardening（live universe scope 未进入稳定 identity）；不是新的
  strategy research、参数选择、Phase 2F 或 Final OOS 任务。
- research question / materiality：不新增研究问题；修正直接决定 live input 是否能
  fail closed，以及未来 BJ 纳入是否会被识别为不同产品范围。停止条件是 stock/index
  provider-adjustment 配对、scope identity、provenance 和回归测试全部明确。
- decision：`ADOPT`。`KlineManifest` 只接受 `PROVIDER_QFQ_SNAPSHOT`；`IndexManifest`
  只接受 HiThink Financial-API + `PROVIDER_RAW_SNAPSHOT`，或 Tencent +
  `PROVIDER_QFQ_SNAPSHOT` 的 explicit fallback；其他 adjustment/provider 配对 reject。
- decision：`ADOPT` `TRADABLE_UNIVERSE_SCOPE_V1 = SH_SZ_A_SHARE_ONLY`。SH/SZ A 股
  included，BJ explicitly excluded，BJ absence 不属于 incomplete coverage；scope/version
  进入 UniverseManifest content hash、GenerationInput input fingerprint、live
  generation identity、provider metadata 和 prospective provenance。
- invariants：B strategy、B spec SHA、B threshold、既有 frozen historical artifacts、
  Final OOS sealed 状态和 T-close/T+1 semantics 均不变。既有 B development eligibility
  不重跑、不改写；若历史输入包含 BJ，只记录
  `KNOWN_DEVELOPMENT_VS_PROSPECTIVE_UNIVERSE_SCOPE_DIFFERENCE`，不自动推翻既有 decision。
- consequence：PR #17 仍是现有 correction PR 的最后 hardening；合并前不获取真实
  prospective input，不生成 package/watchlist，不启动 C/Phase 2F，不调参，不读 Final OOS。

## 2026-08-31 — First post-merge LIVE_OBSERVED acquisition attempt

- context：PR #17 已按 actual expected head `ef48d192c7709a7194348369c689070c665da2b4`
  squash merge，merge SHA 为 `91e9ec76e3f4ea8ffaa1badeb759c1d2a7f5f73b`；merge master
  exact-head correctness run `33399324692` 成功。随后在同一合法 XSHG T-close window
  用 fresh `observed_at_bjt=2026-08-31T22:01:28.307161+08:00` 执行正式 acquisition。
- contract：T=`2026-08-31`，T+1=`2026-09-01`，`LIVE_OBSERVED`，scope/version 为
  `SH_SZ_A_SHARE_ONLY` / `TRADABLE_UNIVERSE_SCOPE_V1`；universe/names 使用 HiThink
  primary，sector 使用 AkShare 1.18.94 exact `新浪行业` spot/detail；没有复用此前失败
  attempt、capability probe 或 partial response。
- finding：在 exact Sina sector/member display-name consistency 阶段发现
  `INPUT_CONFLICT: display-name conflict for 000012: universe/member`；quotes、Kline、
  market_env、manifest、package、persistence 和 Drive recovery 均未执行。
- decision：`FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`；这是 required
  name/provenance consistency conflict 的 fail-closed blocker，不是 provider
  connectivity failure；不得用猜测映射、current data 或 taxonomy substitution 继续。
- consequences：没有 `READY_FOR_STRATEGY_EVALUATION`、package/content/file SHA、byte
  length、local logical path 或 Drive persistent recovery reference；没有 canonical
  watchlist、prospective returns、C、Phase 2F、调参、paper/live trading 或 promotion。
  不向 frozen artifact registry 添加伪 artifact；attempt evidence 另存为
  `data/governance/prospective_input_attempt_evidence_20260831.json`，并明确
  `not_a_frozen_artifact=true`。
- invariants：B strategy/spec/threshold、`5bbeb345ebd8883149138d2f29f8606f919949ae285aa2839fa337921dfc7112`、
  exact Sina taxonomy、SH/SZ scope/version、T-close/T+1、provider/fallback provenance、
  monitoring/rollback、Final OOS sealed/unread 均不变。
- next decision：在 provider/name consistency conflict 解决且新的合法 T-close window
  到来后，重新获取全部 required inputs；在此之前保持该 input blocker，不构造 package，不创建
  `FROZEN_CANDIDATE_CONTRACT_V1`。

## 2026-08-31 — PR #18 display-name consistency conflict and minimal correctness fix

- task classification：`correctness blocker`；这是输入/provider-data consistency
  conflict，不是 provider connectivity failure，也不是新的 strategy research、Phase、
  参数选择、Final OOS 或 promotion 任务。
- historical correction：2026-08-31T22:01:28 的正式 attempt 保留
  `INPUT_CONFLICT`、stage=`exact_sina_sector/display_name_consistency`、symbol=`000012`
  和原始 detail；其 final decision 改为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_INPUT_CONFLICT`，分类为
  `INPUT_PROVIDER_DATA_CONSISTENCY_CONFLICT`。原始 attempt 未保存 raw names 或执行
  计数，故不以 current diagnostic 回填这些字段，也不把失败改写为成功。
- current capability diagnostic：在不读取 returns、Final OOS 或策略结果的前提下，
  重新读取完整当前 `SH_SZ_A_SHARE_ONLY` universe 与 exact Sina sector/member source。
  HiThink universe 为 5,220 symbols，Sina definitions 为 49，完成 49 次 member call，
  common symbols 为 2,539；2,492 个 raw names 一致，47 个 raw names 不一致。`000012`
  的 raw universe name 为 `南玻Ａ`（`U+5357 U+73BB U+FF21`），raw sector name 为
  `南 玻Ａ`（`U+5357 U+0020 U+73BB U+FF21`）。完整清单见
  [`current_capability_name_diagnostic_20260831.md`](current_capability_name_diagnostic_20260831.md)。
- decision：`ADOPT` 统一、预注册、语义安全的名称比较规则
  `DISPLAY_NAME_NORMALIZATION_NFKC_TRIM_EXPLICIT_ZERO_WIDTH_V1`：只移除显式零宽
  格式字符、执行 Unicode NFKC、trim 首尾 whitespace；raw universe/sector values
  继续保留，symbol 仍是 security identity，normalization version 进入 generation
  identity/provenance。`REJECT` 删除 ST/*ST、A/B 标记、内部 whitespace、listing suffix、
  fuzzy/edit-distance、拼音或按 symbol 忽略实质分歧。
- result：该规则消除 0 个当前 raw-name mismatch；47 个冲突 normalization 后仍不一致，
  因而当前真实 blocker 为
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SUBSTANTIVE_NAME_CONFLICT`。adapter 继续
  fail closed，并将 symbol、两边 raw/normalized names、universe count、sector
  definition count 和 completed member calls 暴露为非 secret structured diagnostics。
  该修复不产生 partial formal package。
- invariants/next decision：B strategy/spec/threshold、`SH_SZ_A_SHARE_ONLY`、exact Sina
  taxonomy、T-close/T+1、Final OOS sealed/unread、C exclusion、Phase 2F exclusion 和
  no tuning 均不变。2026-09-01 白天只完成修复与 review；PR #18 完成 Sol review 并合并
  到 clean master，且 XSHG 正式收盘后，才可运行新的 `T=2026-09-01` `LIVE_OBSERVED`
  acquisition；不构造 T=`2026-08-31` package。

## 2026-09-01 — B dependency audit, symbol-authoritative names, and sector gate

- classification：`correctness blocker` + `product blocker`；任务只处理首个
  candidate-bound prospective input 的可执行依赖与 cross-machine development path，
  不启动新的 strategy research、参数选择、Phase 2F、C、Final OOS 或 promotion。
- research question：B 的 display name、sector membership、`sector_name`、
  `sector_rank`、`sector_chg` 是否真的进入 executable/output semantics；当前 exact
  Sina provider 能否在不缩 universe、不替换 taxonomy、不回填历史的情况下满足它们。
- materiality：该结论决定 PR #18 的 name correction 是否安全，以及 B 是否仍需完整
  sector evidence 才能进入 frozen-candidate gate。停止条件是 source call graph、
  field/gate matrix、provider coverage、duplicate 和 ambiguity 已明确；不因当前快照
  发现新的分组或指标而扩大研究。
- inputs：`scripts/b_breakout_retest.py`、`scripts/a_platform_breakout.py`、B
  nomination/eligibility/prospective contract、PR #18 changes，以及 fresh `.venv`
  的 read-only HiThink/AkShare probe。当前 payload 只在内存中读取，结果记录在
  `docs/b_dependency_audit_20260901.md`，明确标记为
  `LOCAL_CURRENT_SNAPSHOT_DIAGNOSTIC_NOT_PROSPECTIVE_EVIDENCE`。
- source finding：exact six-digit symbol 是 security/trading identity；display name
  不参与 symbol join、candidate selection、hard gates、trigger、stop、target、RR、
  score、final status 或 B canonical identity。`sector_rank`/`sector_chg` 分别进入
  B 85-score 的 `strong_sector`/`sector_linkage`，缺 sector evidence 返回
  `INSUFFICIENT_DATA`，故 sector 仍是 `EXECUTABLE_REQUIRED`，不是 generic baggage。
- decision：`ADOPT`
  `DISPLAY_NAME_CONSISTENCY_POLICY_V2_SYMBOL_AUTHORITATIVE`。raw HiThink/Sina names
  独立保留，registered normalization 只做 diagnostic；不 fuzzy reconcile、不生成
  alias、不用名字 join/filter；policy/diagnostics 进入 active V2 contract、provenance
  和 generation identity。V1 historical evidence 不改写。
- current provider evidence：fresh preflight exact versions 全部 PASS；HiThink current
  scope 为 5,221 symbols，exact Sina 为 49 definitions/49 member calls；sector audit
  报告 2,682 个 universe symbols 缺 membership、439 个 sector symbols 在 universe 外、
  47 个 raw-name mismatch（normalization resolve 0），以及 `000587`、`000602`、
  `002217`、`002617`、`600714` 五个 distinct multi-sector memberships；当前无 exact
  duplicate symbol。该事实随 provider snapshot 变化，不回填 2026-08-31。
- decision：`NEEDS_MORE_EVIDENCE` for a future legitimate T-close exact-Sina response
  that is complete and unambiguous for the full scope. Exact duplicate same-sector rows
  may be deterministically deduplicated only with raw row/count provenance; distinct
  sector memberships remain fail closed, with no silent drop/substitution/backfill。
- current gate：
  `FROZEN_CANDIDATE_PREREQUISITES_BLOCKED_SECTOR_MEMBERSHIP_AMBIGUITY`, with an
  independent exact-Sina coverage failure. PR #18 remains unmerged; no T=`2026-08-31`
  backfill and no T=`2026-09-01` acquisition/package is created in this task. Formal
  Delivery Ladder remains `development candidate`; B eligibility remains
  `CANDIDATE_ELIGIBLE_FOR_FROZEN_PREREQUISITES`; Final OOS remains `SEALED / UNREAD`。
