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
- eligibility stop：预先固定的 `STRATEGY_DEVELOPMENT_ELIGIBILITY_V1` 已尝试一次，
  但 bundled runtime 缺少 `pyarrow` / `fastparquet`，且离线 cache 没有可用 parquet
  reader；在读取 frozen DEVELOPMENT parquet 前 fail closed。因此 event N、四个
  horizon 的 positive/mean/median、MFE/MAE、signal concentration、year robustness
  全部 `NOT_COMPUTED`，没有生成伪造 event artifact。
- decision：`NO_REPRODUCIBLE_STRATEGY_CANDIDATE`，真实 blocker 为
  `P1-ENV-FROZEN-DATA-PARQUET-READER`。这不是 B 的收益 rejection，也不是 C 的
  rejection；不自动启动第二个 candidate。Formal Delivery Ladder 保持
  `development candidate`，不创建 `FROZEN_CANDIDATE_CONTRACT_V1`。
- consequence：提供批准的离线 parquet reader 后，只能按原 B spec、原 frozen inputs
  和同一 fixed protocol 重跑一次，再形成一个允许的最终 candidate decision。若 eligible
  才进入 candidate-bound prospective input package；若 rejected 则停止。
