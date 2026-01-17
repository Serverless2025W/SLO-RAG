import { useState } from 'react';
import { queryRAG } from '../api';
import Layout from '../components/Layout';

export default function QueryPage() {
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
    <Layout>
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
          placeholder="Ask SLO-RAG"
          rows={4}
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !query.trim()}>
          {isLoading ? 'Searching...' : 'Execute'}
        </button>
      </form>

      {error && <div className="status error">{error}</div>}

      {result && (
        <div className="results-section">
          <div className="answer-section">
            <h2>Answer</h2>
            <div className="backend-badge">
              {result.model || 'Unknown model'}
            </div>
            <div className="answer-text">
              {result.answer || 'No answer generated.'}
            </div>
          </div>

          <h2>Sources</h2>
          {result.sources && result.sources.length > 0 ? (
            <div className="results-list">
              {result.sources.map((chunk, index) => (
                <div key={index} className="result-card">
                  <div className="result-header">
                    <span className="result-index">Source {index + 1}</span>
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
                  <p className="result-text">{chunk.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="no-results">No source documents retrieved.</p>
          )}
        </div>
      )}
    </Layout>
  );
}
