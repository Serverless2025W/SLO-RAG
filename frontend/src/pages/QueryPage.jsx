import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { queryRAG } from '../api';

export default function QueryPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await queryRAG(query);
      setResult(response);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="hero">
        <h1>Query Documents</h1>
        <p className="subtitle">
          Enter your question to search through the indexed documents using semantic similarity.
        </p>
      </div>

      <form className="query-form" onSubmit={handleSubmit}>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (query.trim() && !isLoading) handleSubmit(e);
            }
          }}
          placeholder="Enter your query... (Press Enter to search)"
          rows={4}
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !query.trim()}>
          {isLoading ? 'Searching...' : 'Search'}
        </button>
      </form>

      {error && <div className="status error">{error}</div>}

      {result && (
        <div className="results-section">
          <h2>Retrieved Context</h2>
          <div className="query-display">
            <strong>Query:</strong> {result.query}
          </div>

          {result.context && result.context.length > 0 ? (
            <div className="results-list">
              {result.context.map((chunk, index) => (
                <div key={index} className="result-card">
                  <div className="result-header">
                    <span className="result-index">Result {index + 1}</span>
                    {chunk.score && (
                      <span className="result-score">
                        Score: {(chunk.score * 100).toFixed(1)}%
                      </span>
                    )}
                  </div>
                  {chunk.filename && (
                    <div className="result-meta">
                      <span>File: {chunk.filename}</span>
                      {chunk.chunk_index !== undefined && (
                        <span>Chunk: {chunk.chunk_index + 1}</span>
                      )}
                    </div>
                  )}
                  <p className="result-text">
                    {typeof chunk === 'string' ? chunk : chunk.text}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-results">No matching documents found.</p>
          )}
        </div>
      )}

      <button className="back-btn" onClick={() => navigate('/')}>
        Back to Upload
      </button>
    </div>
  );
}
