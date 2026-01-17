import { useState, useEffect, useRef } from 'react';
import { useSession } from '../context/SessionContext';
import { sendMessage, getConversationHistory } from '../api';
import Layout from '../components/Layout';

export default function ChatPage() {
  const { username } = useSession();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (username) {
      loadHistory();
    }
  }, [username]);

  const loadHistory = async () => {
    try {
      const history = await getConversationHistory(username);
      setMessages(history);
    } catch (err) {
      console.log('Could not load history:', err.message);
    }
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMessage = {
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await sendMessage(username, trimmed);

      if (response.llm_response?.content) {
        const assistantMessage = {
          role: 'assistant',
          content: response.llm_response.content,
          timestamp: new Date().toISOString()
        };
        setMessages(prev => [...prev, assistantMessage]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Layout>
      <div className="chat-container">
        <div className="message-list">
          {messages.length === 0 && !isLoading && (
            <div className="chat-empty">
              <p>No messages yet. Start a conversation!</p>
            </div>
          )}
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`message ${msg.role}`}
            >
              <div className="message-content">
                {msg.content}
              </div>
              {msg.timestamp && (
                <div className="message-time">
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="message assistant loading">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {error && <div className="status error">{error}</div>}

        <div className="chat-input-area">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={2}
            disabled={isLoading}
            className="chat-textarea"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="chat-send-btn"
          >
            {isLoading ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>
    </Layout>
  );
}
