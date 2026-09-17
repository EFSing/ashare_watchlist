# Cloudflare T-close dispatcher

This is a deliberately small secondary scheduler. Its only production action is
an authenticated GitHub `workflow_dispatch` call to `daily_t_close.yml`; it does
not call market-data providers, persist data, calculate signals, or access the
`runtime-state` branch.

The Cron trigger is `25 9 * * 1-5` UTC (`17:25` BJT). The worker derives
`as_of_date` from Cron's `scheduledTime` in BJT, so a delayed HTTP completion
cannot move the target to another date. It dispatches `master` with
`mode=production`, `trigger_source=cloudflare-cron`, and the explicit date.

## Secret and activation boundary

Repository preparation does not establish account-side activation. Check the
live deployment, Cron and secret binding before describing this dispatcher as
active or inactive. A user with the required accounts completes external setup:

1. Create a fine-grained GitHub PAT restricted to `EFSing/ashare_watchlist`
   with only repository permission `Actions: write`.
2. Store it in the Cloudflare Worker as the secret
   `GITHUB_ACTIONS_DISPATCH_TOKEN` (for example, with
   `wrangler secret put GITHUB_ACTIONS_DISPATCH_TOKEN`).
3. Deploy this Worker and enable its Cron trigger only after this repository
   change is merged and the target workflow accepts the inputs above.

Never paste the token into chat, commit it, put it in `wrangler.toml`, or print
it in a Worker log or test fixture.

`workers_dev = true` explicitly preserves the existing workers.dev deployment
model. This Worker has only a scheduled handler: its workers.dev URL is not an
HTTP production-dispatch endpoint. The GitHub request includes an explicit
`User-Agent`, required by GitHub's REST API.

Duplicate wake-ups use the existing workflow's non-canceling production
concurrency group and restored runtime-state `ALREADY_COMPLETED` check before
provider calls. A missing primary follows the same production path. Repeated
Cron events create no Cloudflare-side state. GitHub's XSHG preflight remains
the holiday authority, and live acquisition rejects a wrong observation date;
the explicit Cron date must never be replaced with the runner's current date.

Account reconciliation on 2026-09-17 found the Worker deployed, workers.dev
enabled, Cron `25 9 * * 1-5` present, and the required secret binding configured.
The deployed source lacked `User-Agent`; historical Cron failures and the PAT's
actual permission/expiry remain `UNRESOLVED` without execution evidence. Secret
presence alone does not verify `Actions: write`. No production dispatch or
Cloudflare account mutation was performed during reconciliation.

Local deterministic tests require only Node.js:

```text
node --test test/dispatcher.test.js
```
