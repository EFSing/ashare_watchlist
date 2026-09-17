import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDispatchRequest,
  dispatchWorkflow,
  targetDateFromScheduledTime,
} from "../src/index.js";

const SCHEDULED_TIME = Date.parse("2026-09-14T09:25:00.000Z");
const TOKEN = "test-token-never-logged";

test("Cron scheduledTime binds the BJT target date", () => {
  assert.equal(targetDateFromScheduledTime(SCHEDULED_TIME), "2026-09-14");
  assert.equal(targetDateFromScheduledTime(Date.parse("2026-09-14T16:25:00Z")), "2026-09-15");
});

test("dispatch payload is explicit and contains no token", async () => {
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
});

test("missing credentials and non-success dispatch fail closed", async () => {
  assert.throws(
    () => buildDispatchRequest(SCHEDULED_TIME, {}),
    /GITHUB_ACTIONS_DISPATCH_TOKEN_REQUIRED/,
  );
  await assert.rejects(
    dispatchWorkflow(SCHEDULED_TIME, { GITHUB_ACTIONS_DISPATCH_TOKEN: TOKEN }, async () => ({ status: 500 })),
    /GITHUB_WORKFLOW_DISPATCH_FAILED_500/,
  );
});
