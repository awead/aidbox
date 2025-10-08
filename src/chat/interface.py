from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict
from openai import OpenAI, AzureOpenAI
from openai.types.chat import ChatCompletion


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""
    role: Literal["system", "user", "assistant", "function", "tool"] = Field(
        ..., description="Role of the message sender"
    )
    content: Optional[str] = Field(None, description="Content of the message")
    name: Optional[str] = Field(None, description="Optional name for the message sender")
    tool_calls: Optional[List[Dict]] = Field(None, description="Tool calls for assistant messages")
    tool_call_id: Optional[str] = Field(None, description="Tool call ID for tool response messages")


class ChatInterface(BaseModel):
    """A chat interface for interacting with OpenAI models."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    api_key: str = Field(..., description="OpenAI API key")
    model: str = Field("gpt-4", description="Model ID to use")
    temperature: float = Field(0.7, description="Sampling temperature", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="Maximum number of tokens to generate")
    messages: List[ChatMessage] = Field(default_factory=list, description="Conversation history")
    
    def __init__(self, **data):
        super().__init__(**data)
        self._client = OpenAI(api_key=self.api_key)
    
    def add_message(
        self,
        role: str,
        content: Optional[str] = None,
        name: Optional[str] = None,
        tool_calls: Optional[List[Dict]] = None,
        tool_call_id: Optional[str] = None
    ) -> None:
        """Add a message to the conversation history.

        Args:
            role: Role of the message sender (system, user, assistant, function, tool)
            content: Content of the message (optional for assistant messages with tool_calls)
            name: Optional name for the message sender
            tool_calls: Tool calls for assistant messages
            tool_call_id: Tool call ID for tool response messages
        """
        self.messages.append(ChatMessage(
            role=role,
            content=content,
            name=name,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id
        ))
    
    def get_conversation_history(self) -> List[Dict]:
        """Get the conversation history in the format expected by the OpenAI API.
        
        Returns:
            List of message dictionaries
        """
        return [message.model_dump(exclude_none=True) for message in self.messages]
    
    def send_message(self, message: str) -> str:
        """Send a user message and get the assistant's response.
        
        Args:
            message: Message content from the user
            
        Returns:
            Assistant's response content
        """
        self.add_message("user", message)
        
        params = {
            "model": self.model,
            "messages": self.get_conversation_history(),
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        
        response: ChatCompletion = self._client.chat.completions.create(**params)
        
        assistant_message = response.choices[0].message.content
        self.add_message("assistant", assistant_message)
        
        return assistant_message
    
    def clear_conversation(self) -> None:
        """Clear the conversation history."""
        self.messages = []
        
    def start_with_system_message(self, content: str) -> None:
        """Start a new conversation with a system message.
        
        Args:
            content: System message content
        """
        self.clear_conversation()
        self.add_message("system", content)


class AzureChatInterface(ChatInterface):
    """A chat interface for interacting with Azure OpenAI models."""
    
    api_key: str = Field(..., description="Azure OpenAI API key")
    azure_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    api_version: str = Field("2024-02-01", description="Azure OpenAI API version")
    deployment_name: str = Field(..., description="Azure OpenAI deployment name")
    
    def __init__(self, **data):
        super().__init__(**data)
        self._client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version
        )
    
    def send_message(self, message: str) -> str:
        """Send a user message and get the assistant's response using Azure OpenAI.
        
        Args:
            message: Message content from the user
            
        Returns:
            Assistant's response content
        """
        self.add_message("user", message)
        
        params = {
            "model": self.deployment_name,
            "messages": self.get_conversation_history(),
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        
        response: ChatCompletion = self._client.chat.completions.create(**params)
        
        assistant_message = response.choices[0].message.content
        self.add_message("assistant", assistant_message)
        
        return assistant_message
