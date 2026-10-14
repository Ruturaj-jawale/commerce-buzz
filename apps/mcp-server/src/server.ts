import "dotenv/config";
import { createServer } from "node:http";
import { mcpHttpHandler } from "./transport.js";

const port = Number(process.env.MCP_PORT ?? 3001);
const host = process.env.MCP_HOST ?? "127.0.0.1";

const server = createServer((request, response) => {
  if (request.url?.split("?")[0] === "/mcp") {
    void mcpHttpHandler(request, response);
    return;
  }
  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ error: "Not found. Use /mcp." }));
});

server.listen(port, host, () => console.log(`SaaS MCP server listening at http://${host}:${port}/mcp`));
