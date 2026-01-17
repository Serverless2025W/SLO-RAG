import { useState, useCallback, useEffect } from 'react';
import { uploadToMinio, pollForChunks, getAllDocuments } from '../api';
import Layout from '../components/Layout';

const MAX_FILES = 10;

export default function UploadPage() {
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fileStatuses, setFileStatuses] = useState({});
  const [chunks, setChunks] = useState([]);
  const [processedFiles, setProcessedFiles] = useState([]);
  const [documents, setDocuments] = useState([]);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      const docs = await getAllDocuments();
      setDocuments(docs);
    } catch (error) {
      console.error('Failed to load documents:', error);
    }
  };

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
    loadDocuments();
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
    <Layout>
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

      {documents.length > 0 && (
        <div className="documents-section">
          <h2>Project Files ({documents.length})</h2>
          <div className="documents-list">
            {documents.map((doc) => (
              <div key={doc.filename} className="document-item">
                <svg className="document-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <div className="document-info">
                  <span className="document-name">{doc.filename}</span>
                  <span className="document-chunks">{doc.chunkCount} chunks</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.keys(groupedChunks).length > 0 && (
        <div className="chunks-section">
          <h2>Uploaded Chunks ({chunks.length} total)</h2>
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
        </div>
      )}
    </Layout>
  );
}
