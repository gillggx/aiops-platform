"use strict";
/**
 * AIOps Report Contract — TypeScript Type Definitions
 *
 * 共同語言：Agent 與 AIOps 之間的溝通標準。
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.SCHEMA_VERSION = void 0;
exports.isAgentAction = isAgentAction;
exports.isHandoffAction = isHandoffAction;
exports.isValidContract = isValidContract;
exports.SCHEMA_VERSION = "aiops-report/v1";
// ---------------------------------------------------------------------------
// Type Guards
// ---------------------------------------------------------------------------
function isAgentAction(action) {
    return action.trigger === "agent";
}
function isHandoffAction(action) {
    return action.trigger === "aiops_handoff";
}
function isValidContract(value) {
    if (typeof value !== "object" || value === null)
        return false;
    const obj = value;
    return (obj["$schema"] === exports.SCHEMA_VERSION &&
        typeof obj["summary"] === "string" &&
        Array.isArray(obj["evidence_chain"]) &&
        Array.isArray(obj["visualization"]) &&
        Array.isArray(obj["suggested_actions"]));
}
//# sourceMappingURL=report.js.map