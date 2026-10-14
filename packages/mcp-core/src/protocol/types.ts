import type { z } from "zod";

export type ToolResult = {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
};

export type ToolDefinition<TSchema extends z.ZodType = z.ZodTypeAny> = {
  name: string;
  description: string;
  inputSchema: TSchema;
  execute: (input: z.output<TSchema>) => Promise<ToolResult>;
};
