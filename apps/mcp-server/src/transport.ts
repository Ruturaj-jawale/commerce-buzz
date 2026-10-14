import { createMcpHandler } from "@modelcontextprotocol/server";
import { toNodeHandler } from "@modelcontextprotocol/node";
import { createMcpServer } from "./router.js";

export const mcpHttpHandler = toNodeHandler(createMcpHandler(createMcpServer));
