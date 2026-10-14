import { getJson } from "./client";
import type { BackendHealth, McpStatus } from "../types/health";

export function fetchBackendHealth(): Promise<BackendHealth> {
  return getJson<BackendHealth>("/health");
}

export function fetchMcpStatus(): Promise<McpStatus> {
  return getJson<McpStatus>("/mcp/status");
}