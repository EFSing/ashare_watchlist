# B Turnover x Relative Volume Incremental Diagnostic V1

Labels: `DEVELOPMENT` / `RECONSTRUCTED_RETROSPECTIVE` / `DATE_ANCHORED` / `NO_VINTAGE_PROOF` / `DIAGNOSTIC_ONLY`

## Current stop gate

`TURNOVER_PRIMARY_SOURCE_UNAVAILABLE_AFTER_NO_PROXY_PROBE`

The initial acquisition gate was `TURNOVER_RATE_ACQUISITION_NOT_RESEARCH_READY`.
This task stopped before the pre-outcome protocol commit because the authorized
primary AKShare source could not provide a usable acquisition. The resumable
checkpoint remains available for a later explicitly authorized resume or source
decision. Outcome analysis was not started. During intake, one pre-existing event
record was inspected only to identify the artifact schema; no outcome value was
used in computation, filtering, or conclusion.

## Intake and acquisition

| item | value |
| --- | --- |
| intake master | `873169aeecb9eb12d32e58990677f2478f3081c0` |
| branch | `codex/b-turnover-x-relative-volume-resume-20260905` |
| provider | `akshare 1.18.94`, `ak.stock_zh_a_hist` |
| endpoint | `https://push2his.eastmoney.com/api/qt/stock/kline/get` |
| parameters | `period=daily`, `start_date=20230630`, `end_date=20260828`, `adjust=''` |
| requested symbols | 5386 |
| completed symbols | 0 |
| failed symbols | 11 |
| pending symbols | 5375 |
| persisted raw rows | 0 |
| raw / canonical SHA | `NOT_CREATED` |
| post-merge probe symbols | 000001.sz, 000002.sz, 000006.sz |
| post-merge probe result | 0 success / 15 failed |
| proxy environment | present: ALL_PROXY, HTTPS_PROXY, HTTP_PROXY, NO_PROXY |
| response layer | `FULL_SUBPROCESS_PROXY_BYPASS_FAILED`; HTTP/provider response observed: `False` |

The first bounded failures were consistent `ProxyError` / `RemoteDisconnected`
responses from the Eastmoney endpoint after three attempts per symbol. All temporary
bypass probe results are recorded below without proxy values:

- `existing_environment`: no per-symbol result fields in legacy checkpoint record
- `no_proxy_host_bypass`: 000001.sz: FAILED, rows=None, outer=ConnectionError, underlying=ProtocolError, response=False; 000002.sz: FAILED, rows=None, outer=ConnectionError, underlying=ProtocolError, response=False; 000006.sz: FAILED, rows=None, outer=ConnectionError, underlying=ProtocolError, response=False
- `full_subprocess_proxy_bypass`: 000001.sz: FAILED, rows=None, outer=ConnectionError, underlying=ProtocolError, response=False; 000002.sz: FAILED, rows=None, outer=ConnectionError, underlying=ProtocolError, response=False; 000006.sz: FAILED, rows=None, outer=ConnectionError, underlying=ProtocolError, response=False
- `full_subprocess_proxy_bypass`: 000001.sz: FAILED, rows=None, outer=ConnectionError, underlying=MaxRetryError, response=False; 000002.sz: FAILED, rows=None, outer=ConnectionError, underlying=MaxRetryError, response=False; 000006.sz: FAILED, rows=None, outer=ConnectionError, underlying=MaxRetryError, response=False
- `full_subprocess_proxy_bypass`: 000001.sz: FAILED, rows=None, outer=ConnectionError, underlying=MaxRetryError, response=False; 000002.sz: FAILED, rows=None, outer=ConnectionError, underlying=MaxRetryError, response=False; 000006.sz: FAILED, rows=None, outer=ConnectionError, underlying=MaxRetryError, response=False

Layer distinction: outer exception class `ConnectionError` and HTTP/provider
response observed `False`. A non-`ProxyError` outer class means
the proxy bypass took effect and the remaining failure is a direct connection-layer
failure; a received HTTP/provider response would instead point to a
provider/server-layer issue.

No failed response was promoted into the canonical dataset and no second provider was used.

## Cohort and semantics

The no-outcome cohort reconciliation completed at exact counts: 4,041,140 frozen
evaluations, 573,586 structural first-breakout rows, 17,714 qualified identities,
and 5,386 structural symbols. Turnover coverage is `NOT_EVALUATED` because the
provider gate failed before any symbol was persisted (`0/17,714`, `0/573,586` are
not coverage estimates).

The frozen relative-volume definition is:

`RV20_T = volume_T / mean(volume[T-20:T-1])`

It uses raw `daily_k.volume`, excludes T from the 20-bar baseline, requires 20
valid prior bars and a positive denominator, and does not interpolate missing
bars or use adjusted volume. The semantic source is the corrected B shared
numeric semantics in `scripts/b_breakout_retest_v1_1.py`.

## Boundaries

- B spec, score, threshold, breakout/retest rule, hard gates, Top-N, universe,
  sector/ST semantics and prospective pipeline were unchanged.
- Existing frozen dataset and frozen registry were unchanged.
- Final OOS was not read; C and Phase 2F were not run.
- No pre-outcome protocol commit exists because gate A precedes protocol creation.
- No promotion, freeze, threshold search, parameter sweep, model fitting or
  Drive/upload action occurred.

Resume evidence: `data/validation/b_turnover_x_relative_volume_incremental_v1/acquisition_checkpoint.json`  
Input manifest: `data/validation/b_turnover_x_relative_volume_incremental_v1/input_manifest.json`  
Summary content SHA-256: `f7e2e632eb936d4ed1b6951fbade9e37317d31ff87c76145cbcb6951d94333f1`
