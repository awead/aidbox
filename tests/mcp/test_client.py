import logging
import pytest

from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp.client import (
    AidboxMCPClient,
    MCPClientConfig,
    MCPClientError,
    MCPConnectionError,
    MCPOperationError,
)


class TestMCPClientConfig:

    def test_default_values(self):
        config = MCPClientConfig()
        assert str(config.server_url) == "http://localhost:8080/sse"
        assert config.timeout == 30
        assert config.log_level == "INFO"

    def test_custom_values(self):
        config = MCPClientConfig(
            server_url="http://example.com:9000/mcp",
            timeout=60,
            log_level="DEBUG",
        )
        assert str(config.server_url) == "http://example.com:9000/mcp"
        assert config.timeout == 60
        assert config.log_level == "DEBUG"

    def test_timeout_minimum_constraint(self):
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig(timeout=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_timeout_maximum_constraint(self):
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig(timeout=301)
        assert "less than or equal to 300" in str(exc_info.value)

    def test_timeout_boundary_values(self):
        config_min = MCPClientConfig(timeout=1)
        assert config_min.timeout == 1

        config_max = MCPClientConfig(timeout=300)
        assert config_max.timeout == 300

    def test_log_level_case_insensitive(self):
        config_lower = MCPClientConfig(log_level="debug")
        assert config_lower.log_level == "DEBUG"

        config_mixed = MCPClientConfig(log_level="WaRnInG")
        assert config_mixed.log_level == "WARNING"

    def test_valid_log_levels(self):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            config = MCPClientConfig(log_level=level)
            assert config.log_level == level

    def test_invalid_log_level(self):
        with pytest.raises(ValidationError) as exc_info:
            MCPClientConfig(log_level="INVALID")
        assert "log_level must be one of" in str(exc_info.value)

    def test_invalid_server_url(self):
        with pytest.raises(ValidationError):
            MCPClientConfig(server_url="not-a-valid-url")

    def test_https_server_url(self):
        config = MCPClientConfig(server_url="https://secure.example.com/sse")
        assert str(config.server_url) == "https://secure.example.com/sse"

    def test_model_dump(self):
        config = MCPClientConfig(
            server_url="http://test.com:8080/sse",
            timeout=45,
            log_level="WARNING",
        )
        dumped = config.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["timeout"] == 45
        assert dumped["log_level"] == "WARNING"


class TestMCPExceptions:

    def test_mcp_client_error_inheritance(self):
        error = MCPClientError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_mcp_connection_error_inheritance(self):
        error = MCPConnectionError("Connection failed")
        assert isinstance(error, MCPClientError)
        assert isinstance(error, Exception)
        assert str(error) == "Connection failed"

    def test_mcp_operation_error_inheritance(self):
        error = MCPOperationError("Operation failed")
        assert isinstance(error, MCPClientError)
        assert isinstance(error, Exception)
        assert str(error) == "Operation failed"

    def test_exception_with_cause(self):
        original_error = ValueError("Original error")
        try:
            raise MCPConnectionError("Wrapped error") from original_error
        except MCPConnectionError as e:
            assert str(e) == "Wrapped error"
            assert e.__cause__ is original_error


@pytest.fixture
def mock_fastmcp_client():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.fixture
def client_config():
    return MCPClientConfig(
        server_url="http://localhost:8080/sse",
        timeout=30,
        log_level="INFO",
    )


@pytest.fixture
def aidbox_client(client_config):
    return AidboxMCPClient(client_config)


class TestAidboxMCPClientInit:

    def test_init_with_config(self, client_config):
        client = AidboxMCPClient(client_config)
        assert client.config == client_config
        assert client._client is None
        assert client._connected is False

    def test_init_without_config(self):
        client = AidboxMCPClient()
        assert client.config is not None
        assert str(client.config.server_url) == "http://localhost:8080/sse"
        assert client.config.timeout == 30
        assert client._client is None
        assert client._connected is False

    def test_init_with_none_config(self):
        client = AidboxMCPClient(config=None)
        assert client.config is not None
        assert str(client.config.server_url) == "http://localhost:8080/sse"

    @patch("src.mcp.client.logging.basicConfig")
    def test_logging_configuration(self, mock_basic_config, client_config):
        AidboxMCPClient(client_config)
        mock_basic_config.assert_called_once()
        call_kwargs = mock_basic_config.call_args[1]
        assert call_kwargs["level"] == logging.INFO
        assert "%(asctime)s" in call_kwargs["format"]


class TestAidboxMCPClientConnection:

    @pytest.mark.asyncio
    async def test_connect_success(self, aidbox_client, mock_fastmcp_client):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            assert aidbox_client._connected is True
            assert aidbox_client._client is not None
            mock_fastmcp_client.__aenter__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, aidbox_client):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("Network error"))

        with patch("src.mcp.client.Client", return_value=mock_client):
            with pytest.raises(MCPConnectionError) as exc_info:
                await aidbox_client.connect()

            assert "Failed to connect to MCP server" in str(exc_info.value)
            assert aidbox_client._connected is False

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, aidbox_client, mock_fastmcp_client):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            with pytest.raises(RuntimeError) as exc_info:
                await aidbox_client.connect()

            assert "already connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disconnect_success(self, aidbox_client, mock_fastmcp_client):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            await aidbox_client.disconnect()

            assert aidbox_client._connected is False
            assert aidbox_client._client is None
            mock_fastmcp_client.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, aidbox_client):
        with pytest.raises(RuntimeError) as exc_info:
            await aidbox_client.disconnect()

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_disconnect_error_handling(self, aidbox_client, mock_fastmcp_client):
        mock_fastmcp_client.__aexit__ = AsyncMock(
            side_effect=Exception("Disconnect error")
        )

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            with pytest.raises(Exception) as exc_info:
                await aidbox_client.disconnect()

            assert "Disconnect error" in str(exc_info.value)


