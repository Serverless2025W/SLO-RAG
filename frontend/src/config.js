const VM_IP = 'localhost';

export const config = {
  minio: {
    endpoint: `/minio`,
    bucket: 'documents',
  },
  openfaas: {
    gateway: `/openfaas`,
    functions: {
      queryEmbeddingRetrieval: '/function/query-embedding-retrieval',
    },
  },
  qdrant: {
    endpoint: `/qdrant`,
    collection: 'embeddings',
  },
  vmIp: VM_IP,
};

export default config;
