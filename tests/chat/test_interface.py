import pytest


from pydantic import ValidationError
from src.chat.interface import ChatMessage, ChatInterface, AzureChatInterface
from unittest.mock import MagicMock, patch


class TestChatMessage:

    def test_system_message_creation(self):
        message = ChatMessage(role="system", content="You are a helpful assistant.")
        assert message.role == "system"
        assert message.content == "You are a helpful assistant."
        assert message.name is None
        assert message.tool_calls is None
        assert message.tool_call_id is None

    def test_function_message_creation(self):
        message = ChatMessage(
            role="function",
            content='{"result": "success"}',
            name="get_weather"
        )
        assert message.role == "function"
        assert message.content == '{"result": "success"}'
        assert message.name == "get_weather"
        assert message.tool_calls is None
        assert message.tool_call_id is None

    def test_tool_message_creation(self):
        message = ChatMessage(
            role="tool",
            content='{"temperature": 72}',
            tool_call_id="call_123456"
        )
        assert message.role == "tool"
        assert message.content == '{"temperature": 72}'
        assert message.tool_call_id == "call_123456"
        assert message.tool_calls is None

    def test_assistant_message_with_tool_calls(self):
        tool_calls = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location": "NYC"}'}
            }
        ]
        message = ChatMessage(
            role="assistant",
            content=None,
            tool_calls=tool_calls
        )
        assert message.role == "assistant"
        assert message.content is None
        assert message.tool_calls == tool_calls
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0]["id"] == "call_123"

    def test_message_with_name_field(self):
        message = ChatMessage(
            role="user",
            content="Test message",
            name="John"
        )
        assert message.role == "user"
        assert message.content == "Test message"
        assert message.name == "John"

    def test_invalid_role_raises_validation_error(self):
        with pytest.raises(ValidationError) as excinfo:
            ChatMessage(role="invalid_role", content="Test")
        assert "role" in str(excinfo.value)

    def test_message_without_role_raises_validation_error(self):
        with pytest.raises(ValidationError) as excinfo:
            ChatMessage(content="Test")
        assert "role" in str(excinfo.value)

    def test_message_content_can_be_none(self):
        message = ChatMessage(role="assistant", content=None)
        assert message.role == "assistant"
        assert message.content is None

    def test_message_serialization_includes_all_fields(self):
        message = ChatMessage(role="user", content="Hello")
        dumped = message.model_dump()
        assert "role" in dumped
        assert "content" in dumped
        assert "name" in dumped
        assert "tool_calls" in dumped
        assert "tool_call_id" in dumped
        assert dumped["name"] is None


