import { McpServer } from "@modelcontextprotocol/server";
import { ToolExecutor, ToolRegistry } from "../../../packages/mcp-core/src/index.js";
import { createPostgresTools } from "../../../packages/connectors/postgres/src/tools.js";

export function createMcpServer(): McpServer {
  const registry = new ToolRegistry();
  for (const tool of createPostgresTools()) registry.register(tool);
  const executor = new ToolExecutor(registry);
  const server = new McpServer({ name: "saas-mcp", version: "1.0.0" });
  for (const tool of registry.list()) {
    server.registerTool(tool.name, { description: tool.description, inputSchema: tool.inputSchema }, async (input) => executor.execute(tool.name, input));
  }
  return server;
}
