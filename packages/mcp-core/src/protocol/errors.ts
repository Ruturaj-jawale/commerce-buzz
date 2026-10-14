export type McpErrorCode =
  | "INVALID_INPUT"
  | "TOOL_NOT_FOUND"
  | "DATABASE_ERROR"
  | "UNSAFE_QUERY"
  | "INTERNAL_ERROR";

export class McpCoreError extends Error {
  constructor(
    public readonly code: McpErrorCode,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "McpCoreError";
  }
}

export const asMcpCoreError = (error: unknown): McpCoreError =>
  error instanceof McpCoreError
    ? error
    : new McpCoreError("INTERNAL_ERROR", "The tool could not be completed.", error);
