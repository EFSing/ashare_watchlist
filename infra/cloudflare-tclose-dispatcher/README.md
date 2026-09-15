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

The dispatcher is `PREPARED / NOT_ACTIVE` until a user with the required
accounts completes the external setup:

1. Create a fine-grained GitHub PAT restricted to `EFSing/ashare_watchlist`
   with only repository permission `Actions: write`.
2. Store it in the Cloudflare Worker as the secret
   `GITHUB_ACTIONS_DISPATCH_TOKEN` (for example, with
   `wrangler secret put GITHUB_ACTIONS_DISPATCH_TOKEN`).
3. Deploy this Worker and enable its Cron trigger only after this repository
   change is merged and the target workflow accepts the inputs above.

Never paste the token into chat, commit it, put it in `wrangler.toml`, or print
it in a Worker log or test fixture.

Local deterministic tests require only Node.js:

```text
node --test test/dispatcher.test.js
```
