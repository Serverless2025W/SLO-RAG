import { config } from './config';

export async function uploadToMinio(file) {
  const { endpoint, bucket } = config.minio;
  const url = `${endpoint}/${bucket}/${encodeURIComponent(file.name)}`;

  const response = await fetch(url, {
    method: 'PUT',
    body: file,
    headers: {
      'Content-Type': file.type || 'application/octet-stream',
    },
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status} ${response.statusText}`);
  }

  return { filename: file.name, bucket };
}

export async function queryRAG(query, sessionId = null) {
  const url = `${config.openfaas.gateway}${config.openfaas.functions.queryEmbeddingRetrieval}`;

  const payload = { query };
  if (sessionId) {
    payload.session_id = sessionId;
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Query failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

export async function getChunksByFilename(filename, limit = 100) {
  const { endpoint, collection } = config.qdrant;
  const url = `${endpoint}/collections/${collection}/points/scroll`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      limit,
      with_payload: true,
      with_vector: false,
      filter: {
        must: [{ key: 'filename', match: { value: filename } }],
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch chunks: ${response.status}`);
  }

  const data = await response.json();
  return data.result?.points || [];
}

export async function getCollectionInfo() {
  const { endpoint, collection } = config.qdrant;
  const url = `${endpoint}/collections/${collection}`;

  const response = await fetch(url);

  if (!response.ok) {
    if (response.status === 404) return null;
    throw new Error(`Failed to fetch collection info: ${response.status}`);
  }

  return response.json();
}

export async function pollForChunks(filename, maxAttempts = 30, intervalMs = 2000) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const chunks = await getChunksByFilename(filename);
      if (chunks.length > 0) return chunks;
    } catch (error) {
      console.log(`Poll attempt ${attempt + 1}: ${error.message}`);
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  return [];
}

export async function deleteDocument(filename) {
  const { endpoint, collection } = config.qdrant;
  const { endpoint: minioEndpoint, bucket } = config.minio;

  // Delete from Qdrant
  const qdrantUrl = `${endpoint}/collections/${collection}/points/delete`;
  const qdrantResponse = await fetch(qdrantUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      filter: {
        must: [{ key: 'filename', match: { value: filename } }],
      },
    }),
  });

  if (!qdrantResponse.ok) {
    throw new Error(`Failed to delete from Qdrant: ${qdrantResponse.status}`);
  }

  // Try to delete from MinIO (may fail if delete not allowed)
  try {
    const minioUrl = `${minioEndpoint}/${bucket}/${encodeURIComponent(filename)}`;
    await fetch(minioUrl, { method: 'DELETE' });
  } catch (e) {
    console.log('MinIO delete skipped:', e.message);
  }

  return { deleted: filename };
}

export async function getAllDocuments() {
  const { endpoint, collection } = config.qdrant;
  const url = `${endpoint}/collections/${collection}/points/scroll`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      limit: 1000,
      with_payload: true,
      with_vector: false,
    }),
  });

  if (!response.ok) {
    if (response.status === 404) return [];
    throw new Error(`Failed to fetch documents: ${response.status}`);
  }

  const data = await response.json();
  const points = data.result?.points || [];

  const fileMap = {};
  points.forEach(point => {
    const filename = point.payload.filename;
    if (!fileMap[filename]) {
      fileMap[filename] = { filename, chunkCount: 0 };
    }
    fileMap[filename].chunkCount++;
  });

  return Object.values(fileMap);
}

export async function sendMessage(sessionId, content) {
  const url = `${config.openfaas.gateway}${config.openfaas.functions.conversationManager}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      role: 'user',
      content: content,
      timestamp: new Date().toISOString()
    }),
  });

  if (!response.ok) {
    throw new Error(`Message failed: ${response.status}`);
  }

  return response.json();
}

export async function storeMessage(sessionId, role, content) {
  const url = `${config.openfaas.gateway}${config.openfaas.functions.conversationManager}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      role: role,
      content: content,
      timestamp: new Date().toISOString()
    }),
  });

  if (!response.ok) {
    throw new Error(`Store message failed: ${response.status}`);
  }

  return response.json();
}

export async function getConversationHistory(sessionId) {
  const url = `${config.openfaas.gateway}${config.openfaas.functions.conversationManager}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'get_history',
      session_id: sessionId
    }),
  });

  if (!response.ok) {
    throw new Error(`History fetch failed: ${response.status}`);
  }

  const data = await response.json();

  // Handle different response formats
  if (data.messages) {
    return data.messages;
  }
  if (data.body) {
    const body = typeof data.body === 'string' ? JSON.parse(data.body) : data.body;
    return body.messages || [];
  }
  return [];
}
