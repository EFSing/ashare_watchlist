# Daily Report UX V5 + dual-model reporting separation

This map records the selective migration from the accepted PR #97 presentation
reference onto live `origin/master` at `85ce2a970ed3bd70d4b5d3289222f76749caee64`.
It is an implementation map, not a replacement governance snapshot.

## Migration audit

| PR #97 material | Decision on the successor branch | Current implementation |
| --- | --- | --- |
| Five first-level areas: 今日总览, 新名单, 今日复盘, 策略表现, 研究与数据 | Still-valid accepted UX; reimplemented | `render_daily_close_html.py::render_html` |
| Sticky, horizontally scrollable navigation and responsive mobile layout | Still-valid accepted UX; reimplemented | renderer self-contained CSS and scroll spy |
| Historical review/performance/volume/research details collapsed by default | Still-valid accepted UX; reimplemented | `_daily_review_html`, `_trade_performance_html`, `_volume_observations_html`, research/data details |
| C inline under 研究与数据 in the same self-contained HTML | Still-valid delivery UX; reimplemented | `c_daily_watchlist.py::_research_data_details` and `compose_delivery_html` |
| PR #97 HANDOFF/CURRENT_STATUS/DECISION_LOG snapshots and stale SHA/PR state | Stale governance; not migrated | live Git/GitHub intake remains authoritative |
| PR #97 semantic joins that could visually mix rule results into tracker path rows | Not migrated; superseded by this contract | independent MODEL_P and MODEL_R render panels |

PR #97 remains open and is not merged, cherry-picked, or auto-closed. The
successor uses the PR #100 contract audit as its semantic basis.

## Reporting contracts

- `MODEL_P` is labeled **前瞻执行路径** and reads only canonical prospective
  tracker/path counters and statuses. It does not invent a cumulative return,
  PF, expectancy, or return series when no canonical aggregate exists.
- `MODEL_R` is labeled **理论规则模拟** and reads only
  `build_strategy_rule_performance`. Its explanation is:
  “按理论触发价模拟；无首次触发期限；无 T+10 强制退出；不代表前瞻执行收益”。
  Closed metrics expose their `closed n` denominator.
- Fixed T+3/T+5/T+10 nodes remain an independent signal-date research layer;
  they are not used as either model's holding-period or performance aggregate.
- Daily review renders prospective path changes and theoretical same-day rule
  closures in separate panels. The latter uses “理论模拟收益” and explicit
  “理论规则模拟 · 止盈/止损” labels.

## Frozen boundaries

No candidate generation, ranking, score, trigger, stop, target, RR, universe,
T/T+1, tracker state machine, fill semantics, MODEL_P/MODEL_R evaluator,
strategy-performance calculation, C selection semantics, Shadow semantics,
runtime-state, canonical artifact identity, prospective evidence, or Final OOS
state is changed by this implementation.
