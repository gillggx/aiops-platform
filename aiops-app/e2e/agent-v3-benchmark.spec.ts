/**
 * V3 Agent benchmark — Section 1 (V2 20 cases) + Section 2 Agent-operable cases.
 *
 * Gated by ANTHROPIC_LIVE=1 so CI without credentials skips it. When run,
 * sends each prompt to the Agent /build/batch endpoint and asserts that the
 * resulting pipeline uses the expected new blocks (coarse sanity check).
 *
 * This is a smoke benchmark, not exhaustive — real validation happens in
 * docs/TEST_CASES_V3.md review during manual sign-off.
 */
import { test, expect, request as pwRequest } from "@playwright/test";

const LIVE = process.env.ANTHROPIC_LIVE === "1";

test.describe("V3 Agent benchmark (ANTHROPIC_LIVE gated)", () => {
  test.skip(!LIVE, "ANTHROPIC_LIVE not set — skipping real-LLM benchmark");

  interface Case {
    id: string;
    prompt: string;
    /** Block names that the resulting pipeline SHOULD contain (coarse sanity check). */
    expectedBlocks: string[];
  }

  // Representative 10 Agent TC (subset — full list in docs/TEST_CASES_V3.md).
  const cases: Case[] = [
    { id: "TC01", prompt: "EQP-01 的 APC etch_time_offset 趨勢", expectedBlocks: ["block_process_history", "block_chart"] },
    { id: "TC04", prompt: "比較 EQP-01 和 EQP-02 的 SPC xbar 趨勢", expectedBlocks: ["block_process_history", "block_chart"] },
    { id: "TC06", prompt: "目前有哪些機台", expectedBlocks: ["block_mcp_call"] },
    { id: "TC13", prompt: "哪台機台最需要關注 (依 OOC 次數)", expectedBlocks: ["block_groupby_agg", "block_sort"] },
    { id: "TC16", prompt: "EQP-07 xbar + APC rf_power_bias 同張圖", expectedBlocks: ["block_chart"] },
    { id: "TC19", prompt: "STEP_007 SPC 5 chart type vs APC rf_power_bias 線性回歸 R²", expectedBlocks: ["block_unpivot", "block_linear_regression"] },
    { id: "TC20", prompt: "STEP_001 xbar 常態分布 histogram + σ 線", expectedBlocks: ["block_histogram", "block_chart"] },
    { id: "TCα5", prompt: "EQP-01 xbar vs APC rf_power_bias 線性回歸 + 95% CI", expectedBlocks: ["block_linear_regression"] },
    { id: "TCβ6", prompt: "監控 EQP-01 5 張 SPC chart WECO，任一觸發發一封 HIGH 告警", expectedBlocks: ["block_weco_rules", "block_any_trigger", "block_alert"] },
    { id: "TCγ1", prompt: "多 APC 參數 correlation heatmap", expectedBlocks: ["block_correlation", "block_chart"] },
  ];

  for (const c of cases) {
    test(`${c.id} — ${c.prompt.slice(0, 40)}`, async ({ baseURL }) => {
      const ctx = await pwRequest.newContext({ baseURL });
      const resp = await ctx.post("/api/agent/build/batch", {
        data: { prompt: c.prompt },
        timeout: 60_000,
      });
      expect(resp.ok(), `batch failed with ${resp.status()}`).toBeTruthy();
      const body = await resp.json();
      expect(body.status).toBe("finished");

      const nodes = body.pipeline_json?.nodes ?? [];
      const nodeBlockIds = new Set<string>(nodes.map((n: { block_id: string }) => n.block_id));

      for (const expected of c.expectedBlocks) {
        expect(nodeBlockIds, `${c.id}: pipeline missing '${expected}' (got ${[...nodeBlockIds].join(",")})`).toContain(expected);
      }
      await ctx.dispose();
    });
  }
});
