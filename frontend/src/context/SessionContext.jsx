import { createContext, useContext, useState, useEffect } from 'react';

const SessionContext = createContext(null);

const STORAGE_KEY = 'slo_rag_username';

export function SessionProvider({ children }) {
  const [username, setUsernameState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      setUsernameState(stored);
    }
    setIsLoading(false);
  }, []);

  const setUsername = (name) => {
    if (name) {
      localStorage.setItem(STORAGE_KEY, name);
      setUsernameState(name);
    }
  };

  const clearSession = () => {
    localStorage.removeItem(STORAGE_KEY);
    setUsernameState(null);
  };

  return (
    <SessionContext.Provider value={{ username, setUsername, clearSession, isLoading }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
}
