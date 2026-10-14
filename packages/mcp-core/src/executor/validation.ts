import type { z } from "zod";
import { McpCoreError } from "../protocol/errors.js";

export function validateInput<TSchema extends z.ZodType>(
  schema: TSchema,
  input: unknown,
): z.infer<TSchema> {
  const parsed = schema.safeParse(input);
  if (!parsed.success) {
    throw new McpCoreError(
      "INVALID_INPUT",
      "Tool input failed validation.",
      parsed.error.flatten(),
    );
  }
  return parsed.data;
}
