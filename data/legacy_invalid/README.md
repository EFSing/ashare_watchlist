# Legacy / invalid watchlists

`watchlist_20260821.json` is retained here for audit and is intentionally excluded from the production watchlist glob.

Reason: filename date `2026-08-21` does not match payload date `2026-08-20` (`filename/payload date mismatch`). Loading it as a production canonical watchlist must fail fast because the signal/list date is ambiguous; retaining it here ensures this historical payload is not lost while it cannot block production ingest.
