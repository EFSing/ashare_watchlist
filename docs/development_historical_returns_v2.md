# DEVELOPMENT historical returns validation V2

`DEVELOPMENT_HISTORICAL_RETURNS_VALIDATION_V2` 是 DEVELOPMENT partition 的
correctness-primary outcome measurement。它不修改 `A_PLATFORM_BREAKOUT_LEGACY_V1`，
不调参、不 promotion、不读取 final OOS，也没有重跑 769 日 CORE replay。

## Price-path semantics

- signal evaluation 严格只使用 T 及以前的信息；
- entry 为 T+1 XSHG session open；
- future corporate actions 只进入事后 outcome measurement；
- 对每个 horizon，以 target date 为 anchor，按 ex-date 升序对
  `entry_date < ex_date <= target_date` 应用冻结的 affine convention：
  `(price - dividend_per_share + allotment_price*allotment_ratio) /
  (1 + per_share_bonus + allotment_ratio)`；
- 同一 transform 作用于 entry open、路径 high/low 和 target close；
- `ex_date == entry_date` 时 entry open 已是 ex-date price，不重复调整；
- MFE/MAE 使用与 return 完全相同的 adjusted path basis。

原始 raw-unadjusted V1 artifacts 保持不变，只作为历史 diagnostic。V2 manifest 为
[`development_historical_returns_v2_manifest.json`](../data/validation/core_signal_validation_continuous_parts/development_returns_v2/development_historical_returns_v2_manifest.json)，
逐事件结果为
[`development_historical_returns_v2.jsonl.gz`](../data/validation/core_signal_validation_continuous_parts/development_returns_v2/development_historical_returns_v2.jsonl.gz)，
完整 V1→V2 audit（含每个 horizon 最大差异 witnesses）为
[`development_historical_returns_v1_v2_audit.json`](../data/validation/core_signal_validation_continuous_parts/development_returns_v2/development_historical_returns_v1_v2_audit.json)。

## V2 primary results

| Horizon | Available | Positive rate | Expectancy / mean return | Mean MFE | Median MFE | Mean MAE | Median MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1D | 8,441 | 42.4594% | -0.1270% | 2.7624% | 1.7155% | -2.8842% | -2.0787% |
| 3D | 8,423 | 42.6095% | -0.2281% | 5.7148% | 3.2626% | -4.6449% | -3.4074% |
| 5D | 8,414 | 40.6703% | -0.5085% | 7.2670% | 4.1667% | -5.7178% | -4.2606% |
| 10D | 8,375 | 41.3134% | -0.4631% | 9.6346% | 5.7496% | -7.2539% | -5.7876% |

完整年度/月度分层位于 V2 manifest 的 `metrics.<horizon>.by_year/by_month`。
signal frequency 与 concentration 位于 `frequency_and_concentration`：769 个 signal dates、
4,041,140 个 candidate evaluations、22,897 个 A matches、8,463 个 qualified events、
3,697 个 qualified symbols；top-1 share 0.1063%，top-5 share 0.5317%，HHI 0.0003783。

## V1 raw → V2 adjusted correctness audit

| Horizon | Crossing samples | Crossing share | Δ positive rate | Δ mean/expectancy | Δ mean MFE | Δ mean MAE |
|---|---:|---:|---:|---:|---:|---:|
| 1D | 0 | 0.0000% | 0.0000 pp | 0.0000 pp | 0.0000 pp | 0.0000 pp |
| 3D | 48 | 0.5699% | +0.0712 pp | +0.0222 pp | +0.0038 pp | +0.0194 pp |
| 5D | 105 | 1.2479% | +0.1188 pp | +0.0346 pp | +0.0065 pp | +0.0276 pp |
| 10D | 271 | 3.2358% | +0.3224 pp | +0.0864 pp | +0.0224 pp | +0.0607 pp |

delta 定义均为 `adjusted V2 - raw V1`。witness 仅用于 correctness audit，不用于调参、
模型选择或 promotion。

## Provenance and hashes

- retrospective status：`RECONSTRUCTED_RETROSPECTIVE`
- 85 分 sector score：`UNVERIFIED`
- full legacy output：`BLOCKED_HISTORICAL_SINA_MEMBERSHIP`
- final OOS read：`false`
- raw source content SHA-256：`68d10afc4a0e3341c124f8a5e896292faf8ca271ab15cfbb7ac55fe485db8ccb`
- frozen CORE projection SHA-256：`882b8925e787d67d7035de07f91cd3c941b7394661bd32d5d534cc62e3996c1b`
- V1 raw event artifact SHA-256：`4e7fb55430755251cb620a2f48f73c2e9d11b75ca79c7138b7152fb8796b12aa`
- V2 adjusted event artifact SHA-256：`eac51184bd2b51e80d7c2824de1e4b51ff904a1509ae320e85d9b816f6ecd8d1`
- V2 content SHA-256：`ab980bbc2abee4ae0d3e05a486aa6d5bb3940ce41c16a4c63cb04db4212ea9c9`
- V2 manifest SHA-256：`213a76b3da552c4dd68ca949f5a7b80eaee3e14241db825b497c78d875898bab`
- V1→V2 audit content SHA-256：`2df1e6b968d8a01a62866f634844e8a55fc4d7dd231b4443593fb3ff06f50be8`
