"""Root entrypoint for SaaS MCP stdio server.

Usage:
    python mcp_server.py
    python mcp_server.py --api-key <YOUR_KEY>
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.mcp.cli import main

if __name__ == "__main__":
    main()
