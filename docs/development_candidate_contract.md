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
- 每次运行的 `input_fingerprint`、strategy version/spec SHA 和完整 input
  manifest 写入 versioned run manifest；输出文件 SHA 作为 output identity 写入
  同一 immutable run manifest。

## Deterministic generation

调用 `DevelopmentCandidateStore.generate(manifest, names, market_env)`：

1. 对 manifest 中的 universe 做稳定的逐标的 evaluator；qualified candidates
   按六位 A 股 code 排序。
2. 使用明确的 display-name mapping 和显式 market environment 组装 canonical
   `watchlist_YYYYMMDD.json` payload；不从当前环境或其他文件静默补字段。
3. 通过 `watchlist_schema.validate_watchlist()` 校验 payload，再用排序 key、
   无空格 JSON 和 UTF-8 newline 生成文件 bytes；相同 manifest、版本和辅助输入
   必须得到相同 output SHA。

成功输出的 canonical payload 只包含既有 schema 字段：`date`、`mode`、
`market_env`、`sectors`、`candidates` 和 `strategy_version`。输入 manifest、
策略 identity 和 hash 保存在 sidecar run manifest，不混入 canonical schema。

## Fail-closed and publish rule

以下情况不产生或覆盖 canonical watchlist，并写入显式失败 run manifest：

- manifest 不为 READY；
- evaluator failure；
- 缺 display name、非法 numeric/code 或 schema failure；
- 没有任何 `QUALIFIED_LEGACY_BASELINE` candidate；
- 已存在的 canonical output 与此次 output bytes 不同。

`generate()` 只允许首次发布或完全相同 bytes 的幂等重跑；它永远不静默覆盖
既有 canonical output。不同输入/版本若要成为新版本，必须拥有新的
`input_fingerprint` / strategy identity，并经过另一次明确的发布决策。

## Versioning, monitoring and rollback

每个成功版本保存于（磁盘目录使用 input fingerprint 的前 16 位以避免
Windows 路径过长，run manifest 内仍保存并校验完整 fingerprint）：

`data/development_candidate/versions/<strategy_version>/<T>/<input_fingerprint>/watchlist_YYYYMMDD.json`

运行 provenance 保存于对应的 `runs/.../run_manifest.json`。canonical output 仍
位于既有 `data/watchlist_YYYYMMDD.json` 路径，供既有 ingest/review 读取。

`monitor(T)` 必须同时验证 canonical schema、文件 SHA 和 immutable run
provenance；缺失、非法或无 provenance 的输出分别报告机器可读异常。已知良好
version 可通过 `rollback(T, input_fingerprint)` 恢复到 canonical path，恢复后
再次执行同一监控校验。

## Development-candidate gate evidence

该 gate 需要固定 development fixtures 覆盖：

- 成功路径：input freeze → evaluation → canonical output → schema ingest；
- 相同输入幂等且 output SHA 不变；
- 缺数据/无 qualified、缺名字、输出冲突都 fail closed 且不污染已有 output；
- monitor 能发现 output 篡改/无 provenance；
- immutable version 能 rollback 并恢复 healthy 状态；
- pytest、compileall、JSON/hash/provenance validation 和 `git diff --check` 全部通过。

通过该 gate 只表示 development path 可在受控输入上重复演示；不改变当前
Delivery Ladder 的正式 promotion 边界，不把 legacy evaluator 写成 production
strategy，也不进入 prospective observation 或 Final OOS。
