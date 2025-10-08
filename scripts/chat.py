#!/usr/bin/env python3

import asyncio
import json
import os
import sys


from pathlib import Path
from src.chat.interface import AzureChatInterface
from src.mcp import AidboxMCPClient, MCPClientConfig, MCPConnectionError
from typing import Any, Dict, List


sys.path.insert(0, str(Path(__file__).parent.parent))


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

        # Add input schema as parameters if available
        if "inputSchema" in tool:
            function_def["parameters"] = tool["inputSchema"]
        else:
            function_def["parameters"] = {"type": "object", "properties": {}}

        functions.append(function_def)

    return functions


async def main():
    api_key = os.environ.get("FHIR_CHAT_OPENAI_API_KEY")
    if not api_key:
        print("Error: FHIR_CHAT_OPENAI_API_KEY environment variable not set")
        print("Please set it with: export FHIR_CHAT_OPENAI_API_KEY='your-api-key'")
        sys.exit(1)

    api_endpoint = os.environ.get("FHIR_CHAT_OPENAI_ENDPOINT")
    if not api_endpoint:
        print("Error: FHIR_CHAT_OPENAI_ENDPOINT environment variable not set")
        print("Please set it with: export FHIR_CHAT_OPENAI_ENDPOINT='your-api-endpoint'")
        sys.exit(1)

    # Initialize chat interface
    chat = AzureChatInterface(
        api_key=api_key,
        azure_endpoint=api_endpoint,
        deployment_name="gpt-5-mini",
        model="gpt-5-mini",
        temperature=1.0  # temp isn't supported with gpt-5-mini
    )

    # Initialize MCP client and get tools
    mcp_config = MCPClientConfig(
        server_url="http://localhost:8080/sse",
        log_level="WARNING"
    )

    print("Connecting to Aidbox MCP server...")
    try:
        async with AidboxMCPClient(mcp_config) as mcp_client:
            # Get available tools
            mcp_tools = await mcp_client.list_tools()
            openai_functions = convert_mcp_tools_to_openai_functions(mcp_tools)

            print(f"Connected! Loaded {len(mcp_tools)} FHIR tools from Aidbox MCP server.")
            print("\nAvailable tools:")
            for tool in mcp_tools:
                print(f"  - {tool['name']}: {tool.get('description', 'No description')}")

            chat.start_with_system_message(
                "You are a helpful FHIR assistant with access to Aidbox tools. "
                "You can search, read, create, update, and delete FHIR resources. "
                "Use the available tools to help users with FHIR-related tasks."
            )

            print("\n" + "=" * 70)
            print("Chat Interface with Aidbox MCP Tools")
            print("=" * 70)
            print("Type 'quit' or 'exit' to end the conversation")
            print("The assistant has access to FHIR tools from Aidbox\n")

            while True:
                try:
                    user_input = input("You: ").strip()

                    if user_input.lower() in ["quit", "exit", "q"]:
                        print("Goodbye!")
                        break

                    if not user_input:
                        continue

                    # Add user message
                    chat.add_message("user", user_input)

                    # Loop to handle multiple tool calls
                    max_iterations = 10  # Prevent infinite loops
                    iteration = 0

                    while iteration < max_iterations:
                        iteration += 1

                        # Get response with function calling
                        # Convert messages to dict format for OpenAI API
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

                        # Check if there are tool calls
                        if message.tool_calls:
                            # Add assistant message with tool calls to history
                            chat.messages.append({
                                "role": "assistant",
                                "content": message.content,
                                "tool_calls": [
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
                            })

                            # Execute each tool call
                            for tool_call in message.tool_calls:
                                function_name = tool_call.function.name
                                function_args = json.loads(tool_call.function.arguments)

                                print(f"\n[Calling tool: {function_name}]")
                                print(f"[Arguments: {json.dumps(function_args, indent=2)}]")

                                try:
                                    # Call the MCP tool
                                    tool_result = await mcp_client.call_tool(
                                        function_name,
                                        function_args
                                    )

                                    # Extract content from CallToolResult
                                    # The result might be a CallToolResult object or similar
                                    if hasattr(tool_result, 'model_dump'):
                                        result_data = tool_result.model_dump()
                                    elif hasattr(tool_result, '__dict__'):
                                        result_data = tool_result.__dict__
                                    else:
                                        result_data = tool_result

                                    # Extract the actual content from the result
                                    if isinstance(result_data, dict) and 'content' in result_data:
                                        # If there's a content field, extract it
                                        content_list = result_data.get('content', [])
                                        if content_list and isinstance(content_list, list):
                                            # Convert content items to dicts if they have model_dump
                                            serializable_content = []
                                            for item in content_list:
                                                if hasattr(item, 'model_dump'):
                                                    serializable_content.append(item.model_dump())
                                                elif isinstance(item, dict):
                                                    serializable_content.append(item)
                                                else:
                                                    serializable_content.append(str(item))

                                            # Get the first content item's text
                                            first_content = serializable_content[0] if serializable_content else {}
                                            if isinstance(first_content, dict) and 'text' in first_content:
                                                result_str = first_content['text']
                                            else:
                                                result_str = json.dumps(serializable_content, indent=2)
                                        else:
                                            result_str = json.dumps(result_data, indent=2, default=str)
                                    else:
                                        result_str = json.dumps(result_data, indent=2, default=str)

                                    print(f"[Result: {result_str[:200]}...]")

                                    # Add tool result to conversation
                                    chat.messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": result_str
                                    })

                                except Exception as e:
                                    error_msg = f"Error calling tool: {str(e)}"
                                    print(f"[{error_msg}]")
                                    import traceback
                                    traceback.print_exc()
                                    chat.messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": error_msg
                                    })

                            # Continue loop to get assistant's response with tool results
                            continue
                        else:
                            # No more tool calls, show final response
                            if message.content:
                                chat.add_message("assistant", message.content)
                                print(f"\nAssistant: {message.content}\n")
                            break

                    if iteration >= max_iterations:
                        print("\n[Warning: Maximum tool call iterations reached]\n")

                except KeyboardInterrupt:
                    print("\n\nGoodbye!")
                    break
                except Exception as e:
                    print(f"\nError: {e}")
                    import traceback
                    traceback.print_exc()

    except MCPConnectionError as e:
        print(f"Failed to connect to Aidbox MCP server: {e}")
        print("Make sure Aidbox is running at http://localhost:8080")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
