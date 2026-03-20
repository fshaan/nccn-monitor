/**
 * MCP Bridge — spawns the Python MCP server as a subprocess and
 * communicates via stdin/stdout using the MCP JSON-RPC protocol.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createInterface, type Interface } from "node:readline";

interface McpRequest {
  jsonrpc: "2.0";
  id: string;
  method: string;
  params?: Record<string, unknown>;
}

interface McpResponse {
  jsonrpc: "2.0";
  id: string;
  result?: unknown;
  error?: { code: number; message: string };
}

export class McpBridge {
  private process: ChildProcess | null = null;
  private readline: Interface | null = null;
  private pending = new Map<string, {
    resolve: (value: unknown) => void;
    reject: (reason: Error) => void;
  }>();
  private initialized = false;

  constructor(
    private pythonPath: string,
    private projectDir: string,
  ) {}

  async start(): Promise<void> {
    if (this.process) return;

    this.process = spawn(this.pythonPath, ["-m", "nccn_monitor.server"], {
      cwd: this.projectDir,
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env },
    });

    this.readline = createInterface({ input: this.process.stdout! });
    this.readline.on("line", (line) => this.handleLine(line));

    this.process.stderr?.on("data", (data) => {
      // Server logs go to stderr — ignore silently
    });

    this.process.on("exit", (code) => {
      this.process = null;
      this.readline = null;
      // Reject all pending requests
      for (const [id, { reject }] of this.pending) {
        reject(new Error(`MCP server exited with code ${code}`));
      }
      this.pending.clear();
    });

    // Initialize MCP session
    await this.send("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "openclaw-nccn-monitor", version: "0.1.0" },
    });
    await this.send("notifications/initialized", {});
    this.initialized = true;
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<string> {
    if (!this.initialized) await this.start();

    const result = await this.send("tools/call", { name, arguments: args }) as {
      content?: Array<{ type: string; text: string }>;
    };

    if (result?.content) {
      return result.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("\n");
    }
    return JSON.stringify(result);
  }

  async stop(): Promise<void> {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
  }

  private send(method: string, params?: Record<string, unknown>): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.process?.stdin) {
        reject(new Error("MCP server not running"));
        return;
      }

      const id = randomUUID();
      const request: McpRequest = {
        jsonrpc: "2.0",
        id,
        method,
        ...(params ? { params } : {}),
      };

      this.pending.set(id, { resolve, reject });

      const line = JSON.stringify(request) + "\n";
      this.process.stdin.write(line);
    });
  }

  private handleLine(line: string): void {
    try {
      const msg = JSON.parse(line) as McpResponse;
      if (!msg.id) return; // notification, ignore

      const handler = this.pending.get(msg.id);
      if (!handler) return;
      this.pending.delete(msg.id);

      if (msg.error) {
        handler.reject(new Error(msg.error.message));
      } else {
        handler.resolve(msg.result);
      }
    } catch {
      // Not JSON — ignore (could be server log output)
    }
  }
}
