# Cross-machine development bootstrap

本文件是 fresh-machine / cross-machine continuation 的最小入口。它只描述如何从
GitHub repository、`pyproject.toml` 和 CI 声明恢复 development runtime；不依赖旧
电脑的 branch、venv、未跟踪文件、绝对路径或会话记忆。

## 1. Clone and intake

在新电脑上使用目标工作目录执行：

```powershell
git clone https://github.com/EFSing/ashare_watchlist.git
Set-Location ashare_watchlist
git remote -v
git fetch --all --prune
git branch --show-current
git rev-parse origin/master
git status --short --branch
```

确认 origin 是 `EFSing/ashare_watchlist`。不要用 `git clean`，不要删除未跟踪文件。
继续既有治理任务时，先读取 `AGENTS.md`、`HANDOFF.md`、`docs/CURRENT_STATUS.md`、
`docs/DECISION_LOG.md` 以及任务相关 protocol/governance 文件，再实时核对 active PR、
PR head、exact-head CI 和 working tree。

## 2. Recreate the declared Python runtime

依赖版本唯一以 `pyproject.toml` 为准；CI 以 Python 3.11 安装 `.[test]`。研究/恢复路径
需要 `.[test,research]`，其中 `pyarrow==17.0.0` 是声明的 research pin。不要复用上一台
电脑的 `.venv`，也不要把当前机器已有的包版本写成 repository declaration。

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test,research]"
```

Unix-like shell 使用相同的 `python -m venv .venv` 和
`source .venv/bin/activate`。需要满足 Python `>=3.11,<3.13`，并由 preflight 验证
以下 exact versions：pandas 2.2.3、requests 2.32.3、exchange-calendars 4.13.2、
AkShare 1.18.94、pytest 8.3.5、research extra 的 pyarrow 17.0.0。

## 3. Local preflight

不打印 token/key；只输出版本、status、environment-variable presence boolean、data-root
availability、provider capability、日历/时区状态和 Drive connector status：

```powershell
python scripts/development_preflight.py
python scripts/development_preflight.py --probe-provider
```

`--probe-provider` 只在内存中读取当前 HiThink universe 与 exact Sina definitions/member
responses，输出 counts、name/coverage/duplicate diagnostics；它不构造
`GenerationInputManifest`、`LIVE_OBSERVED` package、watchlist，也不保存 current data。
任何 provider/schema/taxonomy/coverage conflict 都必须保持 fail-closed，不能用当前快照
回填历史 T。

## 4. Provider and Drive capability

HiThink capability 需要当前 shell 中 `HITHINK_FINANCE_API_KEY` 存在；日志只允许记录
`true/false`，禁止打印值。必须重新验证 authenticated metadata/tickers、historical
stock/index K、adjustment-events endpoint；sector 只能使用 AkShare exact
`stock_sector_spot(indicator="新浪行业")` 与 `stock_sector_detail`，不能用 EM/THS/SW
替代。

Google Drive 是 Codex app connector，不由本地 Python preflight 伪造 capability。新电脑上
在当前 Codex app 重新执行：

1. `get_profile`，确认 connector 可用；
2. 读取既有 private backup 的 metadata，确认 MIME/size/ownership，再用
   streamed raw fetch (`download_raw_file=true`, `include_base64=false`) 取得 file reference；
3. 使用一个不属于正式 artifact 的最小临时文本，执行 upload → metadata → raw/readable
   read-back，比较内容/size；随后删除该临时 Drive file 和本机临时文件；
4. 读取正式 artifact 时不得把近似文件、文件名、URL 或本机路径当作 frozen identity。

Connector 成功但 raw file reference 无法物化时，状态应写成
`AVAILABLE_WITH_STREAMED_FILE_REFERENCE`，不得声称已完成 byte-level recovery verification。
正式 `daily_k.parquet` recovery 仍须按 `docs/FROZEN_ARTIFACT_POLICY.md` 的 frozen SHA
执行；本 preflight 不重新下载或替换它。

## 5. Cross-machine handoff gate

只有以下证据都来自当前机器/当前 app session 时，才可写
`CROSS_MACHINE_DEVELOPMENT_HANDOFF = VERIFIED`：

- tracked working tree 与 intended branch/PR 状态已实时核对；
- declared Python/dependency versions 全部 PASS；
- `HITHINK_FINANCE_API_KEY` presence、`ASHARE_DATA_ROOT` availability 和
  `Asia/Shanghai`/XSHG calendar capability 已核对；
- HiThink 与 exact Sina capability probe PASS；
- Google Drive profile、private metadata/raw streamed read-back、临时 upload/read-back
  probe PASS；
- 没有把本机诊断、current snapshot 或失败 attempt 写成 historical/prospective evidence。

缺任一项使用 `PARTIAL_UNVERIFIED` 或更精确 blocker，不用猜测填补。该 handoff 状态不
等于 frozen candidate、strategy promotion 或 Final OOS access；当前项目仍受既有
`FROZEN_CANDIDATE_PREREQUISITES` 决策和 `Final OOS = SEALED / UNREAD` 约束。
