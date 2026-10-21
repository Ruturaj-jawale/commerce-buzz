"""Root entrypoint for SaaS MCP stdio server.

Usage:
    python mcp_server.py
    python mcp_server.py --api-key <YOUR_KEY>
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

env_path = backend_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.environ.get("DATABASE_URL", "")
if not db_url or db_url == "sqlite:///./saas_mcp.db":
    db_file = backend_dir / "saas_mcp.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"

from app.mcp.cli import main

if __name__ == "__main__":
    main()

