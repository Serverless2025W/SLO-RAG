import { useState, useEffect, useRef } from 'react';
import { useSession } from '../context/SessionContext';
import { queryRAG, getConversationHistory } from '../api';
import Layout from '../components/Layout';

export default function ChatPage() {
  const { username } = useSession();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSummaryBlinking, setIsSummaryBlinking] = useState(false);
  const lastSummaryKeyRef = useRef(null);
  const summaryBlinkTimerRef = useRef(null);
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

  // Summarization events (system messages)
  const summaryMessages = messages.filter(msg => msg.role === 'system');
  const hasSystemMessage = summaryMessages.length > 0;
  const visibleMessages = messages.filter(msg => msg.role !== 'system');
  const latestSummary = summaryMessages[summaryMessages.length - 1];

  useEffect(() => {
    if (!latestSummary) return;
    const summaryKey = `${latestSummary.timestamp || ''}:${latestSummary.content || ''}`;
    if (lastSummaryKeyRef.current === summaryKey) return;

    lastSummaryKeyRef.current = summaryKey;
    // Blink chat container to signal a summarization event.
    // Force a class re-add so the CSS animation re-triggers even if multiple summaries happen quickly.
    setIsSummaryBlinking(false);
    requestAnimationFrame(() => setIsSummaryBlinking(true));

    if (summaryBlinkTimerRef.current) {
      clearTimeout(summaryBlinkTimerRef.current);
    }
    summaryBlinkTimerRef.current = setTimeout(() => {
      setIsSummaryBlinking(false);
      summaryBlinkTimerRef.current = null;
    }, 2200);
  }, [latestSummary]);

  useEffect(() => {
    return () => {
      if (summaryBlinkTimerRef.current) {
        clearTimeout(summaryBlinkTimerRef.current);
      }
    };
  }, []);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    // Check for system messages BEFORE sending (in case summarization happened)
    const currentHistory = await getConversationHistory(username).catch(() => []);
    const currentSystemMsg = currentHistory.find(msg => msg.role === 'system');
    
    const userMessage = {
      role: 'user',
      content: trimmed
    };

    // If we found a system message, update messages before adding new one
    if (currentSystemMsg) {
      // Reload full history to get the correct state (includes summary + last assistant if any)
      setMessages(currentHistory);
      // Then add the new user message
      setMessages(prev => [...prev, userMessage]);
    } else {
      setMessages(prev => [...prev, userMessage]);
    }

    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await queryRAG(trimmed, username);

      if (response.answer) {
        const assistantMessage = {
          role: 'assistant',
          content: response.answer,
          model: response.model,
          sources: response.sources
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
      <div className="chat-section">
        <h2>Ask Anything</h2>
        <div className={`chat-container ${isSummaryBlinking ? 'chat-container--summary-blink' : ''}`}>
          <div className="message-list">
            {visibleMessages.map((msg, index) => (
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
        {hasSystemMessage && (
          <div className="summarization-log">
            <div className="summarization-log-header">
              <span>Summarization events</span>
              <span className="summarization-log-meta">
                {summaryMessages.length} total
              </span>
            </div>
            <div className="summarization-log-list">
              {[...summaryMessages]
                .slice()
                .reverse()
                .map((msg, index) => {
                  const timestamp = msg.timestamp
                    ? new Date(msg.timestamp).toLocaleString()
                    : 'Unknown time';
                  return (
                    <details key={`${msg.timestamp || index}-${index}`} className="summarization-log-item">
                      <summary>
                        <span className="summarization-log-title">Context summarized</span>
                        <span className="summarization-log-time">{timestamp}</span>
                      </summary>
                      <div className="summarization-summary-text">{msg.content}</div>
                    </details>
                  );
                })}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