class TestAidboxMCPClientContextManager:

    @pytest.mark.asyncio
    async def test_context_manager_success(self, aidbox_client, mock_fastmcp_client):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            async with aidbox_client as client:
                assert client is aidbox_client
                assert client._connected is True

            assert aidbox_client._connected is False
            mock_fastmcp_client.__aenter__.assert_awaited_once()
            mock_fastmcp_client.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_manager_connection_failure(self, aidbox_client):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("Network error"))

        with patch("src.mcp.client.Client", return_value=mock_client):
            with pytest.raises(MCPConnectionError):
                async with aidbox_client:
                    pass

    @pytest.mark.asyncio
    async def test_context_manager_exception_during_use(
        self, aidbox_client, mock_fastmcp_client
    ):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            with pytest.raises(ValueError):
                async with aidbox_client:
                    raise ValueError("Test error")

            assert aidbox_client._connected is False
            mock_fastmcp_client.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_manager_returns_false(self, aidbox_client, mock_fastmcp_client):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            result = await aidbox_client.__aexit__(None, None, None)
            assert result is False


class TestAidboxMCPClientListTools:

    @pytest.mark.asyncio
    async def test_list_tools_success(self, aidbox_client, mock_fastmcp_client):
        mock_tool1 = MagicMock()
        mock_tool1.model_dump.return_value = {
            "name": "search_patients",
            "description": "Search for patients",
            "inputSchema": {"type": "object"},
        }

        mock_tool2 = MagicMock()
        mock_tool2.model_dump.return_value = {
            "name": "get_patient",
            "description": "Get patient by ID",
            "inputSchema": {"type": "object"},
        }

        mock_fastmcp_client.list_tools = AsyncMock(return_value=[mock_tool1, mock_tool2])

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            tools = await aidbox_client.list_tools()

            assert len(tools) == 2
            assert tools[0]["name"] == "search_patients"
            assert tools[1]["name"] == "get_patient"
            mock_fastmcp_client.list_tools.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_tools_empty(self, aidbox_client, mock_fastmcp_client):
        mock_fastmcp_client.list_tools = AsyncMock(return_value=[])

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            tools = await aidbox_client.list_tools()

            assert tools == []
            assert isinstance(tools, list)

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self, aidbox_client):
        with pytest.raises(RuntimeError) as exc_info:
            await aidbox_client.list_tools()

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_tools_operation_error(self, aidbox_client, mock_fastmcp_client):
        mock_fastmcp_client.list_tools = AsyncMock(
            side_effect=Exception("Server error")
        )

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            with pytest.raises(MCPOperationError) as exc_info:
                await aidbox_client.list_tools()

            assert "Failed to list tools" in str(exc_info.value)


