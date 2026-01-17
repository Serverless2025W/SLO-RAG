#!/bin/bash
# Deploy one or all functions to faasd
# Usage: ./scripts/deploy.sh [function-name]
# Examples:
#   ./scripts/deploy.sh                    # Deploy all functions
#   ./scripts/deploy.sh query-embedding-retrieval  # Deploy single function

set -e

if [ -z "$DOCKER_USER" ]; then
    echo "Error: DOCKER_USER not set"
    echo "Run: export DOCKER_USER=<your-dockerhub-username>"
    exit 1
fi

if [ -n "$1" ]; then
    echo "Deploying $1..."
    faas-cli deploy -f stack.yaml --filter "$1"
else
    echo "Deploying all functions..."
    faas-cli deploy -f stack.yaml
fi

echo ""
echo "Deployed functions:"
faas-cli list
