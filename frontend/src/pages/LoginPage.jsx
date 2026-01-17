import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../context/SessionContext';

export default function LoginPage() {
  const [inputValue, setInputValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const { setUsername } = useSession();
  const navigate = useNavigate();

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    setUsername(trimmed);
    navigate('/');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSubmit(e);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <h1 className="login-title">
          <span>Welcome to</span>
          <span>SLO-RAG</span>
        </h1>
        <p className="login-subtitle">
          Enter a unique username to enable session tracking
        </p>
        <form className="login-form" onSubmit={handleSubmit}>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={isFocused ? '' : 'Enter username'}
            className="login-input"
            autoFocus
          />
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className="login-button"
          >
            Continue
          </button>
        </form>
      </div>
    </div>
  );
}
