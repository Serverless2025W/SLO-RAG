import { BrowserRouter, Routes, Route } from 'react-router-dom';
import UploadPage from './pages/UploadPage';
import QueryPage from './pages/QueryPage';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/query" element={<QueryPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
