import { useState, useEffect, useRef } from 'react';
import { useSession } from '../context/SessionContext';
import { queryRAG, getConversationHistory, storeMessage } from '../api';
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
      content: trimmed
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      // Store user message
      storeMessage(username, 'user', trimmed).catch(err =>
        console.log('Could not store user message:', err.message)
      );

      const response = await queryRAG(trimmed, username);

      if (response.answer) {
        const assistantMessage = {
          role: 'assistant',
          content: response.answer,
          model: response.model,
          sources: response.sources
        };
        setMessages(prev => [...prev, assistantMessage]);

        // Store assistant message
        storeMessage(username, 'assistant', response.answer).catch(err =>
          console.log('Could not store assistant message:', err.message)
        );
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
      <div className="chat-section">
        <h2>Ask Anything</h2>
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
              {msg.model && (
                <div className="message-model">
                  Model: {msg.model}
                </div>
              )}
              {msg.sources && msg.sources.length > 0 && (
                <div className="message-sources">
                  <details>
                    <summary>Sources ({msg.sources.length})</summary>
                    <ul>
                      {msg.sources.map((src, i) => (
                        <li key={i}>
                          {src.filename} (chunk {src.chunk_index}, score: {src.score.toFixed(3)})
                        </li>
                      ))}
                    </ul>
                  </details>
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
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={isLoading}
            className="chat-input"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className={`chat-send-btn ${input.trim() ? 'active' : ''}`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
        </div>
      </div>
    </Layout>
  );
}
