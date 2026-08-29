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
- PR / commit：本次治理 PR / merge 信息在 exact-head CI 和合并完成后回填。

## 2026-08-29 — Phase 2F local diagnostic exit decision

- context：local-only commit `3eeb5df9f7cf4ef5c30b3380b323f26f2491f873` 的 Phase 2F DEVELOPMENT diagnostic 在不修改冻结策略/阈值、不读取 Final OOS 的边界内分析 A_MATCH/QUALIFIED 的失败结构与执行归因。
- decision：`NEEDS_MORE_EVIDENCE`。诊断结果不足以 adopt production threshold、promotion 或自动启动 Research V2；如未来继续，必须先有 materiality justification、预注册比较和明确 exit gate。
- rationale：Phase 2E V2 结果是描述性 `RECONSTRUCTED_RETROSPECTIVE`，Phase 2F 能帮助判断当前候选是否应被拒绝或是否值得一个范围受限的新 protocol，但当前证据没有证明稳定可迁移 edge。
- alternatives：把诊断画像直接改成规则；因为发现分组差异就自动调参；把历史 sector/membership 缺失扩大成整个产品 blocker。
- consequences：Phase 2F 的研究结果保持 local-only / research-only，不改变 formal master、strategy、data、Phase 2E artifacts 或 product delivery；FULL legacy blocker 仍只作用于对应验证层。
- revisit condition：取得足以改变下一 product decision 的 evidence，或明确批准一个新的 preregistered research protocol 后，另记新 decision。
- PR / commit：Phase 2F 没有在本次治理 PR 中发布；本条只记录其退出 decision。
