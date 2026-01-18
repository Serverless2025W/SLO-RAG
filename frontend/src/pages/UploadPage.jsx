import { useState, useCallback, useEffect } from 'react';
import {
  uploadToMinio,
  pollForChunks,
  getAllDocuments,
  deleteDocument,
  getAllChunksByFilename,
} from '../api';
import Layout from '../components/Layout';

const MAX_FILES = 10;

export default function UploadPage() {
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fileStatuses, setFileStatuses] = useState({});
  const [chunks, setChunks] = useState([]);
  const [processedFiles, setProcessedFiles] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [pendingDocuments, setPendingDocuments] = useState([]);
  const [expandedFilename, setExpandedFilename] = useState(null);
  const [documentChunks, setDocumentChunks] = useState({});
  const [loadingChunks, setLoadingChunks] = useState({});
  const [chunksError, setChunksError] = useState({});

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await getAllDocuments();
      setDocuments(docs);
      setPendingDocuments(prev =>
        prev.filter(pending => !docs.some(doc => doc.filename === pending.filename))
      );
    } catch (error) {
      console.error('Failed to load documents:', error);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    if (pendingDocuments.length === 0) return;
    const interval = setInterval(loadDocuments, 10000);
    return () => clearInterval(interval);
  }, [pendingDocuments.length, loadDocuments]);

  const handleDelete = async (filename) => {
    try {
      await deleteDocument(filename);
      setDocuments(prev => prev.filter(doc => doc.filename !== filename));
      setDocumentChunks(prev => {
        const next = { ...prev };
        delete next[filename];
        return next;
      });
      setPendingDocuments(prev => prev.filter(doc => doc.filename !== filename));
      setExpandedFilename(prev => (prev === filename ? null : prev));
    } catch (error) {
      console.error('Failed to delete document:', error);
    }
  };

  const toggleDocumentChunks = async (filename) => {
    if (expandedFilename === filename) {
      setExpandedFilename(null);
      return;
    }

    setExpandedFilename(filename);

    if (documentChunks[filename]?.length) return;

    setLoadingChunks(prev => ({ ...prev, [filename]: true }));
    setChunksError(prev => ({ ...prev, [filename]: null }));
    try {
      const fetched = await getAllChunksByFilename(filename);
      setDocumentChunks(prev => ({ ...prev, [filename]: fetched }));
    } catch (error) {
      setChunksError(prev => ({ ...prev, [filename]: error.message }));
    } finally {
      setLoadingChunks(prev => ({ ...prev, [filename]: false }));
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
        setPendingDocuments(prev => {
          if (prev.some(doc => doc.filename === file.name)) return prev;
          return [...prev, { filename: file.name, status: 'processing' }];
        });
        updateFileStatus(file.name, { type: 'info', message: 'Processing...' });

        const fetchedChunks = await pollForChunks(file.name, 60, 2000);

        if (fetchedChunks.length > 0) {
          allChunks.push(...fetchedChunks);
          updateFileStatus(file.name, { type: 'success', message: `${fetchedChunks.length} chunks` });
          setPendingDocuments(prev => prev.filter(doc => doc.filename !== file.name));
        } else {
          updateFileStatus(file.name, {
            type: 'warning',
            message: 'Still processing; will refresh documents automatically.',
          });
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

  const visibleDocuments = [
    ...documents,
    ...pendingDocuments.filter(
      pending => !documents.some(doc => doc.filename === pending.filename)
    ),
  ];

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

      {visibleDocuments.length > 0 && (
        <div className="documents-section">
          <h2>Project Files ({visibleDocuments.length})</h2>
          <div className="documents-list">
            {visibleDocuments.map((doc) => {
              const isPending = doc.status === 'processing';
              return (
                <div key={doc.filename} className="document-item">
                <button
                  className="document-main"
                  onClick={() => toggleDocumentChunks(doc.filename)}
                  type="button"
                  title="Show chunks"
                >
                  <svg className="document-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                  <div className="document-info">
                    <span className="document-name">{doc.filename}</span>
                    <span className="document-chunks">
                      {isPending ? 'processing...' : `${doc.chunkCount} chunks`}
                    </span>
                  </div>
                  <span className="document-toggle">{expandedFilename === doc.filename ? 'Hide' : 'Chunks'}</span>
                </button>
                <button
                  className="document-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(doc.filename);
                  }}
                  title="Delete document"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <line x1="10" y1="11" x2="10" y2="17" />
                    <line x1="14" y1="11" x2="14" y2="17" />
                  </svg>
                </button>
                {expandedFilename === doc.filename && (
                  <div className="document-chunks-panel">
                    {loadingChunks[doc.filename] && (
                      <div className="document-chunks-loading">Loading chunks...</div>
                    )}
                    {chunksError[doc.filename] && (
                      <div className="document-chunks-error">{chunksError[doc.filename]}</div>
                    )}
                    {!loadingChunks[doc.filename] && !chunksError[doc.filename] && (
                      <div className="document-chunks-list">
                        {(documentChunks[doc.filename] || [])
                          .sort((a, b) => a.payload.chunk_index - b.payload.chunk_index)
                          .map((chunk, index) => (
                            <div key={chunk.id || index} className="document-chunk-row">
                              <span className="document-chunk-index">
                                Chunk {chunk.payload.chunk_index + 1}
                              </span>
                              <p className="document-chunk-text">{chunk.payload.text}</p>
                            </div>
                          ))}
                        {(documentChunks[doc.filename] || []).length === 0 && (
                          <div className="document-chunks-empty">No chunks found.</div>
                        )}
                      </div>
                    )}
                  </div>
                )}
                </div>
              );
            })}
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
