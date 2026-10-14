import { asMcpCoreError } from "../protocol/errors.js";
import type { ToolResult } from "../protocol/types.js";
import { ToolRegistry } from "../registry/tool-registry.js";
import { validateInput } from "./validation.js";

export class ToolExecutor {
  constructor(private readonly registry: ToolRegistry) {}

  async execute(name: string, input: unknown): Promise<ToolResult> {
    try {
      const tool = this.registry.get(name);
      const validatedInput = validateInput(tool.inputSchema, input);
      return await tool.execute(validatedInput);
    } catch (error) {
      const normalized = asMcpCoreError(error);
      return {
        content: [{ type: "text", text: JSON.stringify({ error: normalized.code, message: normalized.message, details: normalized.details }) }],
        isError: true,
      };
    }
  }
}
