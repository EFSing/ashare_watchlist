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

## 2026-10-09 incident: read-only reconciliation on 2026-10-10

Classification: P1 product blocker (daily execution and monitoring), with the
existing correctness boundaries kept fail-closed. No strategy/research change.

Live GitHub reads confirmed `master=2551c7f3dc34a3c5bcc88c5c24ac0203e037384d`
and `runtime-state=804e9b05a23b3248de933698c636e65be792b776` at intake. PR
[#100](https://github.com/EFSing/ashare_watchlist/pull/100) and
[#101](https://github.com/EFSing/ashare_watchlist/pull/101) are merged. These
identities are evidence checkpoints, not permanent live-head requirements.

### What is established

- Primary [run 37957620044](https://github.com/EFSing/ashare_watchlist/actions/runs/37957620044)
  was created at `2026-10-09T16:14:05Z` (October 10 00:14:05 BJT), 6h57m after
  the intended 17:17 occurrence. Retry
  [37963035069](https://github.com/EFSing/ashare_watchlist/actions/runs/37963035069)
  was created at `16:59:17Z` (00:59:17 BJT), 6h42m after 18:17. Both job logs
  contain `SCHEDULE_CROSSED_BJT_MIDNIGHT`, `SKIPPED_STALE_SCHEDULE`,
  `production_allowed=false`, and `provider_calls=0`. This is delayed schedule
  creation, not a production job spending seven hours in this workflow's lock.
  The GitHub platform's internal cause remains `UNRESOLVED`.
- Cloudflare account GETs confirmed `ashare-tclose-dispatcher`, handler
  `scheduled`, workers.dev enabled, Cron `25 9 * * 1-5` (last modified September
  17), and a `secret_text` binding named `GITHUB_ACTIONS_DISPATCH_TOKEN`.
  The active deployment is `f1252cf7-2628-4005-9d08-ec671d90550b`, version
  `ef7368ce-9995-4c96-b29b-c9710f4fc88b` at 100%, deployed September 17.
- Downloaded deployed JavaScript equals the live-master Wrangler 4.133.0
  dry-run bundle after newline normalization; LF SHA-256 is
  `61bd414564e3c18a139fed1acdf2da6f746287cfd0d1ec323536d9e9d127c7cd`.
  It already contains `User-Agent`, the expected API URL/headers/body,
  `master`, explicit production inputs, `scheduledTime` date binding, and
  `ctx.waitUntil`. No deployment drift explaining this incident was found.
- Cloudflare GraphQL `workersInvocationsScheduled` is enabled, has 90-day
  retention and a seven-day maximum query window. For this Worker,
  `2026-10-09T09:00:00Z..10:00:00Z` returned no scheduled events or adaptive
  invocations, with no API error. The broader
  `2026-10-09T00:00:00Z..2026-10-10T10:00:00Z` also has no scheduled event.
  The same dataset returns the prior October 8 event at `09:25:48Z`,
  `scheduledDatetime=09:25:40Z`, `cron=25 9 * * 1-5`, `status=success`;
  its adaptive metrics are `requests=1`, `subrequests=1`, `errors=0`.
  This is Cloudflare-side evidence of a missing recorded occurrence, independent
  of GitHub's absence of a dispatch run. It does **not** prove whether Cron
  delivery was missed or invocation telemetry was lost. That distinction
  requires Cloudflare account/platform execution evidence and stays `UNRESOLVED`.
- GitHub's incident-window workflow list contains only two `schedule` runs and
  two manual `workflow_dispatch` runs (18:30 and 20:37 BJT). Context logs identify
  the successful 20:37 run as `trigger_source=manual`. No Cloudflare dispatch
  request, HTTP result, or accepted-but-uncreated GitHub run is established for
  October 9. PAT expiry and actual `Actions: write` remain `UNVERIFIED`; binding
  presence and an earlier successful invocation do not verify current permission.
- Live script settings return `observability=null`, `logpush=false`, and no tail
  consumer; deployed code has no outcome logging. Historical GitHub HTTP status
  and exception detail cannot be recovered from persisted Worker logs. The local
  Wrangler OAuth access token initially returned 403, but its existing refresh
  credential restored read-only access. That local token is separate from the
  Worker's GitHub PAT and is not the production incident's root cause.

### Minimal change and monitoring boundary

This change enables native [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
at sampling rate 1 and emits only date/source/target and safe status records:
`DISPATCH_STARTED`, `DISPATCHED` with HTTP 204, or `DISPATCH_FAILED` with HTTP
status / `GITHUB_WORKFLOW_DISPATCH_NETWORK_ERROR`. Network exceptions are
replaced without their original message, stack or cause. Request headers,
token, response body and arbitrary exception text never enter these logs.
The rejected `waitUntil` promise still records a failed Cron invocation, as
specified by the [scheduled-handler contract](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/).
204 means GitHub accepted the request; the later workflow/context must still
be checked before claiming production completed.

Logs are available on both Free and Paid Workers plans in the current public
documentation. No new storage service or paid resource is introduced. **This
repository change is not deployed.** Native logs do not notify a person and do
not detect a Cron occurrence that never invokes the Worker.

Read-only requests to `alerting/v3/available_alerts` and `alerting/v3/policies`
returned HTTP 403 / code 10000 under the existing Wrangler scope. Thus native
notification eligibility, existing policies and delivery in this account are
`UNVERIFIED`. [Workers Issues](https://developers.cloudflare.com/workers/observability/issues/)
and its [automations](https://developers.cloudflare.com/workers/observability/issues/automations/)
are possible native facilities, but no automation was configured or tested.
They observe actual failures; missing Cron occurrences require an explicitly
supported absence condition. Public feature documentation is not proof of an
active account alert. Do not claim the backup scheduler or alerting is recovered.

### October 9 immutable evidence

Read directly from the pinned runtime-state Git blobs; no rerun or remote write:

| Artifact | SHA-256 |
| --- | --- |
| `daily_checkpoint_20261009.json` | `4089e14b5025c622e7fad82731ecf226fe56a8901f5b801ac277ba17a91f12e1` |
| `watchlist_20261009.json` (8 candidates) | `bdd512321788dbce27f3c719724676b93a4fb8e824adbaa451eed290b7faf37b` |
| `daily_close_20261009.html` | `8f8d71bcf2942664f55e5ab1336a4e033c11affe3c61506c55e2f8dc1f61c251` |
| `daily_delivery_20261009.json` | `2e3e8606d8301e426602cfa57f6665a828da9e51599808d3b99891c1ced79438` |

Checkpoint watchlist/HTML byte lengths and hashes match those Git bytes. Receipt
`report_sha256` matches canonical HTML and records Email/Bark `SUCCESS` at
22:01:01 BJT, with candidate count 8. The temporary B+C attachment SHA is
`4037e7c617e6b3da8d89248b7b115cec97841484842f304e123f0344374e89b8`, matching
the successful job's delivery log and receipt; its temporary bytes are not
persisted in runtime-state and were not regenerated. A read-only local copy of
the canonical state passes `completed_run_status`: `ALREADY_COMPLETED`,
`provider_calls=0`. Existing delivery regression covers zero transport calls
for a successfully delivered receipt. No historical bytes were overwritten.

### Account actions and future acceptance (user decision required)

1. Decide whether to merge this PR and deploy this existing Worker from the
   resulting merged checkout. Run the Node tests and `wrangler deploy --dry-run`
   first. Keep the existing secret, Cron, branch and workflow inputs. Deployment
   is a separate production action; this investigation did not perform it.
2. Obtain Cloudflare's execution explanation for the missing October 9 event
   using the Worker/version/Cron and UTC window above. Use the dashboard's
   **Settings > Trigger Events > View events** and account support if necessary.
   Do not reset the Cron or rotate the PAT merely because GitHub has no run.
3. With account notification access, verify an eligible native failure alert
   (Worker error/Issues occurrence threshold 1) and its destination. Also verify
   whether the account supports a missing-occurrence condition. If unavailable,
   this item requires a user decision; do not add another Worker, KV, queue,
   database or paid service. Any activation/test notification requires separate
   authorization and evidence of actual receipt before calling it effective.
4. Accept on the next normal trading-day 17:25 Cron: original scheduled date,
   persisted start/result log, HTTP 204, matching GitHub `cloudflare-cron`
   context, and either successful production/receipt or same-day completion
   without repeated calculation/delivery. Keep 17:17/18:17 schedules, stale
   midnight skip, XSHG and market-date checks. No historical dispatch for this
   incident is needed or permitted.

Re-query the scoped Cloudflare evidence with the account's existing auth (never
put a credential in the query or output):

```graphql
query {
  viewer {
    accounts(filter: {accountTag: "ACCOUNT_TAG"}) {
      workersInvocationsScheduled(limit: 100, filter: {
        scriptName: "ashare-tclose-dispatcher",
        datetime_geq: "2026-10-09T00:00:00Z",
        datetime_leq: "2026-10-10T10:00:00Z"
      }) { datetime scheduledDatetime cron scriptName status }
    }
  }
}
```
