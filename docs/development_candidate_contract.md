# Development Candidate Contract V1

本文件定义当前 `development candidate` 的受控端到端路径。它是
`research` 层的开发验证合同，不是 production promotion、自动交易授权或
Final OOS 入口。

## Scope and fixed identities

- 输入必须是 `generation_contract.freeze_generation_inputs()` 返回的
  `READY_FOR_STRATEGY_EVALUATION` `GenerationInputManifest`。
- 运行只接受既有的 T close / `Asia/Shanghai` / XSHG T+1 语义；本路径不实现
  historical replay，不读取 Final OOS，不获取或回填当前数据。
- 评估器保持既有 `A_PLATFORM_BREAKOUT_LEGACY_V1` 和其现有阈值；本合同不
  调参、不排序优化、不改变策略 spec。
- Phase 2B 的 `GenerationInputManifest.input_fingerprint` 原样保留，既有 frozen
  语义不在本合同中修改。development candidate 另外计算完整的
  `generation_fingerprint`，并把 input fingerprint、contract/schema version、
  strategy identity、实际参与输出的规范化 display-name mapping、canonical
  `market_env` 和其他输出相关辅助输入纳入 hash payload。
- `input_fingerprint`、`generation_fingerprint`、辅助输入 hash/identity、strategy
  identity、完整 input manifest 和 output SHA 都写入 immutable run manifest。

## Deterministic generation

调用 `DevelopmentCandidateStore.generate(manifest, names, market_env)`：

1. 对 manifest 中的 universe 做稳定的逐标的 evaluator；qualified candidates
   按六位 A 股 code 排序。
2. 使用明确的 display-name mapping 和显式 market environment 组装 canonical
   `watchlist_YYYYMMDD.json` payload；不从当前环境或其他文件静默补字段。
3. 通过 `watchlist_schema.validate_watchlist()` 校验 payload，再用排序 key、
   无空格 JSON 和 UTF-8 newline 生成文件 bytes；相同完整 generation identity
   必须得到相同 output SHA。names 或 `market_env` 的变化必须改变
   `generation_fingerprint`，即使 canonical output bytes 偶然相同也不能冒充同一
   generation。

成功输出的 canonical payload 只包含既有 schema 字段：`date`、`mode`、
`market_env`、`sectors`、`candidates` 和 `strategy_version`。输入 manifest、
策略 identity 和 hash 保存在 sidecar run manifest，不混入 canonical schema。

## Fail-closed and publish rule

以下情况不产生或覆盖 canonical watchlist，并写入显式机器可读状态的 run manifest：

- manifest 不为 READY；
- evaluator failure；
- 缺 display name、非法 numeric/code 或 schema failure；
- publish 时的 filesystem/output write failure；
- 已存在的 canonical output 与此次 output bytes 不同。

evaluator 正常完成但没有任何 `QUALIFIED_LEGACY_BASELINE` candidate 是合法成功：
会生成 schema-valid 的 `candidates=[]` canonical watchlist，run manifest 记录
`status=SUCCESS`、`selection_status=NO_CANDIDATES` 和 `candidate_count=0`，monitor
必须报告 `HEALTHY`，既有 downstream ingest 可以读取并得到零条记录。

`generate()` 只允许首次发布或具有同一完整 generation identity 的幂等重跑；它
永远不静默覆盖既有 canonical output。同一 T 已经存在不同 generation identity
时，即使 output bytes 偶然相同也 fail closed。写失败不会留下合法外观的半成品
canonical，也不会破坏 previous known-good output；可写时会记录
`OUTPUT_WRITE_FAILURE` provenance。

## Versioning, monitoring and rollback

每个 generation 版本保存于由完整 generation fingerprint 无损编码得到的目录
（URL-safe Base64 表示完整 SHA-256，不是截断）；这样不同 generation 不能共享
一个 artifact identity。当前工作区的完整路径仍保持在 Windows 传统路径限制内；
只有附加 failure/conflict key 使用短路径组件：

`data/development_candidate/versions/<generation_fingerprint>/watchlist_YYYYMMDD.json`

运行 provenance 保存于对应的 `runs/.../run_manifest.json`。canonical output 仍
位于既有 `data/watchlist_YYYYMMDD.json` 路径，供既有 ingest/review 读取。

`monitor(T)` 必须同时验证 canonical schema、文件 SHA 和 immutable run
provenance；缺失、非法或无 provenance 的输出分别报告机器可读异常。已知良好
version 可通过 `rollback(T, generation_fingerprint)` 恢复到 canonical path；
rollback 必须同时验证完整 generation provenance 和 output SHA，恢复后再次执行
同一监控校验。

## Development-candidate gate evidence

该 gate 需要固定 development fixtures 覆盖：

- 成功路径：input freeze → evaluation → canonical output → schema ingest；
- 相同输入幂等且 output SHA 不变；
- evaluator failure、缺名字、输出冲突和模拟 write failure 都 fail closed 且不
  污染已有 output；
- zero candidate 成功生成 empty canonical、可重复幂等、monitor healthy 且可被
  downstream ingest 读取；
- names-only、market_env-only 和其他辅助输入变化改变 generation identity；
- monitor 能发现 output 篡改/无 provenance；
- immutable version 能 rollback 并恢复 healthy 状态；
- pytest、compileall、JSON/hash/provenance validation 和 `git diff --check` 全部通过。

通过该 gate 只表示 development path 可在受控输入上重复演示；不改变当前
Delivery Ladder 的正式 promotion 边界，不把 legacy evaluator 写成 production
strategy，也不进入 prospective observation 或 Final OOS。
