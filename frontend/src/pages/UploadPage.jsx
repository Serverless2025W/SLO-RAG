import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadToMinio, pollForChunks } from '../api';

const MAX_FILES = 10;

export default function UploadPage() {
  const navigate = useNavigate();
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fileStatuses, setFileStatuses] = useState({});
  const [chunks, setChunks] = useState([]);
  const [processedFiles, setProcessedFiles] = useState([]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const updateFileStatus = (filename, status) => {
    setFileStatuses(prev => ({ ...prev, [filename]: status }));
  };

  const processFiles = async (files) => {
    const fileArray = Array.from(files).slice(0, MAX_FILES);

    if (fileArray.length === 0) return;

    setIsLoading(true);
    setChunks([]);
    setProcessedFiles([]);
    setFileStatuses({});

    const allChunks = [];
    const processed = [];

    for (const file of fileArray) {
      updateFileStatus(file.name, { type: 'info', message: 'Uploading...' });

      try {
        await uploadToMinio(file);
        updateFileStatus(file.name, { type: 'info', message: 'Processing...' });

        const fetchedChunks = await pollForChunks(file.name, 20, 2000);

        if (fetchedChunks.length > 0) {
          allChunks.push(...fetchedChunks);
          updateFileStatus(file.name, { type: 'success', message: `${fetchedChunks.length} chunks` });
        } else {
          updateFileStatus(file.name, { type: 'warning', message: 'No chunks found' });
        }
        processed.push(file.name);
      } catch (error) {
        updateFileStatus(file.name, { type: 'error', message: error.message });
      }
    }

    setChunks(allChunks);
    setProcessedFiles(processed);
    setIsLoading(false);
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    processFiles(e.dataTransfer.files);
  }, []);

  const handleFileSelect = (e) => {
    processFiles(e.target.files);
  };

  const groupedChunks = chunks.reduce((acc, chunk) => {
    const filename = chunk.payload.filename;
    if (!acc[filename]) acc[filename] = [];
    acc[filename].push(chunk);
    return acc;
  }, {});

  return (
    <div className="page">
      <div className="hero">
        <h1>SLO-RAG Platform</h1>
        <p className="subtitle">
          Serverless Retrieval-Augmented Generation with SLO-aware routing.
          Upload your documents and query them using semantic search.
        </p>
      </div>

      <div className="upload-section">
        <h2>Upload Documents</h2>
        <div
          className={`dropzone ${isDragging ? 'dragging' : ''} ${isLoading ? 'loading' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {isLoading ? (
            <div className="loader">
              <div className="spinner"></div>
              <p>Processing files...</p>
            </div>
          ) : (
            <>
              <p>Drag & drop your PDF or text files here (max {MAX_FILES})</p>
              <span>or</span>
              <label className="file-input-label">
                Browse Files
                <input type="file" accept=".pdf,.txt" multiple onChange={handleFileSelect} />
              </label>
            </>
          )}
        </div>

        {Object.keys(fileStatuses).length > 0 && (
          <div className="file-statuses">
            {Object.entries(fileStatuses).map(([filename, status]) => (
              <div key={filename} className={`file-status ${status.type}`}>
                <span className="file-status-name">{filename}</span>
                <span className="file-status-message">{status.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {Object.keys(groupedChunks).length > 0 && (
        <div className="chunks-section">
          <h2>Document Chunks ({chunks.length} total)</h2>
          {Object.entries(groupedChunks).map(([filename, fileChunks]) => (
            <div key={filename} className="file-chunks">
              <h3 className="file-chunks-title">{filename} ({fileChunks.length} chunks)</h3>
              <div className="chunks-list">
                {fileChunks
                  .sort((a, b) => a.payload.chunk_index - b.payload.chunk_index)
                  .map((chunk, index) => (
                    <div key={chunk.id || index} className="chunk-card">
                      <div className="chunk-header">
                        <span className="chunk-index">Chunk {chunk.payload.chunk_index + 1}</span>
                      </div>
                      <p className="chunk-text">{chunk.payload.text}</p>
                    </div>
                  ))}
              </div>
            </div>
          ))}

          <button className="continue-btn" onClick={() => navigate('/query')}>
            Continue to Query Page
          </button>
        </div>
      )}

      {processedFiles.length > 0 && chunks.length === 0 && !isLoading && (
        <button className="continue-btn" onClick={() => navigate('/query')}>
          Continue to Query Page
        </button>
      )}
    </div>
  );
}
