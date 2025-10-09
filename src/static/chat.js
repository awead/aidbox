class ChatClient {
    constructor() {
        this.ws = null;
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendButton = document.getElementById('send-button');
        this.chatForm = document.getElementById('chat-form');
        this.statusElement = document.getElementById('connection-status');
        this.statusText = document.getElementById('status-text');
        this.toolsList = document.getElementById('tools-list');

        this.setupEventListeners();
        this.connect();
        this.loadTools();
    }

    setupEventListeners() {
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateStatus('connected', 'Connected');
            this.messageInput.disabled = false;
            this.sendButton.disabled = false;
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateStatus('disconnected', 'Disconnected');
            this.messageInput.disabled = true;
            this.sendButton.disabled = true;

            setTimeout(() => {
                console.log('Attempting to reconnect...');
                this.connect();
            }, 3000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('disconnected', 'Connection Error');
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };
    }

    updateStatus(status, text) {
        this.statusElement.className = `status-${status}`;
        this.statusText.textContent = text;
    }

    async loadTools() {
        try {
            const response = await fetch('/api/tools');
            const data = await response.json();

            if (data.error) {
                this.toolsList.innerHTML = `<p class="error-message">${data.error}</p>`;
                return;
            }

            if (data.tools && data.tools.length > 0) {
                this.toolsList.innerHTML = data.tools.map(tool => `
                    <div class="tool-item">
                        <div class="tool-name">${this.escapeHtml(tool.name)}</div>
                        <div class="tool-description">${this.escapeHtml(tool.description || 'No description')}</div>
                    </div>
                `).join('');
            } else {
                this.toolsList.innerHTML = '<p class="loading">No tools available</p>';
            }
        } catch (error) {
            console.error('Error loading tools:', error);
            this.toolsList.innerHTML = '<p class="error-message">Failed to load tools</p>';
        }
    }

    sendMessage() {
        const message = this.messageInput.value.trim();

        if (!message || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        this.addUserMessage(message);

        this.ws.send(JSON.stringify({
            type: 'message',
            content: message
        }));

        this.messageInput.value = '';
        this.messageInput.focus();
    }

    handleMessage(data) {
        switch (data.type) {
            case 'assistant':
                this.addAssistantMessage(data.content);
                break;
            case 'tool_call':
                this.addToolCall(data.tool_name, data.arguments);
                break;
            case 'tool_result':
                this.addToolResult(data.tool_name, data.result);
                break;
            case 'tool_error':
                this.addToolError(data.tool_name, data.error);
                break;
            case 'error':
                this.addErrorMessage(data.content);
                break;
            case 'warning':
                this.addWarning(data.content);
                break;
            default:
                console.warn('Unknown message type:', data.type);
        }

        this.scrollToBottom();
    }

    addUserMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <div class="message-header">You</div>
            <div class="message-content">${this.escapeHtml(content)}</div>
        `;
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addAssistantMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.innerHTML = `
            <div class="message-header">Assistant</div>
            <div class="message-content">${this.escapeHtml(content)}</div>
        `;
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    addToolCall(toolName, args) {
        const toolDiv = document.createElement('div');
        toolDiv.className = 'tool-call';
        toolDiv.innerHTML = `
            <div class="tool-call-header">Calling tool: ${this.escapeHtml(toolName)}</div>
            <div class="tool-call-args">${this.formatJson(args)}</div>
        `;
        this.messagesContainer.appendChild(toolDiv);
        this.scrollToBottom();
    }

    addToolResult(toolName, result) {
        const resultDiv = document.createElement('div');
        resultDiv.className = 'tool-result';

        let formattedResult;
        try {
            const parsed = JSON.parse(result);

            if (parsed.content && parsed.content[0] && parsed.content[0].text) {
                const textObj = JSON.parse(parsed.content[0].text);
                formattedResult = this.formatJson(textObj);
            } else {
                formattedResult = this.formatJson(parsed);
            }

        } catch {
            formattedResult = this.escapeHtml(result);
        }

        resultDiv.innerHTML = `
            <div class="tool-result-header">Tool result: ${this.escapeHtml(toolName)}</div>
            <div class="tool-result-content">${formattedResult}</div>
        `;
        this.messagesContainer.appendChild(resultDiv);
        this.scrollToBottom();
    }

    addToolError(toolName, error) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'tool-error';
        errorDiv.innerHTML = `
            <div class="tool-error-header">Tool error: ${this.escapeHtml(toolName)}</div>
            <div>${this.escapeHtml(error)}</div>
        `;
        this.messagesContainer.appendChild(errorDiv);
        this.scrollToBottom();
    }

    addErrorMessage(content) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = content;
        this.messagesContainer.appendChild(errorDiv);
        this.scrollToBottom();
    }

    addWarning(content) {
        const warningDiv = document.createElement('div');
        warningDiv.className = 'warning';
        warningDiv.textContent = content;
        this.messagesContainer.appendChild(warningDiv);
        this.scrollToBottom();
    }

    scrollToBottom() {
        const container = document.getElementById('chat-container');
        container.scrollTop = container.scrollHeight;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatJson(obj) {
        return `<pre>${this.escapeHtml(JSON.stringify(obj, null, 2))}</pre>`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new ChatClient();
});
