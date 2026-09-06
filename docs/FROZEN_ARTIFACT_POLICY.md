# FROZEN ARTIFACT POLICY

## Purpose

本 policy 管理 validation、raw、replay、returns 和 checkpoint artifacts 的身份、冻结、备份和跨设备恢复。机器可读明细位于 [`data/governance/frozen_artifacts.json`](../data/governance/frozen_artifacts.json)。

它不授权重新抓取数据、不改变 strategy/protocol、不读取 Final OOS，也不把 development artifact 提升为 production 或 OOS。

## CI provenance and handoff state

- Git/GitHub live state（branch、`HEAD`、PR state、PR head、exact-head CI）一律以实时
  查询为准；`HANDOFF.md` 是跨设备最小恢复入口，不保存这些 last-verified CI/PR 字段。
- 涉及 frozen-artifact recovery / STRICT PATH 的任务，只核验当前任务实际依赖的 PR/CI/
  head；普通开发不默认执行。
- 当前 commit 自己产生的 CI 不回写到同一 commit。若 CI 结果改变，只在下一次实质性
  状态更新时按需回填证据；不为更新 run ID 建立无限 HANDOFF commit 循环。
- 已合并 PR 不得继续标作 active PR；PR 状态由 GitHub live state 维护，不写入 HANDOFF。

## Identity rules

1. `logical_identity`、artifact version、source/provider、semantic content 和 raw bytes 共同确定 artifact 身份。
2. absolute filesystem path、电脑名、工作区路径、检索时间和临时目录永远不得进入 canonical semantic/content hash；路径只能作为 provenance / logical path。
3. 对 raw 文件，byte-level SHA-256 是 content identity；对 manifest / replay / returns，若 producer 提供 canonical semantic hash，registry 同时记录 semantic `content_sha256` 与冻结文件的 `file_sha256`。对 Windows text checkout，若 CRLF 使本机 bytes 不同，另记录 `working_tree_sha256`；Git blob 的 `file_sha256` 才是跨设备可恢复文件身份。
4. 同一 bytes 换电脑后必须产生相同的 file SHA；同一 logical records 在允许的 canonicalization 下必须产生相同的 semantic/content SHA。
5. identity、schema、provider semantics 或 adjustment convention 变化时，新增 version 和 artifact record；不得静默覆盖旧 artifact。

## Recoverability states

每条 registry record 的 `status` 至少按以下状态登记：

- `LOCAL_PRESENT`：当前工作区能读到 exact logical file。
- `HASH_VERIFIED`：实际 bytes 与 registry / producer 声明的 SHA 一致。
- `PERSISTENT_BACKUP_PRESENT`：存在不依赖当前电脑的可恢复副本，例如已核验的 Git remote object 或受控 external backup。
- `RECOVERY_VERIFIED`：从 persistent backup 的 Git object 做过恢复读取并重新核对 bytes/hash；这不等于把 CRLF 工作树 bytes 当成 Git blob bytes。
- `FULLY_RECOVERABLE`：以上四项全部满足。
- `NOT_FULLY_RECOVERABLE`：任一项无法客观确认；不得用“应该有备份”替代证据。

`daily_k.parquet` 当前具有 `LOCAL_PRESENT`、`HASH_VERIFIED`、`PERSISTENT_BACKUP_PRESENT`、`RECOVERY_VERIFIED` 和 `FULLY_RECOVERABLE`；其 recovery evidence 是 Google Drive private-download archive 中唯一且 SHA 严格匹配的 parquet member。ZIP 自身不是 frozen artifact；文件名、绝对路径、URL 和 credentials 不是 identity。

## Freeze and update rules

- frozen_by_commit 必须是实际冻结该 artifact 的 commit；旧 artifact 不因新治理 commit 而改写。
- 新生成的 research artifact 必须先有 manifest、source identity、logical path、file SHA 和 semantic/content SHA（适用时），再加入 registry。
- artifact 与 registry hash 不一致时立即停止，标记 `PROJECT_GOVERNANCE_STATE_CONFLICT` 或 `HASH_MISMATCH`，不得自动修复或重新下载。
- checkpoint 只能与匹配的 raw input content SHA、strategy spec SHA、protocol SHA 和 dataset version 一起 resume；不可跨 identity 拼接。
- interrupted output、resume output、final output 和旧 diagnostic 都保留并分别登记；final output 不覆盖 evidence。
- phase/task 完成、PR ready/merge、artifact freeze、provider semantics 变化或
  research/production status 变化后，按 `AGENTS.md` 的更新节奏处理：HANDOFF 在交接/
  暂停/checkpoint 前更新；CURRENT_STATUS 仅在可独立交付/PR/merge/release/研究阶段/
  稳定流水线状态实质变化时更新；registry 只在实际 artifact/freeze identity 变化时更新。
- secret、API key、token、credential value 永远不得进入 registry、Git、manifest 或日志；只允许记录环境变量名和 presence/empty 等审计摘要。

## New-device recovery procedure

1. clone/fetch 指定 repo 和 commit；先读取 `HANDOFF.md`、本 policy 和 registry；仅当
   当前任务依赖 formal status 或既有决策理由时，再读取 `CURRENT_STATUS.md` /
   `DECISION_LOG.md`。
2. 核对当前 branch 与所需 commit/HEAD，检查 tracked working tree clean；只验证本次
   recovery 实际依赖的 PR/CI（如适用）。
3. 对 registry 中每个 required artifact 检查 logical path、实际 file SHA、semantic/content SHA 和 status。
4. 对 external artifact（当前为 `daily_k.parquet`）从受控 Google Drive private backup 读取 exact parquet member bytes，核对 `61189a4850e2eb157453e28e5375e502e20d214508bbe70ea71066ca3e05e426`；不能核对就停止 replay/resume。
5. 只在所有 required inputs、checkpoint identity 和 producer/runtime dependency 一致时执行 resume；不得重新下载“近似文件”。
6. 将 recovery evidence、时间和 commit/backup reference 回填 registry；如需要新的
   恢复 checkpoint 再更新 HANDOFF，并声明 `HANDOFF_CURRENT_AND_CONSISTENT`。

## Current recovery decision

正式 master 上的 Phase 2E manifests、outputs、checkpoints、probe 和 V1/V2 returns artifacts 已在 registry 中逐项登记。`daily_k.parquet` 已通过 Google Drive private-download archive 的唯一 parquet member 完成 persistent backup / recovery verification，registry 状态为 `FULLY_RECOVERABLE`。local-only Phase 2F diagnostics 仍不在 remote，registry 将其作为 `LOCAL_UNPUBLISHED`、`NOT_FULLY_RECOVERABLE` 单独记录。
