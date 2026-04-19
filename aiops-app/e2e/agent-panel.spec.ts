/**
 * Phase 3.2 Agent Glass Box — UI smoke tests.
 *
 * These verify panel open/close, prompt input, status rendering, cancel wiring.
 * Real-LLM scenario tests are deferred to manual verification (Spec §15.7 G5)
 * — cost + variance make them unsuitable for CI.
 */

import { test, expect, type APIRequestContext } from "@playwright/test";

const BASE_API = "/api/pipeline-builder";

async function createPipeline(
  request: APIRequestContext,
  payload: Record<string, unknown>
): Promise<{ id: number; name: string }> {
  const res = await request.post(`${BASE_API}/pipelines`, { data: payload });
  expect(res.status()).toBe(201);
  return (await res.json()) as { id: number; name: string };
}

async function deletePipeline(request: APIRequestContext, id: number): Promise<void> {
  await request.post(`${BASE_API}/pipelines/${id}/deprecate`);
  await request.delete(`${BASE_API}/pipelines/${id}`);
}

test.describe("Phase 3.2 — Agent Panel UI", () => {
  test("Ask Agent button opens panel; prompt + examples present", async ({ page, request }) => {
    const rec = await createPipeline(request, {
      name: "E2E Agent Panel Open",
      description: "",
      pipeline_json: { version: "1.0", name: "x", nodes: [], edges: [] },
    });
    await page.goto(`/admin/pipeline-builder/${rec.id}`);

    await expect(page.getByTestId("btn-ask-agent")).toBeVisible();
    await page.getByTestId("btn-ask-agent").click();
    await expect(page.getByTestId("agent-panel")).toBeVisible();
    await expect(page.getByTestId("agent-prompt-input")).toBeVisible();
    // Status badge shows idle
    await expect(page.getByTestId("agent-status")).toHaveText(/idle/i);
    // Start button disabled without prompt
    await expect(page.getByTestId("agent-start-btn")).toBeDisabled();
    // Type something → enabled
    await page.getByTestId("agent-prompt-input").fill("alert on OOC");
    await expect(page.getByTestId("agent-start-btn")).toBeEnabled();

    await deletePipeline(request, rec.id);
  });

  test("Panel close button works", async ({ page, request }) => {
    const rec = await createPipeline(request, {
      name: "E2E Agent Panel Close",
      description: "",
      pipeline_json: { version: "1.0", name: "x", nodes: [], edges: [] },
    });
    await page.goto(`/admin/pipeline-builder/${rec.id}`);
    await page.getByTestId("btn-ask-agent").click();
    await expect(page.getByTestId("agent-panel")).toBeVisible();
    // Close button (× in header)
    await page.locator('[data-testid="agent-panel"] button').first().click();
    await expect(page.getByTestId("agent-panel")).not.toBeVisible();
    await deletePipeline(request, rec.id);
  });

  test("Agent session can be created + cancelled via API (backend wiring)", async ({ request }) => {
    // Create session
    const create = await request.post("/api/agent/build", {
      data: { prompt: "test" },
    });
    expect(create.status()).toBe(201);
    const { session_id } = (await create.json()) as { session_id: string };
    expect(session_id).toMatch(/^[0-9a-f-]{36}$/i);

    // Cancel it (never subscribed → just set cancel flag; session still in registry)
    const cancel = await request.post(`/api/agent/build/${session_id}/cancel`);
    expect(cancel.status()).toBe(200);
    const body = (await cancel.json()) as { status: string };
    expect(body.status).toBe("cancelled");
  });

  test("batch endpoint produces a session with events (live LLM if ANTHROPIC_API_KEY set, else skip)", async ({ request }) => {
    test.skip(!process.env.ANTHROPIC_LIVE, "Set ANTHROPIC_LIVE=1 to run against real Claude");
    test.setTimeout(120_000);
    // A minimal prompt unlikely to fail
    const res = await request.post("/api/agent/build/batch", {
      data: { prompt: "Build a pipeline that fetches EQP-01 process history for last 24 hours and alerts on any OOC event" },
    });
    expect(res.status()).toBe(200);
    const body = (await res.json()) as {
      status: string;
      events: { type: string; data: unknown }[];
    };
    expect(body.status === "finished" || body.status === "failed").toBeTruthy();
    expect(body.events.length).toBeGreaterThan(0);
  });
});
