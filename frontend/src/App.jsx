import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { SessionProvider, useSession } from './context/SessionContext';
import UploadPage from './pages/UploadPage';
import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import './App.css';

function ProtectedRoutes() {
  const { username, isLoading } = useSession();

  if (isLoading) {
    return (
      <div className="app">
        <div className="loading-screen">
          <div className="spinner"></div>
        </div>
      </div>
    );
  }

  if (!username) {
    return <LoginPage />;
  }

  return (
    <Routes>
      <Route path="/" element={<UploadPage />} />
      <Route path="/chat" element={<ChatPage />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <div className="app">
          <ProtectedRoutes />
        </div>
      </SessionProvider>
    </BrowserRouter>
  );
}

export default App;