class TestChatInterface:

    @pytest.fixture
    def mock_openai_client(self):
        with patch('src.chat.interface.OpenAI') as mock_client:
            yield mock_client

    @pytest.fixture
    def chat_interface(self, mock_openai_client):
        return ChatInterface(
            api_key="test-api-key",
            model="gpt-4",
            temperature=0.7
        )

    @pytest.fixture
    def chat_interface_with_max_tokens(self, mock_openai_client):
        return ChatInterface(
            api_key="test-api-key",
            model="gpt-4",
            temperature=0.7,
            max_tokens=500
        )

    def test_chat_interface_initialization(self, mock_openai_client):
        interface = ChatInterface(api_key="test-api-key")
        assert interface.api_key == "test-api-key"
        assert interface.model == "gpt-4"
        assert interface.temperature == 0.7
        assert interface.max_tokens is None
        assert len(interface.messages) == 0
        mock_openai_client.assert_called_once_with(api_key="test-api-key")

    def test_chat_interface_custom_initialization(self, mock_openai_client):
        interface = ChatInterface(
            api_key="custom-key",
            model="gpt-3.5-turbo",
            temperature=0.5,
            max_tokens=1000
        )
        assert interface.api_key == "custom-key"
        assert interface.model == "gpt-3.5-turbo"
        assert interface.temperature == 0.5
        assert interface.max_tokens == 1000
        mock_openai_client.assert_called_once_with(api_key="custom-key")

    def test_temperature_validation_min(self, mock_openai_client):
        with pytest.raises(ValidationError) as excinfo:
            ChatInterface(api_key="test-key", temperature=-0.1)
        assert "temperature" in str(excinfo.value)

    def test_temperature_validation_max(self, mock_openai_client):
        with pytest.raises(ValidationError) as excinfo:
            ChatInterface(api_key="test-key", temperature=2.1)
        assert "temperature" in str(excinfo.value)

    def test_temperature_boundary_values(self, mock_openai_client):
        interface_min = ChatInterface(api_key="test-key", temperature=0.0)
        assert interface_min.temperature == 0.0

        interface_max = ChatInterface(api_key="test-key", temperature=2.0)
        assert interface_max.temperature == 2.0

    def test_add_message(self, chat_interface):
        chat_interface.add_message("user", "Hello!")
        assert len(chat_interface.messages) == 1
        assert chat_interface.messages[0].role == "user"
        assert chat_interface.messages[0].content == "Hello!"

    def test_add_message_with_all_parameters(self, chat_interface):
        tool_calls = [{"id": "call_1", "type": "function"}]
        chat_interface.add_message(
            role="assistant",
            content="I'll help you with that.",
            name="Assistant",
            tool_calls=tool_calls,
            tool_call_id=None
        )
        assert len(chat_interface.messages) == 1
        message = chat_interface.messages[0]
        assert message.role == "assistant"
        assert message.content == "I'll help you with that."
        assert message.name == "Assistant"
        assert message.tool_calls == tool_calls

    def test_add_message_with_tool_call_id(self, chat_interface):
        chat_interface.add_message(
            role="tool",
            content='{"result": "success"}',
            tool_call_id="call_123"
        )
        assert len(chat_interface.messages) == 1
        message = chat_interface.messages[0]
        assert message.role == "tool"
        assert message.tool_call_id == "call_123"

    def test_add_multiple_messages(self, chat_interface):
        chat_interface.add_message("system", "You are helpful.")
        chat_interface.add_message("user", "Hello!")
        chat_interface.add_message("assistant", "Hi there!")

        assert len(chat_interface.messages) == 3
        assert chat_interface.messages[0].role == "system"
        assert chat_interface.messages[1].role == "user"
        assert chat_interface.messages[2].role == "assistant"

    def test_get_conversation_history(self, chat_interface):
        chat_interface.add_message("user", "Hello!")
        chat_interface.add_message("assistant", "Hi!")

        history = chat_interface.get_conversation_history()
        assert len(history) == 2
        assert isinstance(history, list)
        assert isinstance(history[0], dict)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello!"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi!"

    def test_get_conversation_history_excludes_none(self, chat_interface):
        chat_interface.add_message("user", "Hello!", name=None)
        history = chat_interface.get_conversation_history()
        assert len(history) == 1
        assert "role" in history[0]
        assert "content" in history[0]
        assert "name" not in history[0]
        assert "tool_calls" not in history[0]

    def test_get_conversation_history_empty(self, chat_interface):
        history = chat_interface.get_conversation_history()
        assert len(history) == 0
        assert isinstance(history, list)

    def test_clear_conversation(self, chat_interface):
        chat_interface.add_message("user", "Hello!")
        chat_interface.add_message("assistant", "Hi!")
        assert len(chat_interface.messages) == 2

        chat_interface.clear_conversation()
        assert len(chat_interface.messages) == 0

    def test_start_with_system_message(self, chat_interface):
        chat_interface.add_message("user", "Hello!")
        assert len(chat_interface.messages) == 1

        chat_interface.start_with_system_message("You are a helpful assistant.")
        assert len(chat_interface.messages) == 1
        assert chat_interface.messages[0].role == "system"
        assert chat_interface.messages[0].content == "You are a helpful assistant."

    def test_send_message(self, chat_interface, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello! How can I help?"

        mock_client_instance = mock_openai_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        response = chat_interface.send_message("Hi there!")

        assert response == "Hello! How can I help?"
        assert len(chat_interface.messages) == 2
        assert chat_interface.messages[0].role == "user"
        assert chat_interface.messages[0].content == "Hi there!"
        assert chat_interface.messages[1].role == "assistant"
        assert chat_interface.messages[1].content == "Hello! How can I help?"

    def test_send_message_calls_api_correctly(self, chat_interface, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"

        mock_client_instance = mock_openai_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        chat_interface.send_message("Test message")

        mock_client_instance.chat.completions.create.assert_called_once()
        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["temperature"] == 0.7
        assert "max_tokens" not in call_kwargs
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0]["role"] == "user"
        assert call_kwargs["messages"][0]["content"] == "Test message"

    def test_send_message_with_max_tokens(self, chat_interface_with_max_tokens, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"

        mock_client_instance = mock_openai_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        chat_interface_with_max_tokens.send_message("Test message")

        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 500

    def test_send_message_with_existing_history(self, chat_interface, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"

        mock_client_instance = mock_openai_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        chat_interface.add_message("system", "You are helpful.")
        chat_interface.send_message("Test message")

        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][1]["role"] == "user"

    def test_send_message_preserves_history(self, chat_interface, mock_openai_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "First response"

        mock_client_instance = mock_openai_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        chat_interface.send_message("First message")

        mock_response.choices[0].message.content = "Second response"
        chat_interface.send_message("Second message")

        assert len(chat_interface.messages) == 4
        assert chat_interface.messages[0].content == "First message"
        assert chat_interface.messages[1].content == "First response"
        assert chat_interface.messages[2].content == "Second message"
        assert chat_interface.messages[3].content == "Second response"


class TestAzureChatInterface:

    @pytest.fixture
    def mock_azure_client(self):
        with patch('src.chat.interface.AzureOpenAI') as mock_client:
            yield mock_client

    @pytest.fixture
    def azure_chat_interface(self, mock_azure_client):
        return AzureChatInterface(
            api_key="azure-test-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4-deployment",
            model="gpt-4",
            temperature=0.7
        )

    @pytest.fixture
    def azure_chat_interface_custom_version(self, mock_azure_client):
        return AzureChatInterface(
            api_key="azure-test-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4-deployment",
            api_version="2023-12-01",
            model="gpt-4"
        )

    def test_azure_chat_interface_initialization(self, mock_azure_client):
        interface = AzureChatInterface(
            api_key="azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4-deployment"
        )
        assert interface.api_key == "azure-key"
        assert interface.azure_endpoint == "https://test.openai.azure.com/"
        assert interface.deployment_name == "gpt-4-deployment"
        assert interface.api_version == "2024-02-01"
        assert interface.model == "gpt-4"
        assert len(interface.messages) == 0

        mock_azure_client.assert_called_once_with(
            api_key="azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            api_version="2024-02-01"
        )

    def test_azure_chat_interface_custom_api_version(self, mock_azure_client):
        interface = AzureChatInterface(
            api_key="azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4-deployment",
            api_version="2023-12-01"
        )
        assert interface.api_version == "2023-12-01"

        mock_azure_client.assert_called_once_with(
            api_key="azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            api_version="2023-12-01"
        )

    def test_azure_inherits_from_chat_interface(self, azure_chat_interface):
        assert isinstance(azure_chat_interface, ChatInterface)

    def test_azure_add_message(self, azure_chat_interface):
        azure_chat_interface.add_message("user", "Hello Azure!")
        assert len(azure_chat_interface.messages) == 1
        assert azure_chat_interface.messages[0].role == "user"
        assert azure_chat_interface.messages[0].content == "Hello Azure!"

    def test_azure_get_conversation_history(self, azure_chat_interface):
        azure_chat_interface.add_message("user", "Hello!")
        history = azure_chat_interface.get_conversation_history()
        assert len(history) == 1
        assert history[0]["role"] == "user"

    def test_azure_clear_conversation(self, azure_chat_interface):
        azure_chat_interface.add_message("user", "Hello!")
        azure_chat_interface.clear_conversation()
        assert len(azure_chat_interface.messages) == 0

    def test_azure_start_with_system_message(self, azure_chat_interface):
        azure_chat_interface.start_with_system_message("You are helpful.")
        assert len(azure_chat_interface.messages) == 1
        assert azure_chat_interface.messages[0].role == "system"

    def test_azure_send_message(self, azure_chat_interface, mock_azure_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from Azure!"

        mock_client_instance = mock_azure_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        response = azure_chat_interface.send_message("Hi there!")

        assert response == "Hello from Azure!"
        assert len(azure_chat_interface.messages) == 2
        assert azure_chat_interface.messages[0].role == "user"
        assert azure_chat_interface.messages[1].role == "assistant"

    def test_azure_send_message_uses_deployment_name(self, azure_chat_interface, mock_azure_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"

        mock_client_instance = mock_azure_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        azure_chat_interface.send_message("Test")

        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4-deployment"
        assert "deployment_name" not in call_kwargs

    def test_azure_send_message_with_max_tokens(self, mock_azure_client):
        interface = AzureChatInterface(
            api_key="azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4-deployment",
            max_tokens=800
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"

        mock_client_instance = mock_azure_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        interface.send_message("Test")

        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 800

    def test_azure_send_message_with_custom_temperature(self, mock_azure_client):
        interface = AzureChatInterface(
            api_key="azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="gpt-4-deployment",
            temperature=0.3
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"

        mock_client_instance = mock_azure_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        interface.send_message("Test")

        call_kwargs = mock_client_instance.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    def test_azure_required_fields(self, mock_azure_client):
        with pytest.raises(ValidationError) as excinfo:
            AzureChatInterface(api_key="test-key")
        error_str = str(excinfo.value)
        assert "azure_endpoint" in error_str
        assert "deployment_name" in error_str

    def test_azure_conversation_flow(self, azure_chat_interface, mock_azure_client):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]

        mock_client_instance = mock_azure_client.return_value
        mock_client_instance.chat.completions.create.return_value = mock_response

        azure_chat_interface.start_with_system_message("You are helpful.")

        mock_response.choices[0].message.content = "First response"
        azure_chat_interface.send_message("First question")

        mock_response.choices[0].message.content = "Second response"
        azure_chat_interface.send_message("Second question")

        assert len(azure_chat_interface.messages) == 5
        assert azure_chat_interface.messages[0].role == "system"
        assert azure_chat_interface.messages[1].role == "user"
        assert azure_chat_interface.messages[2].role == "assistant"
        assert azure_chat_interface.messages[3].role == "user"
        assert azure_chat_interface.messages[4].role == "assistant"
