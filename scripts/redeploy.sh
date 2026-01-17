#!/bin/bash
# Full redeploy: build, push, and deploy function(s)
# Usage: ./scripts/redeploy.sh [function-name]
# Examples:
#   ./scripts/redeploy.sh                    # Redeploy all functions
#   ./scripts/redeploy.sh query-embedding-retrieval  # Redeploy single function

set -e

if [ -z "$DOCKER_USER" ]; then
    echo "Error: DOCKER_USER not set"
    echo "Run: export DOCKER_USER=<your-dockerhub-username>"
    exit 1
fi

FILTER=""
if [ -n "$1" ]; then
    FILTER="--filter $1"
    echo "=== Redeploying $1 ==="
else
    echo "=== Redeploying all functions ==="
fi

echo ""
echo "Step 1/2: Building and pushing..."
faas-cli publish -f stack.yaml $FILTER

echo ""
echo "Step 2/2: Deploying..."
faas-cli deploy -f stack.yaml $FILTER

echo ""
echo "=== Done! ==="
faas-cli list
