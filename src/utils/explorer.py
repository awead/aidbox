from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from src.mcp import AidboxMCPClient, MCPClientConfig, MCPConnectionError

console = Console()

config = MCPClientConfig(
    server_url="http://localhost:8080/sse",
    timeout=30,
    log_level="WARNING"
)

async def list_tools():
    """Listing available tools"""

    try:
        async with AidboxMCPClient(config) as client:
            tools = await client.list_tools()

            # Create a table for tools
            table = Table(title="Available Tools", show_header=True, header_style="bold magenta")
            table.add_column("Name", style="cyan")
            table.add_column("Description", style="white")

            for tool in tools:
                table.add_row(tool.get('name', 'N/A'), tool.get('description', 'N/A'))

            console.print(table)

    except MCPConnectionError as e:
        console.print(f"[red]Failed to connect to MCP server: {e}[/red]")
        console.print("[yellow]Make sure Aidbox is running and MCP endpoints are configured[/yellow]")
    except Exception as e:
        console.print(f"[red]Error during MCP operations: {e}[/red]")


async def get_tool(tool_name):
    """Print the detailed information for a given tool"""

    console.print(Panel(f"Showing tool: {tool_name}", style="bold cyan"))

    try:
        async with AidboxMCPClient(config) as client:
            tools = await client.list_tools()

            tool = next((t for t in tools if t.get("name") == tool_name), None)

            if tool:
                console.print(JSON.from_data(tool))
            else:
                console.print(f"[yellow]Tool '{tool_name}' not found[/yellow]")

    except MCPConnectionError as e:
        console.print(f"[red]Failed to connect to MCP server: {e}[/red]")
        console.print("[yellow]Make sure Aidbox is running and MCP endpoints are configured[/yellow]")
    except Exception as e:
        console.print(f"[red]Error during MCP operations: {e}[/red]")
