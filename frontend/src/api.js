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

export async function queryRAG(query) {
  const url = `${config.openfaas.gateway}${config.openfaas.functions.queryEmbeddingRetrieval}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
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
