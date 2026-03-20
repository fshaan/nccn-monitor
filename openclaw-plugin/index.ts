/**
 * NCCN Monitor — OpenClaw Plugin
 *
 * Wraps the Python MCP server as a native OpenClaw plugin.
 * Tools appear directly in OpenClaw's tool list (like feishu_chat, etc.)
 * without needing mcporter as middleware.
 */
import { join } from "node:path";
import { existsSync } from "node:fs";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { McpBridge } from "./src/mcp-bridge.js";
import {
  createCheckUpdatesTool,
  createGetStatusTool,
  createListGuidelinesTool,
  createFindGuidelineTool,
  createUpdateWatchListTool,
  createBrowseGuidelinesTool,
} from "./src/tools.js";

// Default paths — can be overridden via plugin config
const DEFAULT_PROJECT_DIR = join(process.env.HOME ?? "", "Workspace/Claude/nccn_watcher");
const DEFAULT_PYTHON_PATH = join(DEFAULT_PROJECT_DIR, ".venv/bin/python");

const nccnMonitorPlugin = {
  config: {
    defaults: {
      enabled: true,
      pythonPath: DEFAULT_PYTHON_PATH,
      projectDir: DEFAULT_PROJECT_DIR,
    },
    parse(raw: Record<string, unknown>) {
      return {
        enabled: raw.enabled !== false,
        pythonPath: (raw.pythonPath as string) || DEFAULT_PYTHON_PATH,
        projectDir: (raw.projectDir as string) || DEFAULT_PROJECT_DIR,
      };
    },
  },

  register(api: OpenClawPluginApi) {
    const config = api.getConfig() as {
      enabled: boolean;
      pythonPath: string;
      projectDir: string;
    };

    if (!config.enabled) {
      api.logger.info("[nccn-monitor] Plugin disabled");
      return;
    }

    // Validate paths
    if (!existsSync(config.pythonPath)) {
      api.logger.warn(
        `[nccn-monitor] Python not found at ${config.pythonPath}. ` +
          `Run: cd ${config.projectDir} && uv venv .venv && uv pip install -e .`,
      );
      return;
    }

    const bridge = new McpBridge(config.pythonPath, config.projectDir);

    // Register all 6 tools
    api.registerTool(() => createCheckUpdatesTool(bridge));
    api.registerTool(() => createGetStatusTool(bridge));
    api.registerTool(() => createListGuidelinesTool(bridge));
    api.registerTool(() => createFindGuidelineTool(bridge));
    api.registerTool(() => createUpdateWatchListTool(bridge));
    api.registerTool(() => createBrowseGuidelinesTool(bridge));

    api.logger.info(
      `[nccn-monitor] Registered 6 tools (python=${config.pythonPath}, project=${config.projectDir})`,
    );
  },
};

export default nccnMonitorPlugin;
