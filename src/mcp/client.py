"""MCP client for connecting to Aidbox MCP server."""

import logging

from contextlib import asynccontextmanager
from fastmcp import Client
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class MCPClientConfig(BaseModel):
    """Configuration for the MCP client connection."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    server_url: HttpUrl = Field(
        default="http://localhost:8080/sse",
        description="URL of the Aidbox MCP server endpoint",
    )
    timeout: int = Field(
        default=30,
        description="Connection timeout in seconds",
        ge=1,
        le=300
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level for the MCP client"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate that log_level is a valid logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper


class MCPClientError(Exception):
    """Base exception for MCP client errors."""

    pass


class MCPConnectionError(MCPClientError):
    """Exception raised when connection to MCP server fails."""

    pass


class MCPOperationError(MCPClientError):
    """Exception raised when an MCP operation fails."""

    pass


class AidboxMCPClient:
    """Client for interacting with the Aidbox MCP server.

    This client provides a high-level interface for connecting to an Aidbox MCP server
    via HTTP/SSE and executing various operations like listing and calling tools,
    reading resources, and working with prompts.

    Example:
        Basic usage with context manager:

        >>> config = MCPClientConfig(server_url="http://localhost:8080/sse")
        >>> async with AidboxMCPClient(config) as client:
        ...     tools = await client.list_tools()
        ...     result = await client.call_tool("search_patients", {"name": "John"})

        Direct usage:

        >>> client = AidboxMCPClient(config)
        >>> await client.connect()
        >>> try:
        ...     tools = await client.list_tools()
        ... finally:
        ...     await client.disconnect()
    """

    def __init__(self, config: Optional[MCPClientConfig] = None):
        """Initialize the MCP client with configuration.

        Args:
            config: Configuration for the MCP client. If None, uses default configuration.
        """
        self.config = config or MCPClientConfig()
        self._client: Optional[Client] = None
        self._connected = False

        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logger.info(f"Initialized MCP client for server: {self.config.server_url}")

    @asynccontextmanager
    async def _get_client(self):
        """Context manager for the FastMCP client connection.

        Yields:
            The connected FastMCP Client instance.

        Raises:
            MCPConnectionError: If connection to the server fails.
        """
        try:
            client = Client(str(self.config.server_url))
            async with client as c:
                logger.info("Successfully connected to MCP server")
                yield c
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def connect(self) -> None:
        """Establish connection to the MCP server.

        Raises:
            MCPConnectionError: If connection fails.
            RuntimeError: If already connected.
        """
        if self._connected:
            raise RuntimeError("Client is already connected")

        try:
            self._client = Client(str(self.config.server_url))
            await self._client.__aenter__()
            self._connected = True
            logger.info("Connected to MCP server")
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            raise MCPConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def disconnect(self) -> None:
        """Close the connection to the MCP server.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected or not self._client:
            raise RuntimeError("Client is not connected")

        try:
            await self._client.__aexit__(None, None, None)
            self._connected = False
            self._client = None
            logger.info("Disconnected from MCP server")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        return False


    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools on the MCP server.

        Returns:
            List of tool definitions with their names, descriptions, and schemas.

        Raises:
            MCPOperationError: If listing tools fails.
            RuntimeError: If not connected.
        """
        if not self._connected or not self._client:
            raise RuntimeError(
                "Client is not connected. Use connect() or async context manager."
            )

        try:
            tools = await self._client.list_tools()
            logger.debug(f"Listed {len(tools)} tools")
            return [tool.model_dump() for tool in tools]
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            raise MCPOperationError(f"Failed to list tools: {e}") from e


    async def call_tool(
        self, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool. Defaults to empty dict.

        Returns:
            Result returned by the tool.

        Raises:
            MCPOperationError: If tool call fails.
            RuntimeError: If not connected.
        """
        if not self._connected or not self._client:
            raise RuntimeError(
                "Client is not connected. Use connect() or async context manager."
            )

        arguments = arguments or {}

        try:
            logger.debug(f"Calling tool: {tool_name} with arguments: {arguments}")
            result = await self._client.call_tool(tool_name, arguments)
            logger.debug(f"Tool call successful: {tool_name}")
            return result
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name}: {e}")
            raise MCPOperationError(f"Failed to call tool {tool_name}: {e}") from e

