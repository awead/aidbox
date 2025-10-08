"""Interactive console with preloaded modules for Aidbox development."""

from src.mcp import AidboxMCPClient, MCPClientConfig, MCPConnectionError # noqa: F401
from src.utils.explorer import list_tools, get_tool # noqa: F401

print("Console ready")
