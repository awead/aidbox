"""Tests for the web application."""


from src.web.app import convert_mcp_tools_to_openai_functions


def test_convert_mcp_tools_to_openai_functions():
    """Test conversion of MCP tool schemas to OpenAI function format."""
    mcp_tools = [
        {
            "name": "search_patients",
            "description": "Search for patients",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                }
            }
        },
        {
            "name": "read_resource",
            "description": "Read a FHIR resource"
        }
    ]

    result = convert_mcp_tools_to_openai_functions(mcp_tools)

    assert len(result) == 2
    assert result[0]["name"] == "search_patients"
    assert result[0]["description"] == "Search for patients"
    assert result[0]["parameters"]["type"] == "object"
    assert "name" in result[0]["parameters"]["properties"]

    assert result[1]["name"] == "read_resource"
    assert result[1]["description"] == "Read a FHIR resource"
    assert result[1]["parameters"]["type"] == "object"
    assert result[1]["parameters"]["properties"] == {}


def test_templates_directory_exists():
    """Test that templates directory exists."""
    from src.web.app import TEMPLATES_DIR
    assert TEMPLATES_DIR.exists()
    assert TEMPLATES_DIR.is_dir()
    assert (TEMPLATES_DIR / "chat.html").exists()


def test_static_directory_exists():
    """Test that static directory exists."""
    from src.web.app import STATIC_DIR
    assert STATIC_DIR.exists()
    assert STATIC_DIR.is_dir()
    assert (STATIC_DIR / "style.css").exists()
    assert (STATIC_DIR / "chat.js").exists()
