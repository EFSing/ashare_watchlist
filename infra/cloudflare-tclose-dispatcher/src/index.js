const BJT_OFFSET_MS = 8 * 60 * 60 * 1000;

export const REPOSITORY = "EFSing/ashare_watchlist";
export const WORKFLOW = "daily_t_close.yml";
export const DISPATCH_REF = "master";
export const TRIGGER_SOURCE = "cloudflare-cron";

function scheduledDate(scheduledTime) {
  if (typeof scheduledTime !== "number" || !Number.isFinite(scheduledTime)) {
    throw new Error("INVALID_CRON_SCHEDULED_TIME");
  }
  const instant = new Date(scheduledTime);
  if (Number.isNaN(instant.getTime())) {
    throw new Error("INVALID_CRON_SCHEDULED_TIME");
  }
  return new Date(instant.getTime() + BJT_OFFSET_MS).toISOString().slice(0, 10);
}

export function targetDateFromScheduledTime(scheduledTime) {
  return scheduledDate(scheduledTime);
}

export function buildDispatchRequest(scheduledTime, env) {
  const token = String(env?.GITHUB_ACTIONS_DISPATCH_TOKEN ?? "").trim();
  if (!token) {
    throw new Error("GITHUB_ACTIONS_DISPATCH_TOKEN_REQUIRED");
  }
  const asOfDate = scheduledDate(scheduledTime);
  return {
    url: `https://api.github.com/repos/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,
    init: {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "ashare-tclose-dispatcher",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: DISPATCH_REF,
        inputs: {
          mode: "production",
          as_of_date: asOfDate,
          trigger_source: TRIGGER_SOURCE,
        },
      }),
    },
  };
}

export async function dispatchWorkflow(scheduledTime, env, fetchImpl = fetch) {
  const request = buildDispatchRequest(scheduledTime, env);
  const response = await fetchImpl(request.url, request.init);
  if (response.status !== 204) {
    throw new Error(`GITHUB_WORKFLOW_DISPATCH_FAILED_${response.status}`);
  }
  return {
    status: "DISPATCHED",
    as_of_date: JSON.parse(request.init.body).inputs.as_of_date,
    trigger_source: TRIGGER_SOURCE,
  };
}

export default {
  async scheduled(controller, env, ctx) {
    const work = dispatchWorkflow(controller.scheduledTime, env);
    if (ctx && typeof ctx.waitUntil === "function") {
      ctx.waitUntil(work);
      return undefined;
    }
    return work;
  },
};
