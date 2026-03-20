/**
 * OpenClaw tool definitions for NCCN Monitor.
 * Each tool delegates to the Python MCP server via McpBridge.
 */
import { Type } from "@sinclair/typebox";
import type { McpBridge } from "./mcp-bridge.js";

interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
}

function textResult(text: string): ToolResult {
  return { content: [{ type: "text", text }] };
}

export function createCheckUpdatesTool(bridge: McpBridge) {
  return {
    name: "nccn_check_updates",
    label: "NCCN Check Updates",
    description:
      "Check all monitored NCCN guidelines for version updates. " +
      "Downloads updated PDFs, extracts update notes, and generates " +
      "AI-powered change summaries. Designed for daily cron scheduling.",
    parameters: Type.Object({}),
    async execute() {
      const result = await bridge.callTool("check_updates");
      return textResult(result);
    },
  };
}

export function createGetStatusTool(bridge: McpBridge) {
  return {
    name: "nccn_get_status",
    label: "NCCN Status",
    description:
      "Get the current health status of the NCCN monitor, " +
      "including last check time and number of tracked guidelines.",
    parameters: Type.Object({}),
    async execute() {
      const result = await bridge.callTool("get_status");
      return textResult(result);
    },
  };
}

export function createListGuidelinesTool(bridge: McpBridge) {
  return {
    name: "nccn_list_guidelines",
    label: "NCCN List Guidelines",
    description:
      "List all 92 NCCN professional guidelines with versions and Chinese names. " +
      "Organized by category (Cancer by Type, Screening, Supportive Care, Specific Populations).",
    parameters: Type.Object({}),
    async execute() {
      const result = await bridge.callTool("list_guidelines");
      return textResult(result);
    },
  };
}

export function createFindGuidelineTool(bridge: McpBridge) {
  return {
    name: "nccn_find_guideline",
    label: "NCCN Find Guideline",
    description:
      "Search NCCN guidelines by name in Chinese or English. " +
      'Supports fuzzy matching. Examples: "肺癌", "GIST", "lymphoma".',
    parameters: Type.Object({
      query: Type.String({
        description: "Search term in Chinese, English, or abbreviation",
      }),
    }),
    async execute(_toolCallId: string, params: { query: string }) {
      const result = await bridge.callTool("find_guideline", { query: params.query });
      return textResult(result);
    },
  };
}

export function createUpdateWatchListTool(bridge: McpBridge) {
  return {
    name: "nccn_update_watch_list",
    label: "NCCN Update Watch List",
    description:
      "Add, remove, or replace guidelines in the monitoring watch list. " +
      "Accepts Chinese or English names with fuzzy matching. " +
      'Examples: action="add", guidelines="肺癌, 胃癌, GIST"',
    parameters: Type.Object({
      action: Type.String({
        description: '"add", "remove", or "set" (replace entire list)',
      }),
      guidelines: Type.String({
        description: "Comma-separated guideline names (Chinese or English)",
      }),
    }),
    async execute(_toolCallId: string, params: { action: string; guidelines: string }) {
      const result = await bridge.callTool("update_watch_list", {
        action: params.action,
        guidelines: params.guidelines,
      });
      return textResult(result);
    },
  };
}

export function createBrowseGuidelinesTool(bridge: McpBridge) {
  return {
    name: "nccn_browse_guidelines",
    label: "NCCN Browse Guidelines",
    description:
      "Browse all NCCN guidelines organized by category with Chinese names. " +
      "Shows which guidelines are currently in the watch list (✅).",
    parameters: Type.Object({}),
    async execute() {
      const result = await bridge.callTool("browse_guidelines");
      return textResult(result);
    },
  };
}
