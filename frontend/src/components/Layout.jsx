import { useNavigate, useLocation } from 'react-router-dom';
import { useSession } from '../context/SessionContext';

export default function Layout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, clearSession } = useSession();

  const isUpload = location.pathname === '/';
  const isChat = location.pathname === '/chat';

  const handleLogout = () => {
    clearSession();
    navigate('/');
  };

  return (
    <div className="page">
      <div className="hero">
        <div className="session-bar">
          <div className="user-menu">
            <button className="user-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="user-icon">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span>{username}</span>
            </button>
            <div className="user-dropdown">
              <button className="logout-btn" onClick={handleLogout}>
                Logout
              </button>
            </div>
          </div>
        </div>
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
            className={`nav-tab ${isChat ? 'active' : ''}`}
            onClick={() => navigate('/chat')}
            title="Chat"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}
