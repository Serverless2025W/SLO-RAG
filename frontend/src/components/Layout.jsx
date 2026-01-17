import { useNavigate, useLocation } from 'react-router-dom';

export default function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();

  const isUpload = location.pathname === '/';
  const isQuery = location.pathname === '/query';

  return (
    <div className="page">
      <div className="hero">
        <h1>SLO-RAG Platform</h1>
        <p className="subtitle">
          Serverless Retrieval-Augmented Generation with SLO-aware routing.
          Upload documents and query them with minimal cost overhead.
        </p>
        <div className="nav-tabs">
          <button
            className={`nav-tab ${isUpload ? 'active' : ''}`}
            onClick={() => navigate('/')}
            title="Documents"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </button>
          <button
            className={`nav-tab ${isQuery ? 'active' : ''}`}
            onClick={() => navigate('/query')}
            title="Query"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}
