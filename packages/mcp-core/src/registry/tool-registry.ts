import { McpCoreError } from "../protocol/errors.js";
import type { ToolDefinition } from "../protocol/types.js";

export class ToolRegistry {
  private readonly tools = new Map<string, ToolDefinition>();

  register(tool: ToolDefinition): void {
    if (this.tools.has(tool.name)) {
      throw new McpCoreError("INTERNAL_ERROR", `Tool already registered: ${tool.name}`);
    }
    this.tools.set(tool.name, tool);
  }

  get(name: string): ToolDefinition {
    const tool = this.tools.get(name);
    if (!tool) throw new McpCoreError("TOOL_NOT_FOUND", `Unknown tool: ${name}`);
    return tool;
  }

  list(): ToolDefinition[] {
    return [...this.tools.values()];
  }
}
