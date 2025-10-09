"""Web application for FHIR chat interface with Aidbox MCP server."""

import json
import logging
import os
import sys

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.chat.interface import AzureChatInterface
from src.mcp import AidboxMCPClient, MCPClientConfig, MCPConnectionError


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

mcp_client: Optional[AidboxMCPClient] = None
openai_functions: List[Dict[str, Any]] = []


def convert_mcp_tools_to_openai_functions(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert MCP tool schemas to OpenAI function format.

    Args:
        mcp_tools: List of MCP tool definitions

    Returns:
        List of OpenAI function definitions
    """
    functions = []
    for tool in mcp_tools:
        function_def = {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
        }

        if "inputSchema" in tool:
            function_def["parameters"] = tool["inputSchema"]
        else:
            function_def["parameters"] = {"type": "object", "properties": {}}

        functions.append(function_def)

    return functions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global mcp_client, openai_functions

    api_key = os.environ.get("FHIR_CHAT_OPENAI_API_KEY")
    api_endpoint = os.environ.get("FHIR_CHAT_OPENAI_ENDPOINT")

    if not api_key or not api_endpoint:
        logger.error("Missing required environment variables: FHIR_CHAT_OPENAI_API_KEY and/or FHIR_CHAT_OPENAI_ENDPOINT")
        sys.exit(1)

    mcp_config = MCPClientConfig(
        server_url="http://localhost:8080/sse",
        log_level="WARNING"
    )

    logger.info("Connecting to Aidbox MCP server...")
    try:
        mcp_client = AidboxMCPClient(mcp_config)
        await mcp_client.connect()

        mcp_tools = await mcp_client.list_tools()
        openai_functions = convert_mcp_tools_to_openai_functions(mcp_tools)

        logger.info(f"Connected! Loaded {len(mcp_tools)} FHIR tools from Aidbox MCP server.")
        logger.info("Available tools:")
        for tool in mcp_tools:
            logger.info(f"  - {tool['name']}: {tool.get('description', 'No description')}")
    except MCPConnectionError as e:
        logger.error(f"Failed to connect to Aidbox MCP server: {e}")
        logger.error("Make sure Aidbox is running at http://localhost:8080")
        sys.exit(1)

    yield

    if mcp_client:
        await mcp_client.disconnect()
        logger.info("Disconnected from MCP server")


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main chat interface."""
    return templates.TemplateResponse(
        "chat.html",
        {"request": request}
    )


@app.get("/api/tools")
async def get_tools():
    """Get list of available tools."""
    if not mcp_client:
        return {"error": "MCP client not connected"}

    try:
        tools = await mcp_client.list_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for chat communication."""
    await websocket.accept()

    api_key = os.environ.get("FHIR_CHAT_OPENAI_API_KEY")
    api_endpoint = os.environ.get("FHIR_CHAT_OPENAI_ENDPOINT")

    if not api_key or not api_endpoint:
        await websocket.send_json({
            "type": "error",
            "content": "Server configuration error: Missing Azure OpenAI credentials"
        })
        await websocket.close()
        return

    chat = AzureChatInterface(
        api_key=api_key,
        azure_endpoint=api_endpoint,
        deployment_name="gpt-5-mini",
        model="gpt-5-mini",
        temperature=1.0
    )

    chat.start_with_system_message(
        "You are a helpful FHIR assistant with access to Aidbox tools. "
        "You can search, read, create, update, and delete FHIR resources. "
        "Use the available tools to help users with FHIR-related tasks."
    )

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                user_message = data.get("content", "").strip()

                if not user_message:
                    continue

                chat.add_message("user", user_message)

                max_iterations = 10
                iteration = 0

                while iteration < max_iterations:
                    iteration += 1

                    messages_for_api = []
                    for msg in chat.messages:
                        if hasattr(msg, 'model_dump'):
                            messages_for_api.append(msg.model_dump(exclude_none=True))
                        else:
                            messages_for_api.append(msg)

                    response = chat._client.chat.completions.create(
                        model=chat.deployment_name,
                        messages=messages_for_api,
                        temperature=chat.temperature,
                        tools=[{"type": "function", "function": f} for f in openai_functions],
                        tool_choice="auto"
                    )

                    message = response.choices[0].message

                    if message.tool_calls:
                        tool_calls_data = [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            }
                            for tc in message.tool_calls
                        ]
                        chat.add_message(
                            role="assistant",
                            content=message.content,
                            tool_calls=tool_calls_data
                        )

                        for tool_call in message.tool_calls:
                            function_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)

                            await websocket.send_json({
                                "type": "tool_call",
                                "tool_name": function_name,
                                "arguments": function_args
                            })

                            try:
                                tool_result = await mcp_client.call_tool(
                                    function_name,
                                    function_args
                                )

                                if hasattr(tool_result, 'model_dump'):
                                    result_data = tool_result.model_dump()
                                elif hasattr(tool_result, '__dict__'):
                                    result_data = tool_result.__dict__
                                else:
                                    result_data = tool_result

                                if isinstance(result_data, dict) and 'content' in result_data:
                                    content_list = result_data.get('content', [])
                                    if content_list and isinstance(content_list, list):
                                        serializable_content = []
                                        for item in content_list:
                                            if hasattr(item, 'model_dump'):
                                                serializable_content.append(item.model_dump())
                                            elif isinstance(item, dict):
                                                serializable_content.append(item)
                                            else:
                                                serializable_content.append(str(item))

                                        first_content = serializable_content[0] if serializable_content else {}
                                        if isinstance(first_content, dict) and 'text' in first_content:
                                            result_str = first_content['text']
                                        else:
                                            result_str = json.dumps(serializable_content, indent=2)
                                    else:
                                        result_str = json.dumps(result_data, indent=2, default=str)
                                else:
                                    result_str = json.dumps(result_data, indent=2, default=str)

                                await websocket.send_json({
                                    "type": "tool_result",
                                    "tool_name": function_name,
                                    "result": result_str
                                })

                                chat.add_message(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=result_str
                                )

                            except Exception as e:
                                error_msg = f"Error calling tool: {str(e)}"
                                logger.error(error_msg, exc_info=True)

                                await websocket.send_json({
                                    "type": "tool_error",
                                    "tool_name": function_name,
                                    "error": error_msg
                                })

                                chat.add_message(
                                    role="tool",
                                    tool_call_id=tool_call.id,
                                    content=error_msg
                                )

                        continue
                    else:
                        if message.content:
                            chat.add_message("assistant", message.content)
                            await websocket.send_json({
                                "type": "assistant",
                                "content": message.content
                            })
                        break

                if iteration >= max_iterations:
                    await websocket.send_json({
                        "type": "warning",
                        "content": "Maximum tool call iterations reached"
                    })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": str(e)
            })
        except:
            pass
