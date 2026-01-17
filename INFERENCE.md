# SLO-RAG Deployment Workflow

## Quick Reference

### First Time Setup
```bash
# Set your Docker Hub username (add to ~/.bashrc to persist)
export DOCKER_USER=<your-dockerhub-username>

# Pull OpenFaaS templates
faas-cli template pull
faas-cli template store pull python3-http
faas-cli template store pull python3-http-debian
```

### Common Commands

| Task | Command |
|------|---------|
| Redeploy single function | `./scripts/redeploy.sh query-embedding-retrieval` |
| Redeploy all functions | `./scripts/redeploy.sh` |
| View function logs | `./scripts/logs.sh query-embedding-retrieval` |
| List functions | `faas-cli list` |
| Restart infrastructure | `sudo ./scripts/restart-faasd.sh` |

### Manual Steps (if scripts don't work)

```bash
# Build and push
faas-cli publish -f stack.yaml --filter <function-name>

# Deploy
faas-cli deploy -f stack.yaml --filter <function-name>

# Restart faasd (for docker-compose changes)
sudo cp docker-compose.yaml /var/lib/faasd/docker-compose.yaml
sudo systemctl restart faasd
```

## Function Names
- `text-extraction` - PDF/text parsing, chunking
- `embedding-generation` - Vector embeddings via FastEmbed
- `query-embedding-retrieval` - Query + retrieval + calls router
- `router` - Routes to local or remote inference
- `local-inference` - Llama-3.2-1B on GPU
- `remote-inference` - Groq API (Llama-3.3-70B)

## Inference Workflow
```
User Query
    ↓
query-embedding-retrieval
    ↓ (generates embedding, retrieves from Qdrant)
    ↓ (formats RAG prompt)
    ↓
router (random selection)
    ↓
local-inference OR remote-inference
    ↓
Response with answer + model + sources
```

## Testing

### Test full RAG workflow
```bash
curl -X POST http://localhost:8080/function/query-embedding-retrieval \
  -H "Content-Type: application/json" \
  -d '{"query": "What is machine learning?"}'
```

### Upload test document
```bash
/tmp/mc cp /path/to/file.pdf local/documents/
```

### Check MinIO
```bash
/tmp/mc ls local/documents
```

## Troubleshooting

### Function not updating after deploy
```bash
# Force remove and redeploy
faas-cli remove <function-name>
faas-cli deploy -f stack.yaml --filter <function-name>
```

### Check faasd logs
```bash
sudo journalctl -u faasd -n 50 --no-pager
```

### Check running containers
```bash
sudo ctr -n openfaas tasks ls
```
