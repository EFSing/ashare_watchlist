import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDispatchRequest,
  dispatchWorkflow,
  targetDateFromScheduledTime,
} from "../src/index.js";
import worker from "../src/index.js";

const SCHEDULED_TIME = Date.parse("2026-09-14T09:25:00.000Z");
const TOKEN = "test-token-never-logged";

test("Cron scheduledTime binds the BJT target date", () => {
  assert.equal(targetDateFromScheduledTime(SCHEDULED_TIME), "2026-09-14");
  assert.equal(targetDateFromScheduledTime(Date.parse("2026-09-14T16:25:00Z")), "2026-09-15");
});

test("dispatch payload is explicit and contains no token", async (t) => {
  t.mock.method(console, "info", () => {});
  const request = buildDispatchRequest(SCHEDULED_TIME, {
    GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN,
  });
  const payload = JSON.parse(request.init.body);

  assert.equal(payload.ref, "master");
  assert.deepEqual(payload.inputs, {
    mode: "production",
    as_of_date: "2026-09-14",
    trigger_source: "cloudflare-cron",
  });
  assert.equal(request.url.includes(TOKEN), false);
  assert.equal(request.url, "https://api.github.com/repos/EFSing/ashare_watchlist/actions/workflows/daily_t_close.yml/dispatches");
  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers.Accept, "application/vnd.github+json");
  assert.equal(request.init.headers["Content-Type"], "application/json");
  assert.equal(request.init.headers["X-GitHub-Api-Version"], "2022-11-28");
  assert.equal(request.init.body.includes(TOKEN), false);

  let seen;
  const result = await dispatchWorkflow(SCHEDULED_TIME, { GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN }, async (url, init) => {
    seen = { url, init };
    return { status: 204 };
  });
  assert.equal(result.status, "DISPATCHED");
  assert.equal(seen.init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(seen.init.headers["User-Agent"], "ashare-tclose-dispatcher");
  assert.equal(JSON.parse(seen.init.body).inputs.as_of_date, "2026-09-14");

  // Exercise the actual Cron entry point; its waitUntil promise must settle.
  t.mock.method(globalThis, "fetch", async (url, init) => {
    seen = { url, init };
    return { status: 204 };
  });
  let pending;
  await worker.scheduled({ scheduledTime: SCHEDULED_TIME }, { GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN }, {
    waitUntil: (work) => { pending = work; },
  });
  assert.equal((await pending).status, "DISPATCHED");
  assert.deepEqual(JSON.parse(seen.init.body), payload);
});

test("dispatch outcome logs identify HTTP failures without response or credentials", async (t) => {
  const logs = [];
  t.mock.method(console, "info", (record) => logs.push(record));
  t.mock.method(console, "error", (record) => logs.push(record));
  const env = { GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN };
  await dispatchWorkflow(SCHEDULED_TIME, env, async () => ({ status: 204 }));
  assert.deepEqual(logs.map((r) => r.status), ["DISPATCH_STARTED", "DISPATCHED"]);
  assert.equal(logs[1].http_status, 204);
  assert.equal(logs[1].as_of_date, "2026-09-14");
  assert.equal(logs[1].scheduled_time, "2026-09-14T09:25:00.000Z");
  for (const status of [200, 401, 403, 422, 500]) {
    await assert.rejects(dispatchWorkflow(SCHEDULED_TIME, env, async () => ({
      status,
      text: () => { throw new Error(`response must never be read: ${TOKEN}`); },
    })), new RegExp(`^Error: GITHUB_WORKFLOW_DISPATCH_FAILED_${status}$`));
    assert.equal(logs.at(-1).status, "DISPATCH_FAILED");
    assert.equal(logs.at(-1).http_status, status);
  }
  assert.equal(JSON.stringify(logs).includes(TOKEN), false);
  assert.equal(JSON.stringify(logs).includes("Authorization"), false);
});

test("scheduled waitUntil keeps network failure visible and redacts the original exception", async (t) => {
  const logs = [];
  t.mock.method(console, "info", (record) => logs.push(record));
  t.mock.method(console, "error", (record) => logs.push(record));
  t.mock.method(globalThis, "fetch", async () => { throw new Error(`Authorization: Bearer ${TOKEN}`); });
  let pending;
  await worker.scheduled({ scheduledTime: SCHEDULED_TIME }, { GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN }, {
    waitUntil: (work) => { pending = work; },
  });
  await assert.rejects(pending, (error) => {
    assert.equal(error.message, "GITHUB_WORKFLOW_DISPATCH_NETWORK_ERROR");
    assert.equal(error.stack.includes(TOKEN), false);
    assert.equal(error.cause, undefined);
    return true;
  });
  assert.equal(logs.at(-1).status, "DISPATCH_FAILED");
  assert.equal(logs.at(-1).reason, "GITHUB_WORKFLOW_DISPATCH_NETWORK_ERROR");
  assert.equal(JSON.stringify(logs).includes(TOKEN), false);
});

test("missing credentials and non-success dispatch fail closed", async (t) => {
  t.mock.method(console, "info", () => {});
  t.mock.method(console, "error", () => {});
  assert.throws(
    () => buildDispatchRequest(SCHEDULED_TIME, {}),
    /GITHUB_ACTIONS_DISPATCH_TOKEN_REQUIRED/,
  );
  await assert.rejects(
    dispatchWorkflow(SCHEDULED_TIME, { GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN }, async () => ({ status: 500 })),
    /GITHUB_WORKFLOW_DISPATCH_FAILED_500/,
  );
});
