# Daily Report UX V5 implementation map

This map records how the uploaded `daily_close_20260930_ux_prototype_v5.html` is translated
into the live renderer. The prototype is an acceptance reference; values remain dynamic.

| V5 reference behavior | Implementation surface | Data/invariant boundary |
| --- | --- | --- |
| Five first-level areas | `render_daily_close_html.render_html` nav/sections; `c_daily_watchlist.compose_delivery_html` | C is inline under `research-data`; no external page or extra top-level nav |
| Overview-first decision surface | `ReportModel.overview`, `daily_summary`, overview decision grid | counts and next execution date come from canonical model/tracker |
| Compact watchlist volume line | `_volume_summary_line`, `_volume_observations_html` | volume remains observational-only; missing values stay `—`/`样本不足` |
| Changed events visible; long history collapsed | `_daily_review_html`, `_daily_table`, `_active_review_html` | event identity/grouping remains tracker-derived |
| Closed card shows TP/SL and rule return | `_merge_rule_performance_context`, `_daily_table` | return/exit reason are joined from `build_strategy_rule_performance`; daily change is market context only |
| Closed/open performance summaries | `_performance_cards`, `_trade_performance_html` | winner/loser means, payoff, open mark mean use canonical performance rows |
| T+3/T+5/T+10 under Strategy Performance | `_research_panel`, `_next_horizon_dates`, `_trade_performance_html` | fixed-horizon calculation and entry basis are unchanged; detail rows stay collapsed |
| Research/data consolidation | `research-data` section plus inline C adapter | Shadow/C/data-quality/audit are lower-priority details; Formal B remains self-contained |
| Sticky/mobile navigation | existing `.section-nav` CSS and scroll spy | five anchors only; horizontal mobile scroll and scroll margins retained |

No candidate generation, ranking, strategy rule, tracker transition, performance evaluator,
fixed-horizon definition, C selection semantics, Shadow semantics, or artifact identity is changed.
