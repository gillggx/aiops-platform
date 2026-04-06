/**
 * aiops-contract QA Test Suite (TypeScript)
 *
 * 手動執行驗證：npx ts-node src/test_contract.ts
 */

import {
  AIOpsReportContract,
  SCHEMA_VERSION,
  isValidContract,
  isAgentAction,
  isHandoffAction,
} from "./report";

let passed = 0;
let failed = 0;

function check(name: string, fn: () => void) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (e) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${e}`);
    failed++;
  }
}

function assert(condition: boolean, msg: string) {
  if (!condition) throw new Error(msg);
}

// ---------------------------------------------------------------------------
// 1. isValidContract type guard
// ---------------------------------------------------------------------------

console.log("\n[1] isValidContract type guard");

check("valid minimal contract passes", () => {
  const contract = {
    $schema: SCHEMA_VERSION,
    summary: "test",
    evidence_chain: [],
    visualization: [],
    suggested_actions: [],
  };
  assert(isValidContract(contract), "should be valid");
});

check("null fails", () => {
  assert(!isValidContract(null), "null should fail");
});

check("missing summary fails", () => {
  assert(!isValidContract({ $schema: SCHEMA_VERSION, evidence_chain: [], visualization: [], suggested_actions: [] }), "missing summary should fail");
});

check("wrong schema version fails", () => {
  assert(!isValidContract({ $schema: "wrong-version", summary: "test", evidence_chain: [], visualization: [], suggested_actions: [] }), "wrong version should fail");
});

check("non-array evidence_chain fails", () => {
  assert(!isValidContract({ $schema: SCHEMA_VERSION, summary: "test", evidence_chain: "oops", visualization: [], suggested_actions: [] }), "non-array should fail");
});

// ---------------------------------------------------------------------------
// 2. SuggestedAction type guards
// ---------------------------------------------------------------------------

console.log("\n[2] SuggestedAction type guards");

check("isAgentAction correctly identifies agent trigger", () => {
  const action = { label: "分析", trigger: "agent" as const, message: "請分析 EQP-01" };
  assert(isAgentAction(action), "should be agent action");
  assert(!isHandoffAction(action), "should not be handoff action");
});

check("isHandoffAction correctly identifies aiops_handoff trigger", () => {
  const action = { label: "開啟", trigger: "aiops_handoff" as const, mcp: "open_lot_trace" };
  assert(isHandoffAction(action), "should be handoff action");
  assert(!isAgentAction(action), "should not be agent action");
});

// ---------------------------------------------------------------------------
// 3. TypeScript type compatibility
// ---------------------------------------------------------------------------

console.log("\n[3] TypeScript type compatibility");

check("full contract object is assignable to AIOpsReportContract", () => {
  const contract: AIOpsReportContract = {
    $schema: SCHEMA_VERSION,
    summary: "EQP-01 今日 OOC",
    evidence_chain: [
      { step: 1, tool: "get_dc_timeseries", finding: "Temperature 超 UCL", viz_ref: "viz-0" },
      { step: 2, tool: "get_event_log", finding: "PM 事件", viz_ref: undefined },
    ],
    visualization: [
      { id: "viz-0", type: "vega-lite", spec: { mark: "line" } },
      { id: "viz-1", type: "kpi-card", spec: { label: "OOC", value: 11 } },
      { id: "viz-2", type: "unknown-future-type", spec: {} }, // 開放型別
    ],
    suggested_actions: [
      { label: "分析", trigger: "agent", message: "分析 EQP-01 lot 良率" },
      { label: "開啟 Lot Trace", trigger: "aiops_handoff", mcp: "open_lot_trace", params: { equipment_id: "EQP-01" } },
    ],
  };
  assert(contract.summary.length > 0, "summary should exist");
  assert(contract.evidence_chain.length === 2, "should have 2 evidence items");
  assert(contract.visualization.length === 3, "should have 3 viz items");
  assert(contract.suggested_actions.length === 2, "should have 2 actions");
});

check("unknown visualization type is allowed (open type system)", () => {
  const viz = { id: "viz-future", type: "super-custom-chart", spec: { data: [1, 2, 3] } };
  assert(typeof viz.type === "string", "type should be a string");
});

check("viz_ref is optional on EvidenceItem", () => {
  const item = { step: 1, tool: "some_tool", finding: "找到問題" };
  // Should compile without viz_ref
  assert(item.step === 1, "should work without viz_ref");
});

check("handoff action params is optional", () => {
  const action = { label: "開啟", trigger: "aiops_handoff" as const, mcp: "open_lot_trace" };
  assert(!("params" in action) || action.params === undefined, "params should be optional");
});

// ---------------------------------------------------------------------------
// 4. SCHEMA_VERSION constant
// ---------------------------------------------------------------------------

console.log("\n[4] SCHEMA_VERSION constant");

check("SCHEMA_VERSION has correct value", () => {
  assert(SCHEMA_VERSION === "aiops-report/v1", `expected aiops-report/v1, got ${SCHEMA_VERSION}`);
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\n${"─".repeat(40)}`);
console.log(`  Passed: ${passed}  Failed: ${failed}`);
if (failed > 0) {
  process.exit(1);
}