class TestAidboxMCPClientCallTool:

    @pytest.mark.asyncio
    async def test_call_tool_success(self, aidbox_client, mock_fastmcp_client):
        expected_result = {"status": "success", "data": {"id": "123", "name": "John"}}
        mock_fastmcp_client.call_tool = AsyncMock(return_value=expected_result)

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            result = await aidbox_client.call_tool(
                "get_patient", {"patient_id": "123"}
            )

            assert result == expected_result
            mock_fastmcp_client.call_tool.assert_awaited_once_with(
                "get_patient", {"patient_id": "123"}
            )

    @pytest.mark.asyncio
    async def test_call_tool_no_arguments(self, aidbox_client, mock_fastmcp_client):
        expected_result = {"tools": ["tool1", "tool2"]}
        mock_fastmcp_client.call_tool = AsyncMock(return_value=expected_result)

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            result = await aidbox_client.call_tool("list_all_tools")

            assert result == expected_result
            mock_fastmcp_client.call_tool.assert_awaited_once_with("list_all_tools", {})

    @pytest.mark.asyncio
    async def test_call_tool_with_none_arguments(self, aidbox_client, mock_fastmcp_client):
        expected_result = {"status": "ok"}
        mock_fastmcp_client.call_tool = AsyncMock(return_value=expected_result)

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            result = await aidbox_client.call_tool("ping", None)

            assert result == expected_result
            mock_fastmcp_client.call_tool.assert_awaited_once_with("ping", {})

    @pytest.mark.asyncio
    async def test_call_tool_complex_arguments(self, aidbox_client, mock_fastmcp_client):
        complex_args = {
            "query": {"name": {"$like": "%John%"}, "age": {"$gte": 18}},
            "limit": 10,
            "offset": 0,
        }
        expected_result = {"count": 5, "results": []}
        mock_fastmcp_client.call_tool = AsyncMock(return_value=expected_result)

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            result = await aidbox_client.call_tool("search_patients", complex_args)

            assert result == expected_result
            mock_fastmcp_client.call_tool.assert_awaited_once_with(
                "search_patients", complex_args
            )

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self, aidbox_client):
        with pytest.raises(RuntimeError) as exc_info:
            await aidbox_client.call_tool("test_tool", {})

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_tool_operation_error(self, aidbox_client, mock_fastmcp_client):
        mock_fastmcp_client.call_tool = AsyncMock(
            side_effect=Exception("Tool not found")
        )

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            with pytest.raises(MCPOperationError) as exc_info:
                await aidbox_client.call_tool("nonexistent_tool", {})

            assert "Failed to call tool nonexistent_tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_tool_returns_none(self, aidbox_client, mock_fastmcp_client):
        mock_fastmcp_client.call_tool = AsyncMock(return_value=None)

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()
            result = await aidbox_client.call_tool("delete_resource", {"id": "123"})

            assert result is None

    @pytest.mark.asyncio
    async def test_call_tool_returns_primitive_types(
        self, aidbox_client, mock_fastmcp_client
    ):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            mock_fastmcp_client.call_tool = AsyncMock(return_value=42)
            result = await aidbox_client.call_tool("count_resources", {})
            assert result == 42

            mock_fastmcp_client.call_tool = AsyncMock(return_value="success")
            result = await aidbox_client.call_tool("status", {})
            assert result == "success"

            mock_fastmcp_client.call_tool = AsyncMock(return_value=True)
            result = await aidbox_client.call_tool("is_healthy", {})
            assert result is True


class TestAidboxMCPClientGetClientContextManager:

    @pytest.mark.asyncio
    async def test_get_client_success(self, aidbox_client, mock_fastmcp_client):
        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            async with aidbox_client._get_client() as client:
                assert client is mock_fastmcp_client
                mock_fastmcp_client.__aenter__.assert_awaited_once()

            mock_fastmcp_client.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_client_connection_error(self, aidbox_client):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("Network error"))

        with patch("src.mcp.client.Client", return_value=mock_client):
            with pytest.raises(MCPConnectionError) as exc_info:
                async with aidbox_client._get_client():
                    pass

            assert "Failed to connect to MCP server" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_client_uses_correct_url(self, client_config):
        client_config.server_url = "http://custom.server:9090/sse"
        aidbox_client = AidboxMCPClient(client_config)

        with patch("src.mcp.client.Client") as mock_client_class:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_instance

            async with aidbox_client._get_client():
                pass

            mock_client_class.assert_called_once_with(
                "http://custom.server:9090/sse"
            )


class TestAidboxMCPClientIntegration:

    @pytest.mark.asyncio
    async def test_complete_workflow_with_context_manager(
        self, aidbox_client, mock_fastmcp_client
    ):
        mock_tool = MagicMock()
        mock_tool.model_dump.return_value = {
            "name": "search_patients",
            "description": "Search patients",
        }
        mock_fastmcp_client.list_tools = AsyncMock(return_value=[mock_tool])
        mock_fastmcp_client.call_tool = AsyncMock(
            return_value={"count": 1, "results": [{"id": "123"}]}
        )

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            async with aidbox_client:
                tools = await aidbox_client.list_tools()
                assert len(tools) == 1

                result = await aidbox_client.call_tool(
                    "search_patients", {"name": "John"}
                )
                assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_complete_workflow_manual_connection(
        self, aidbox_client, mock_fastmcp_client
    ):
        mock_tool = MagicMock()
        mock_tool.model_dump.return_value = {"name": "test_tool"}
        mock_fastmcp_client.list_tools = AsyncMock(return_value=[mock_tool])
        mock_fastmcp_client.call_tool = AsyncMock(return_value={"status": "ok"})

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            try:
                tools = await aidbox_client.list_tools()
                assert len(tools) == 1

                result = await aidbox_client.call_tool("test_tool", {})
                assert result["status"] == "ok"
            finally:
                await aidbox_client.disconnect()

        assert aidbox_client._connected is False

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, aidbox_client, mock_fastmcp_client):
        mock_fastmcp_client.call_tool = AsyncMock(
            side_effect=[
                {"result": "first"},
                {"result": "second"},
                {"result": "third"},
            ]
        )

        with patch("src.mcp.client.Client", return_value=mock_fastmcp_client):
            await aidbox_client.connect()

            result1 = await aidbox_client.call_tool("tool1", {})
            result2 = await aidbox_client.call_tool("tool2", {})
            result3 = await aidbox_client.call_tool("tool3", {})

            assert result1["result"] == "first"
            assert result2["result"] == "second"
            assert result3["result"] == "third"
            assert mock_fastmcp_client.call_tool.await_count == 3

            await aidbox_client.disconnect()


