const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const clearButton = document.getElementById('clear-chat');
const chatMessages = document.getElementById('chat-messages');
const typingIndicator = document.getElementById('typing-indicator');
const messageCount = document.getElementById('message-count');
const autoScrollToggle = document.getElementById('auto-scroll');
const themeToggle = document.getElementById('theme-toggle');

let messageCounter = 1;
const MAX_STORED_MESSAGES = 50;

// Theme Management
function initializeTheme() {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
        document.documentElement.setAttribute('data-theme', 'dark');
        themeToggle.checked = true;
    }
}

function toggleTheme(e) {
    if (e.target.checked) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
    }
}

// Message Management
function updateMessageCount() {
    messageCounter = document.querySelectorAll('.message').length;
    messageCount.textContent = `Messages: ${messageCounter}`;
}

function getCurrentTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatCodeBlocks(text) {
    const codeBlockRegex = /```(?:python)?\n([\s\S]*?)```|\n((?:    |\t)[\s\S]+?)(?=\n\S|$)/g;
    let formattedText = text;
    let codeBlocks = [];
    
    formattedText = formattedText.replace(codeBlockRegex, (match, fenced, indented) => {
        const code = (fenced || indented).trim();
        const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
        codeBlocks.push(code);
        return placeholder;
    });
    
    const parts = formattedText.split(/((?:__CODE_BLOCK_\d+__))/);
    
    return parts.map(part => {
        const codeBlockMatch = part.match(/__CODE_BLOCK_(\d+)__/);
        if (codeBlockMatch) {
            const code = codeBlocks[parseInt(codeBlockMatch[1])];
            return `<div class="code-block">
                <button class="copy-button">Copy</button>
                <pre><code class="python">${escapeHtml(code)}</code></pre>
            </div>`;
        }
        return part;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function addMessage(message, isUser = false, save = true) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
    messageDiv.style.animation = isUser ? 'slideIn 0.3s ease' : 'fadeIn 0.3s ease';
    
    const formattedContent = isUser ? message : formatCodeBlocks(message);
    const icon = isUser ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
    
    messageDiv.innerHTML = `
        <div class="message-content">
            ${icon} ${formattedContent}
        </div>
        <div class="message-time">${getCurrentTime()}</div>
        <div class="message-actions">
            <i class="fas fa-copy action-icon" title="Copy message"></i>
            <i class="fas fa-trash action-icon" title="Delete message"></i>
        </div>
    `;
    
    chatMessages.insertBefore(messageDiv, typingIndicator);
    
    if (!isUser) {
        messageDiv.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
        
        messageDiv.querySelectorAll('.copy-button').forEach(button => {
            button.addEventListener('click', () => {
                const code = button.nextElementSibling.textContent;
                copyToClipboard(code, button);
            });
        });
    }

    setupMessageActions(messageDiv, save);
    
    if (autoScrollToggle.checked) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    updateMessageCount();
    
    if (save) {
        saveChatHistory();
    }
}

function setupMessageActions(messageDiv, save) {
    const copyButton = messageDiv.querySelector('.fa-copy');
    const deleteButton = messageDiv.querySelector('.fa-trash');
    
    if (copyButton) {
        copyButton.addEventListener('click', () => {
            const content = messageDiv.querySelector('.message-content').textContent.trim();
            copyToClipboard(content, copyButton);
        });
    }
    
    if (deleteButton) {
        deleteButton.addEventListener('click', () => {
            messageDiv.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => {
                messageDiv.remove();
                updateMessageCount();
                if (save) {
                    saveChatHistory();
                }
            }, 300);
        });
    }
}

async function copyToClipboard(text, button) {
    try {
        await navigator.clipboard.writeText(text);
        const originalColor = button.style.color;
        button.style.color = 'var(--primary-color)';
        setTimeout(() => {
            button.style.color = originalColor;
        }, 1000);
    } catch (err) {
        console.error('Failed to copy:', err);
    }
}

// Chat History Management
function loadChatHistory() {
    const savedMessages = localStorage.getItem('chatHistory');
    if (savedMessages) {
        const messages = JSON.parse(savedMessages);
        chatMessages.innerHTML = '';
        messages.forEach(msg => {
            addMessage(msg.content, msg.isUser, false);
        });
        chatMessages.appendChild(typingIndicator);
    }
    updateMessageCount();
}

function saveChatHistory() {
    const messages = [];
    document.querySelectorAll('.message').forEach(msg => {
        if (!msg.querySelector('.typing-indicator')) {
            messages.push({
                content: msg.querySelector('.message-content').innerHTML,
                isUser: msg.classList.contains('user-message'),
                timestamp: msg.querySelector('.message-time').textContent
            });
        }
    });
    const trimmedMessages = messages.slice(-MAX_STORED_MESSAGES);
    localStorage.setItem('chatHistory', JSON.stringify(trimmedMessages));
}

// Message Sending
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    messageInput.value = '';
    messageInput.disabled = true;
    sendButton.disabled = true;

    addMessage(message, true);
    typingIndicator.style.display = 'block';

    try {
        const response = await fetch('/send_message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message })
        });

        const data = await response.json();
        typingIndicator.style.display = 'none';

        if (data && data.response) {
            console.log('Bot response:', data.response);
            
            if (data.response.includes("need to restart our conversation")) {
                await resetChat();
            }
            
            addMessage(data.response);
        } else {
            console.error('Invalid response format:', data);
            addMessage('Sorry, there was an error. Please try again.');
        }
    } catch (error) {
        console.error('Error:', error);
        typingIndicator.style.display = 'none';
        addMessage('Sorry, there was an error processing your message.');
    } finally {
        messageInput.disabled = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// Chat Reset
async function resetChat() {
    try {
        const response = await fetch('/reset_chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ reset: true })
        });

        if (!response.ok) {
            throw new Error('Failed to reset chat history');
        }

        localStorage.removeItem('chatHistory');
        const welcomeMessage = chatMessages.firstElementChild;
        chatMessages.innerHTML = '';
        chatMessages.appendChild(welcomeMessage);
        chatMessages.appendChild(typingIndicator);
        updateMessageCount();
        addMessage('Chat history has been cleared. How can I help you?', false);
    } catch (error) {
        console.error('Error resetting chat:', error);
        addMessage('There was an error clearing the chat history. Please try again.', false);
    }
}

// Event Listeners
sendButton.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
clearButton.addEventListener('click', () => {
    if (confirm('Are you sure you want to clear the chat history?')) {
        resetChat();
    }
});
themeToggle.addEventListener('change', toggleTheme);

// Initialize
initializeTheme();
loadChatHistory();
messageInput.focus();
