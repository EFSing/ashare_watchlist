# T+1 execution review

Formal execution review uses EXECUTION_MODEL_DAILY_OHLC_T1_V1.

- A signal dated T can only enter on the next XSHG session.
- Entry fills at the session open when open >= trigger; otherwise the first
  intraday trigger fill is trigger.
- The entry session never produces an exit. Stop/target touches on that bar
  are retained as audit flags.
- Exit evaluation starts at sellable_from, the next XSHG session after the
  actual entry date. Opening gaps fill at the open; a same-bar stop and target
  touch remains AMBIGUOUS_SAME_BAR.
- T+10 remains a signal-date horizon. A T+10 entry is deferred to the next
  sellable session; an untriggered signal is EXPIRED_UNTRIGGERED.

Realized returns and R are gross, before fees and slippage. Fixed-horizon
T+3/T+5/T+10 snapshots are research observations, not realized trade P&L.
reconcile_t1_execution.py rebuilds derived execution state from canonical
watchlist identity, stored observations, and the XSHG calendar only; it never
fetches historical quotes.
